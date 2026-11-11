"""Immutable revision ledger service (M3, FR-B3/FR-B4).

See ``docs/M3_DESIGN.md`` for the model. The service never values portfolios
or calculates returns; the downstream cash/units replay is a posting-validity
check only (D-045). All financial quantities are ``Decimal``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

from bitemporal_ledger.ledger.derivation import (
    purchase_actual_cash,
    purchase_units,
    redemption_proceeds,
    switch_derived,
)
from bitemporal_ledger.ledger.models import (
    CorrectionRequest,
    CorrectionResult,
    IngestReport,
    VisibleRevision,
)

_TXN_TYPES = {"CONTRIBUTION", "WITHDRAWAL", "PURCHASE", "REDEMPTION", "SIP_INSTALMENT", "SWITCH"}
_CORRECTION_TYPES = {"REPLACE", "VOID", "REVERSE_AND_REPLACE"}
_MAX_ALLOTMENT_LAG_DAYS = 5
_LATEST = "infinity"


class LedgerService:
    def __init__(self, dsn: str, nav_snapshot_id: int) -> None:
        self.dsn = dsn
        self.nav_snapshot_id = nav_snapshot_id

    # ---------------------------------------------------------- helpers

    def _connect(self):
        return psycopg.connect(self.dsn)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _nav_price(self, cur, scheme_code: str, nav_date: date) -> Decimal | None:
        cur.execute(
            "SELECT nav FROM core.nav_observation WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s AND nav_date = %s",
            (self.nav_snapshot_id, scheme_code, nav_date),
        )
        row = cur.fetchone()
        return Decimal(row[0]) if row else None

    def _first_nav_on_or_after(self, cur, scheme_code: str, day: date) -> date | None:
        cur.execute(
            "SELECT min(nav_date) FROM core.nav_observation WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s AND nav_date >= %s",
            (self.nav_snapshot_id, scheme_code, day),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        candidate: date = row[0]
        return candidate if (candidate - day).days <= _MAX_ALLOTMENT_LAG_DAYS else None

    def _allotment_dates(self, cur, txn_type: str, effective: date, scheme: str | None, source: str | None, target: str | None) -> tuple[date | None, date | None, date | None] | None:
        """Resolve (allotment, source_nav, target_allotment); None if unpriceable."""
        if txn_type in ("PURCHASE", "REDEMPTION", "SIP_INSTALMENT"):
            if scheme is None:
                return None
            allotment = self._first_nav_on_or_after(cur, scheme, effective)
            if allotment is None:
                return None
            return (allotment, None, None)
        if txn_type == "SWITCH":
            if source is None or target is None:
                return None
            source_nav = self._first_nav_on_or_after(cur, source, effective)
            if source_nav is None:
                return None
            target_allotment = self._first_nav_on_or_after(cur, target, source_nav)
            if target_allotment is None:
                return None
            # allotment_date mirrors the last leg for convenience.
            return (target_allotment, source_nav, target_allotment)
        return (None, None, None)

    def _derived_legs(
        self,
        cur,
        txn_type: str,
        scheme: str | None,
        source: str | None,
        target: str | None,
        amount: Decimal | None,
        units: Decimal | None,
        allotment: date | None,
        source_nav: date | None,
        target_allotment: date | None,
    ) -> list[tuple[str, Decimal, Decimal, str | None]] | None:
        """Return [(posting_date_iso, cash_delta, units_delta, scheme)] or None if unpriceable."""
        if txn_type == "CONTRIBUTION":
            assert amount is not None
            return [(txn_type, amount, Decimal("0"), None)]
        if txn_type == "WITHDRAWAL":
            assert amount is not None
            return [(txn_type, -amount, Decimal("0"), None)]
        if txn_type == "PURCHASE":
            assert amount is not None and scheme is not None and allotment is not None
            price = self._nav_price(cur, scheme, allotment)
            if price is None:
                return None
            units_q = purchase_units(amount, price)
            actual = purchase_actual_cash(units_q, price)
            if units_q <= 0:
                return None
            return [("PURCHASE", -actual, units_q, scheme)]
        if txn_type == "REDEMPTION":
            assert units is not None and scheme is not None and allotment is not None
            price = self._nav_price(cur, scheme, allotment)
            if price is None:
                return None
            proceeds = redemption_proceeds(units, price)
            return [("REDEMPTION", proceeds, -units, scheme)]
        if txn_type == "SIP_INSTALMENT":
            assert amount is not None and scheme is not None and allotment is not None
            price = self._nav_price(cur, scheme, allotment)
            if price is None:
                return None
            units_q = purchase_units(amount, price)
            actual = purchase_actual_cash(units_q, price)
            if units_q <= 0:
                return None
            # The external contribution is posted by the caller on effective_date;
            # the purchase leg is posted on allotment_date.
            return [("SIP_PURCHASE", -actual, units_q, scheme)]
        if txn_type == "SWITCH":
            assert units is not None and source is not None and target is not None
            assert source_nav is not None and target_allotment is not None
            source_price = self._nav_price(cur, source, source_nav)
            target_price = self._nav_price(cur, target, target_allotment)
            if source_price is None or target_price is None:
                return None
            derived = switch_derived(units, source_price, target_price)
            proceeds = derived.proceeds
            assert proceeds is not None and derived.units is not None and derived.residual is not None
            return [
                ("SWITCH_REDEMPTION", proceeds, -units, source),
                ("SWITCH_PURCHASE", -derived.actual_cash, derived.units, target),
            ]
        return None

    # ---------------------------------------------------------- ingestion

    def ingest_m2_output(
        self,
        investors_path: str | Path,
        accounts_path: str | Path,
        transactions_path: str | Path,
    ) -> IngestReport:
        investors = json.loads(Path(investors_path).read_text(encoding="utf-8"))
        accounts = json.loads(Path(accounts_path).read_text(encoding="utf-8"))
        transactions = json.loads(Path(transactions_path).read_text(encoding="utf-8"))

        # Validate the whole batch before touching the database, so a rejected
        # row cannot leave a partially ingested dataset behind.
        for txn in transactions:
            if txn["txn_type"] not in _TXN_TYPES:
                raise ValueError(f"Unapproved transaction type {txn['txn_type']!r} in M2 output")
            for field_name in ("amount_instructed", "units_instructed"):
                if txn.get(field_name) is not None and Decimal(str(txn[field_name])) <= 0:
                    raise ValueError(f"Non-positive {field_name} in {txn['txn_group_id']}")

        with self._connect() as conn:
            with conn.cursor() as cur:
                # Reference data is small; executemany is already efficient.
                cur.executemany(
                    "INSERT INTO core.investor (investor_id, synthetic_ref, display_name, data_class, synthetic_label)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    [
                        (inv["investor_id"], inv["synthetic_ref"], inv["display_name"], inv["data_class"], inv["synthetic_label"])
                        for inv in investors
                    ],
                )
                cur.executemany(
                    "INSERT INTO core.account (account_id, synthetic_ref, investor_id, display_name, account_status, currency, opened_date, closed_date, data_class, synthetic_label)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    [
                        (
                            acc["account_id"], acc["synthetic_ref"], acc["investor_id"], acc["display_name"],
                            acc["account_status"], acc["currency"], acc["opened_date"], acc["closed_date"],
                            acc["data_class"], acc["synthetic_label"],
                        )
                        for acc in accounts
                    ],
                )

                # Skip already-ingested groups with one query rather than one
                # query per transaction (idempotent re-ingestion).
                all_group_ids = [txn["txn_group_id"] for txn in transactions]
                cur.execute(
                    "SELECT txn_group_id FROM core.txn_business WHERE txn_group_id = ANY(%s)",
                    (all_group_ids,),
                )
                existing = {row[0] for row in cur.fetchall()}
                new_txns = [txn for txn in transactions if txn["txn_group_id"] not in existing]
                skipped = len(transactions) - len(new_txns)

                business_rows: list[tuple] = []
                revision_rows: list[tuple] = []
                for txn in new_txns:
                    business_rows.append(
                        (txn["txn_group_id"], txn["account_id"], txn["investor_id"], txn["data_class"], txn["synthetic_label"])
                    )
                    recorded_at = self._as_utc(datetime.fromisoformat(str(txn["recorded_at"]).replace("Z", "+00:00")))
                    date.fromisoformat(str(txn["effective_date"]))
                    allotment_raw = txn.get("allotment_date")
                    allotment = date.fromisoformat(str(allotment_raw)) if allotment_raw else None
                    # SWITCH legs share the single M2 allotment date (= effective_date in M2 output).
                    source_nav_date = allotment if txn["txn_type"] == "SWITCH" else None
                    revision_rows.append(
                        (
                            txn["txn_group_id"], txn["txn_type"], txn["instruction_date"], txn["effective_date"],
                            allotment, source_nav_date, source_nav_date,
                            txn["posting_sequence"], txn.get("scheme_code"), txn.get("source_scheme_code"),
                            txn.get("target_scheme_code"), txn.get("amount_instructed"), txn.get("units_instructed"),
                            recorded_at, txn["data_class"], txn["synthetic_label"],
                        )
                    )

                if business_rows:
                    cur.executemany(
                        "INSERT INTO core.txn_business (txn_group_id, account_id, investor_id, data_class, synthetic_label)"
                        " VALUES (%s, %s, %s, %s, %s)",
                        business_rows,
                    )
                    cur.executemany(
                        "INSERT INTO core.txn_revision (txn_group_id, revision_no, revision_kind, revision_status, txn_type,"
                        " instruction_date, effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence,"
                        " scheme_code, source_scheme_code, target_scheme_code, amount_instructed, units_instructed, recorded_at,"
                        " data_class, synthetic_label)"
                        " VALUES (%s, 1, 'ORIGINAL', 'ACCEPTED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        revision_rows,
                    )
                    new_ids = [txn["txn_group_id"] for txn in new_txns]
                    # Both projections are derived set-based from the immutable
                    # revisions just written; this removes two round-trips per
                    # transaction while preserving the same rows.
                    cur.execute(
                        "INSERT INTO core.txn_revision_period (txn_revision_id, txn_group_id, system_period)"
                        " SELECT r.txn_revision_id, r.txn_group_id, tstzrange(r.recorded_at, 'infinity', '[)')"
                        " FROM core.txn_revision r"
                        " WHERE r.txn_group_id = ANY(%s) AND r.revision_no = 1"
                        " AND NOT EXISTS ("
                        "   SELECT 1 FROM core.txn_revision_period p WHERE p.txn_revision_id = r.txn_revision_id"
                        " )",
                        (new_ids,),
                    )
                    cur.execute(
                        "INSERT INTO core.txn_version_current (txn_group_id, latest_revision_id, revision_no, txn_type, instruction_date,"
                        " effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code,"
                        " source_scheme_code, target_scheme_code, amount_instructed, units_instructed, recorded_at, is_voided, data_class, synthetic_label)"
                        " SELECT DISTINCT ON (r.txn_group_id) r.txn_group_id, r.txn_revision_id, r.revision_no, r.txn_type,"
                        " r.instruction_date, r.effective_date, r.allotment_date, r.source_nav_date, r.target_allotment_date,"
                        " r.posting_sequence, r.scheme_code, r.source_scheme_code, r.target_scheme_code, r.amount_instructed,"
                        " r.units_instructed, r.recorded_at, (r.revision_status = 'VOIDED'), r.data_class, r.synthetic_label"
                        " FROM core.txn_revision r"
                        " WHERE r.txn_group_id = ANY(%s)"
                        " ORDER BY r.txn_group_id, r.revision_no DESC"
                        " ON CONFLICT (txn_group_id) DO NOTHING",
                        (new_ids,),
                    )
                created = len(new_txns)
            conn.commit()
        return IngestReport(
            investors_upserted=len(investors),
            accounts_upserted=len(accounts),
            transactions_created=created,
            transactions_skipped=skipped,
            dataset_hash="",
        )

    # ---------------------------------------------------------- queries

    def get_as_of(self, known_as_of: datetime) -> list[VisibleRevision]:
        """Visible revisions at knowledge time K (VOIDED excluded)."""
        known_as_of = self._as_utc(known_as_of)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT ON (r.txn_group_id) r.txn_group_id, r.txn_revision_id, r.revision_no, r.revision_kind, r.revision_status,"
                    " r.txn_type, b.account_id, r.instruction_date, r.effective_date, r.allotment_date, r.source_nav_date,"
                    " r.target_allotment_date, r.posting_sequence, r.scheme_code, r.source_scheme_code, r.target_scheme_code,"
                    " r.amount_instructed, r.units_instructed, r.recorded_at"
                    " FROM core.txn_revision r JOIN core.txn_business b ON b.txn_group_id = r.txn_group_id"
                    " WHERE r.recorded_at <= %s"
                    " ORDER BY r.txn_group_id, r.revision_no DESC",
                    (known_as_of,),
                )
                rows = cur.fetchall()
        return [
            VisibleRevision(
                txn_group_id=r[0], txn_revision_id=r[1], revision_no=r[2], revision_kind=r[3], revision_status=r[4],
                txn_type=r[5], account_id=r[6], instruction_date=r[7], effective_date=r[8], allotment_date=r[9],
                source_nav_date=r[10], target_allotment_date=r[11], posting_sequence=r[12], scheme_code=r[13],
                source_scheme_code=r[14], target_scheme_code=r[15],
                amount_instructed=Decimal(r[16]) if r[16] is not None else None,
                units_instructed=Decimal(r[17]) if r[17] is not None else None,
                recorded_at=r[18],
            )
            for r in rows if r[4] != "VOIDED"
        ]

    def get_current_projection(self) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT txn_group_id, latest_revision_id, revision_no, txn_type, effective_date, is_voided"
                    " FROM core.txn_version_current ORDER BY txn_group_id"
                )
                return [dict(zip(["txn_group_id", "latest_revision_id", "revision_no", "txn_type", "effective_date", "is_voided"], r)) for r in cur.fetchall()]

    def rebuild_all_projections(self) -> int:
        """Rebuild both projections from the immutable revision source."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Rebuild the temporal projection: each revision's interval is
                # [recorded_at, next recorded_at) within its business transaction.
                cur.execute("DELETE FROM core.txn_revision_period")
                cur.execute(
                    "INSERT INTO core.txn_revision_period (txn_revision_id, txn_group_id, system_period)"
                    " SELECT r.txn_revision_id, r.txn_group_id,"
                    " tstzrange(r.recorded_at, COALESCE(LEAD(r.recorded_at) OVER (PARTITION BY r.txn_group_id ORDER BY r.revision_no), 'infinity'), '[)')"
                    " FROM core.txn_revision r"
                )
                period_count = cur.rowcount
                cur.execute(
                    "INSERT INTO core.txn_version_current (txn_group_id, latest_revision_id, revision_no, txn_type, instruction_date,"
                    " effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code,"
                    " source_scheme_code, target_scheme_code, amount_instructed, units_instructed, recorded_at, is_voided, data_class, synthetic_label)"
                    " SELECT DISTINCT ON (r.txn_group_id) r.txn_group_id, r.txn_revision_id, r.revision_no, r.txn_type, r.instruction_date,"
                    " r.effective_date, r.allotment_date, r.source_nav_date, r.target_allotment_date, r.posting_sequence, r.scheme_code,"
                    " r.source_scheme_code, r.target_scheme_code, r.amount_instructed, r.units_instructed, r.recorded_at,"
                    " (r.revision_status = 'VOIDED'), r.data_class, r.synthetic_label"
                    " FROM core.txn_revision r ORDER BY r.txn_group_id, r.revision_no DESC"
                    " ON CONFLICT (txn_group_id) DO UPDATE SET latest_revision_id = EXCLUDED.latest_revision_id,"
                    " revision_no = EXCLUDED.revision_no, txn_type = EXCLUDED.txn_type, instruction_date = EXCLUDED.instruction_date,"
                    " effective_date = EXCLUDED.effective_date, allotment_date = EXCLUDED.allotment_date,"
                    " source_nav_date = EXCLUDED.source_nav_date, target_allotment_date = EXCLUDED.target_allotment_date,"
                    " posting_sequence = EXCLUDED.posting_sequence, scheme_code = EXCLUDED.scheme_code,"
                    " source_scheme_code = EXCLUDED.source_scheme_code, target_scheme_code = EXCLUDED.target_scheme_code,"
                    " amount_instructed = EXCLUDED.amount_instructed, units_instructed = EXCLUDED.units_instructed,"
                    " recorded_at = EXCLUDED.recorded_at, is_voided = EXCLUDED.is_voided,"
                    " data_class = EXCLUDED.data_class, synthetic_label = EXCLUDED.synthetic_label, updated_at = now()"
                )
                count = cur.rowcount
            conn.commit()
        return period_count + count

    # ---------------------------------------------------------- corrections

    def apply_correction(self, request: CorrectionRequest) -> CorrectionResult:
        recorded_at = self._as_utc(request.recorded_at)
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 1. Target + prior revision.
                cur.execute("SELECT account_id, investor_id FROM core.txn_business WHERE txn_group_id = %s", (request.txn_group_id,))
                business = cur.fetchone()
                if business is None:
                    return self._reject(request, recorded_at, "INVALID_REFERENCE", {"target": "txn_business not found"})
                cur.execute(
                    "SELECT txn_revision_id, revision_no, revision_status, txn_type, instruction_date, effective_date, allotment_date,"
                    " source_nav_date, target_allotment_date, posting_sequence, scheme_code, source_scheme_code, target_scheme_code,"
                    " amount_instructed, units_instructed, recorded_at FROM core.txn_revision WHERE txn_group_id = %s ORDER BY revision_no DESC LIMIT 1",
                    (request.txn_group_id,),
                )
                prior = cur.fetchone()
                if prior is None:
                    return self._reject(request, recorded_at, "INVALID_REFERENCE", {"target": "no prior revision"})
                prior_revision_id, prior_revision_no, prior_status, prior_type, prior_instruction, prior_effective, prior_allotment, \
                    prior_source_nav, prior_target_allotment, prior_seq, prior_scheme, prior_source_scheme, prior_target_scheme, \
                    prior_amount, prior_units, prior_recorded = prior
                if request.expected_prior_revision_id is not None and request.expected_prior_revision_id != prior_revision_id:
                    return self._reject(request, recorded_at, "INVALID_REFERENCE", {"expected_prior_revision_id": request.expected_prior_revision_id, "actual_prior_revision_id": prior_revision_id})
                if recorded_at <= prior_recorded:
                    return self._reject(request, recorded_at, "NON_MONOTONIC_RECORDED_AT", {"prior_recorded_at": prior_recorded.isoformat()})
                if request.correction_type not in _CORRECTION_TYPES:
                    return self._reject(request, recorded_at, "INVALID_CORRECTION_TYPE", {"correction_type": request.correction_type})
                if not request.reason_code or not request.actor_id:
                    return self._reject(request, recorded_at, "INVALID_REFERENCE", {"reason": "reason_code and actor_id are required"})

                # 2. Candidate instruction snapshot.
                if request.correction_type == "VOID":
                    cand = dict(instruction_date=prior_instruction, effective_date=prior_effective, allotment_date=prior_allotment,
                                source_nav_date=prior_source_nav, target_allotment_date=prior_target_allotment,
                                posting_sequence=prior_seq, scheme_code=prior_scheme, source_scheme_code=prior_source_scheme,
                                target_scheme_code=prior_target_scheme, amount_instructed=prior_amount, units_instructed=prior_units)
                else:
                    proposed_effective = request.proposed_effective_date or prior_effective
                    proposed_amount = request.proposed_amount if request.proposed_amount is not None else (
                        Decimal(prior_amount) if prior_amount is not None else None
                    )
                    proposed_units = request.proposed_units if request.proposed_units is not None else (
                        Decimal(prior_units) if prior_units is not None else None
                    )
                    if request.correction_type == "REVERSE_AND_REPLACE":
                        if request.proposed_scheme_code is None:
                            return self._reject(request, recorded_at, "INVALID_CORRECTION_TYPE", {"reason": "REVERSE_AND_REPLACE requires proposed_scheme_code"})
                        proposed_scheme = request.proposed_scheme_code
                        proposed_source = request.proposed_scheme_code if prior_type == "SWITCH" else prior_source_scheme
                        proposed_target = request.proposed_scheme_code if prior_type == "SWITCH" else prior_target_scheme
                    else:
                        proposed_scheme, proposed_source, proposed_target = prior_scheme, prior_source_scheme, prior_target_scheme
                    changed = (
                        proposed_effective != prior_effective
                        or proposed_amount != (Decimal(prior_amount) if prior_amount is not None else None)
                        or proposed_units != (Decimal(prior_units) if prior_units is not None else None)
                        or proposed_scheme != prior_scheme
                    )
                    if request.correction_type == "REPLACE" and not changed:
                        return self._reject(request, recorded_at, "INVALID_CORRECTION_TYPE", {"reason": "REPLACE changes no instruction field"})
                    resolved = self._allotment_dates(cur, prior_type, proposed_effective, proposed_scheme, proposed_source, proposed_target)
                    if resolved is None:
                        return self._reject(request, recorded_at, "MISSING_NAV_ALLOTMENT", {"effective_date": proposed_effective.isoformat(), "scheme_code": proposed_scheme})
                    new_allotment, new_source_nav, new_target_allotment = resolved
                    cand = dict(instruction_date=proposed_effective, effective_date=proposed_effective, allotment_date=new_allotment,
                                source_nav_date=new_source_nav, target_allotment_date=new_target_allotment,
                                posting_sequence=prior_seq, scheme_code=proposed_scheme, source_scheme_code=proposed_source,
                                target_scheme_code=proposed_target, amount_instructed=proposed_amount, units_instructed=proposed_units)

                # 3. Downstream validity (posting replay, Decimal only).
                if request.correction_type == "VOID":
                    pass
                else:
                    derived = self._derived_legs(
                        cur, prior_type, cand["scheme_code"], cand["source_scheme_code"], cand["target_scheme_code"],
                        cand["amount_instructed"], cand["units_instructed"], cand["allotment_date"],
                        cand["source_nav_date"], cand["target_allotment_date"],
                    )
                    if derived is None:
                        return self._reject(request, recorded_at, "MISSING_NAV_ALLOTMENT", {"reason": "derived pricing failed"})

                failure = self._replay_candidate(cur, business[0], request.txn_group_id, prior_type, cand, recorded_at, is_voided=(request.correction_type == "VOID"))
                if failure is not None:
                    return self._reject(request, recorded_at, failure[0], failure[1])

                # 4. Commit atomically: group + revision + period close + projection.
                group_id = f"SYN_GRPCORR-{request.txn_group_id}-{int(recorded_at.timestamp())}"
                cur.execute(
                    "INSERT INTO core.correction_group (correction_group_id, txn_group_id, correction_type, reason_code, reason_note, source_ref, actor_id, recorded_at, status)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'APPLIED')",
                    (group_id, request.txn_group_id, request.correction_type, request.reason_code, request.reason_note, request.source_ref, request.actor_id, recorded_at),
                )
                revision_no = prior_revision_no + 1
                revision_kind = request.correction_type
                revision_status = "VOIDED" if request.correction_type == "VOID" else "ACCEPTED"
                # Close the prior interval in the projection first so the new
                # [recorded_at, infinity) row cannot overlap it (GiST).
                cur.execute(
                    "UPDATE core.txn_revision_period SET system_period = tstzrange(%s, %s, '[)') WHERE txn_revision_id = %s",
                    (prior_recorded, recorded_at, prior_revision_id),
                )
                cur.execute(
                    "INSERT INTO core.txn_revision (txn_group_id, revision_no, correction_group_id, prev_revision_id, revision_kind, revision_status,"
                    " txn_type, instruction_date, effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence,"
                    " scheme_code, source_scheme_code, target_scheme_code, amount_instructed, units_instructed, recorded_at,"
                    " data_class, synthetic_label) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING txn_revision_id",
                    (request.txn_group_id, revision_no, group_id, prior_revision_id, revision_kind, revision_status,
                     prior_type, cand["instruction_date"], cand["effective_date"], cand["allotment_date"],
                     cand["source_nav_date"], cand["target_allotment_date"], cand["posting_sequence"],
                     cand["scheme_code"], cand["source_scheme_code"], cand["target_scheme_code"],
                     cand["amount_instructed"], cand["units_instructed"], recorded_at, "synthetic_accounts_real_nav", "synthetic_accounts_real_nav"),
                )
                new_revision_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO core.txn_revision_period (txn_revision_id, txn_group_id, system_period)"
                    " VALUES (%s, %s, tstzrange(%s, 'infinity', '[)'))",
                    (new_revision_id, request.txn_group_id, recorded_at),
                )
                cur.execute("UPDATE core.correction_group SET applied_revision_id = %s WHERE correction_group_id = %s",
                            (new_revision_id, group_id))
                cur.execute(
                    "INSERT INTO core.txn_version_current (txn_group_id, latest_revision_id, revision_no, txn_type, instruction_date,"
                    " effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code, source_scheme_code,"
                    " target_scheme_code, amount_instructed, units_instructed, recorded_at, is_voided)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (txn_group_id) DO UPDATE SET latest_revision_id = EXCLUDED.latest_revision_id, revision_no = EXCLUDED.revision_no,"
                    " txn_type = EXCLUDED.txn_type, instruction_date = EXCLUDED.instruction_date, effective_date = EXCLUDED.effective_date,"
                    " allotment_date = EXCLUDED.allotment_date, source_nav_date = EXCLUDED.source_nav_date,"
                    " target_allotment_date = EXCLUDED.target_allotment_date, posting_sequence = EXCLUDED.posting_sequence,"
                    " scheme_code = EXCLUDED.scheme_code, source_scheme_code = EXCLUDED.source_scheme_code,"
                    " target_scheme_code = EXCLUDED.target_scheme_code, amount_instructed = EXCLUDED.amount_instructed,"
                    " units_instructed = EXCLUDED.units_instructed, recorded_at = EXCLUDED.recorded_at, is_voided = EXCLUDED.is_voided, updated_at = now()",
                    (request.txn_group_id, new_revision_id, revision_no, prior_type, cand["instruction_date"], cand["effective_date"],
                     cand["allotment_date"], cand["source_nav_date"], cand["target_allotment_date"], cand["posting_sequence"],
                     cand["scheme_code"], cand["source_scheme_code"], cand["target_scheme_code"],
                     cand["amount_instructed"], cand["units_instructed"], recorded_at, revision_status == "VOIDED"),
                )
                conn.commit()
                return CorrectionResult(applied=True, reason_code="APPLIED", reason="Correction applied atomically.",
                                        correction_group_id=group_id, revision_id=new_revision_id, revision_no=revision_no)

    def _replay_candidate(self, cur, account_id: int, candidate_txn: str, candidate_type: str, candidate: dict, recorded_at: datetime, is_voided: bool = False) -> tuple[str, dict] | None:
        """Replay posting legs for the account with the candidate replacing the current revision."""
        cur.execute(
            "SELECT c.txn_group_id, c.txn_type, c.effective_date, c.allotment_date, c.source_nav_date, c.target_allotment_date,"
            " c.posting_sequence, c.scheme_code, c.source_scheme_code, c.target_scheme_code, c.amount_instructed, c.units_instructed, c.is_voided"
            " FROM core.txn_version_current c JOIN core.txn_business b ON b.txn_group_id = c.txn_group_id WHERE b.account_id = %s",
            (account_id,),
        )
        rows = [dict(zip(["txn_group_id", "txn_type", "effective_date", "allotment_date", "source_nav_date", "target_allotment_date", "posting_sequence", "scheme_code", "source_scheme_code", "target_scheme_code", "amount_instructed", "units_instructed", "is_voided"], r)) for r in cur.fetchall()]
        # Replace the candidate's current row with the proposed instruction.
        replaced = [
            dict(
                txn_group_id=candidate_txn, txn_type=candidate_type, effective_date=candidate["effective_date"],
                allotment_date=candidate["allotment_date"], source_nav_date=candidate["source_nav_date"],
                target_allotment_date=candidate["target_allotment_date"], posting_sequence=candidate["posting_sequence"],
                scheme_code=candidate["scheme_code"], source_scheme_code=candidate["source_scheme_code"],
                target_scheme_code=candidate["target_scheme_code"], amount_instructed=candidate["amount_instructed"],
                units_instructed=candidate["units_instructed"], is_voided=is_voided,
            )
            if row["txn_group_id"] == candidate_txn else row
            for row in rows
        ]
        legs: list[tuple[date, int, str, Decimal, Decimal, str | None]] = []
        for row in replaced:
            if row["is_voided"]:
                continue
            txn_type = row["txn_type"]
            effective = row["effective_date"]
            seq = int(row["posting_sequence"])
            amount = Decimal(row["amount_instructed"]) if row["amount_instructed"] is not None else None
            units = Decimal(row["units_instructed"]) if row["units_instructed"] is not None else None
            scheme, source, target = row["scheme_code"], row["source_scheme_code"], row["target_scheme_code"]
            allotment, source_nav, target_allotment = row["allotment_date"], row["source_nav_date"], row["target_allotment_date"]
            derived = self._derived_legs(cur, row["txn_type"], scheme, source, target, amount, units, allotment, source_nav, target_allotment)
            if txn_type == "CONTRIBUTION":
                legs.append((effective, seq, row["txn_group_id"], amount or Decimal("0"), Decimal("0"), None))
            elif txn_type == "WITHDRAWAL":
                legs.append((effective, seq, row["txn_group_id"], -(amount or Decimal("0")), Decimal("0"), None))
            elif derived is None:
                return ("MISSING_NAV_ALLOTMENT", {"txn_group_id": row["txn_group_id"]})
            elif txn_type == "PURCHASE":
                for kind, cash_delta, units_delta, code in derived:
                    legs.append((allotment or effective, seq, row["txn_group_id"], cash_delta, units_delta, code))
            elif txn_type == "REDEMPTION":
                legs.append((allotment or effective, seq, row["txn_group_id"], derived[0][1], derived[0][2], derived[0][3]))
            elif txn_type == "SIP_INSTALMENT":
                legs.append((effective, seq, row["txn_group_id"], amount or Decimal("0"), Decimal("0"), None))
                for kind, cash_delta, units_delta, code in derived:
                    legs.append((allotment or effective, seq, row["txn_group_id"], cash_delta, units_delta, code))
            elif txn_type == "SWITCH":
                legs.append((source_nav or effective, seq, row["txn_group_id"], derived[0][1], derived[0][2], source))
                legs.append((target_allotment or allotment or effective, seq, row["txn_group_id"], derived[1][1], derived[1][2], target))
        legs.sort(key=lambda item: (item[0], item[1], item[2]))
        cash = Decimal("0")
        units_map: dict[str, Decimal] = {}
        for posting_date, seq, txn_group_id, cash_delta, units_delta, code in legs:
            cash += cash_delta
            if code is not None:
                units_map[code] = units_map.get(code, Decimal("0")) + units_delta
                if units_map[code] < 0:
                    return ("NEGATIVE_UNITS_DOWNSTREAM", {"txn_group_id": txn_group_id, "scheme_code": code, "posting_date": posting_date.isoformat()})
            if cash < 0:
                return ("INSUFFICIENT_CASH_DOWNSTREAM", {"txn_group_id": txn_group_id, "posting_date": posting_date.isoformat()})
        return None

    def _reject(self, request: CorrectionRequest, recorded_at: datetime, reason_code: str, details: dict) -> CorrectionResult:
        group_id = f"SYN_GRPCORR-{request.txn_group_id}-{int(recorded_at.timestamp())}"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO core.correction_rejection (correction_group_id, txn_group_id, expected_prior_revision_id, correction_type,"
                    " reason_code, attempted_recorded_at, actor_id, details) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (group_id, request.txn_group_id, request.expected_prior_revision_id, request.correction_type, reason_code, recorded_at, request.actor_id, json.dumps(details)),
                )
            conn.commit()
        return CorrectionResult(applied=False, reason_code=reason_code, reason=details.get("reason", reason_code), correction_group_id=group_id)
