"""Snapshot persistence and operations (M6, METHODOLOGY §10)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg

from bitemporal_ledger.performance.service import PerformanceService
from bitemporal_ledger.reporting.canonical import canonical_payload_hash
from bitemporal_ledger.valuation.service import ValuationService

__all__ = ["SnapshotService", "build_payload"]

ENGINE_VERSION = "performance-1.0.0"
SCHEME_MAPPING_VERSION = "amfi_code_v1"
ROUNDING_POLICY = "units_3dp_round_down__amounts_2dp_round_half_up__nav_as_published"


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _nav_snapshot_checksum(conn, snapshot_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT source_file_sha256 FROM core.nav_snapshot WHERE nav_snapshot_id = %s", (snapshot_id,))
        row = cur.fetchone()
        return row[0] if row else "unknown"


def _migrations_hash(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT migration_name, checksum FROM core.migration ORDER BY migration_id")
        rows = cur.fetchall()
    joined = "".join(f"{name}:{checksum}" for name, checksum in rows)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_payload(
    *,
    account_id: int,
    period_start: date,
    period_end: date,
    known_as_of: datetime,
    nav_snapshot_id: int,
    valuation: ValuationService,
    performance: PerformanceService,
    config_hash: str = "generator-1.0.0",
    generated_at: datetime | None = None,
) -> dict:
    """Build the canonical report payload for one account/period/K."""
    known_as_of = known_as_of if known_as_of.tzinfo else known_as_of.replace(tzinfo=timezone.utc)
    generated = generated_at or known_as_of
    perf = performance.compute(account_id, period_start, period_end, known_as_of)
    holdings = [
        {
            "scheme_code": h.scheme_code,
            "units": _decimal(h.units),
            "nav": _decimal(h.price),
            "nav_date": h.price_date.isoformat(),
            "stale_nav": h.is_stale,
            "stale_days": h.stale_days,
            "value": _decimal(h.value),
        }
        for h in perf_start_holdings(valuation, account_id, period_end, known_as_of)
    ]
    payload = {
        "account_id": account_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "known_as_of_utc": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_utc": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calculation_engine_version": ENGINE_VERSION,
        "nav_snapshot_id": nav_snapshot_id,
        "scheme_mapping_version": SCHEME_MAPPING_VERSION,
        "rounding_policy": ROUNDING_POLICY,
        "config_hash": config_hash,
        "cash": _decimal(perf.start_value and perf.end_value is not None and ValuationService(valuation.dsn, nav_snapshot_id).value(account_id, period_end, known_as_of).cash or Decimal("0")),
        "holdings": holdings,
        "total_value": _decimal(perf.end_value),
        "external_flows": [
            {"date": f.flow_date.isoformat(), "amount": _decimal(f.amount)} for f in perf.flows
        ],
        "performance": {
            "twr": _decimal(perf.twr),
            "modified_dietz": _decimal(perf.modified_dietz),
            "xirr_status": perf.xirr["status"],
            "xirr_rate": _decimal(perf.xirr["rate"]),
        },
        "data_class": "synthetic_accounts_real_nav",
        "synthetic_label": "synthetic_accounts_real_nav",
    }
    return payload


def perf_start_holdings(valuation: ValuationService, account_id: int, valid_date: date, known_as_of: datetime):
    return valuation.value(account_id, valid_date, known_as_of).holdings


class SnapshotService:
    def __init__(self, dsn: str, nav_snapshot_id: int, valuation: ValuationService, performance: PerformanceService) -> None:
        self.dsn = dsn
        self.nav_snapshot_id = nav_snapshot_id
        self.valuation = valuation
        self.performance = performance

    def _metadata(self, conn, snapshot_id: int | None) -> dict:
        if snapshot_id is None:
            return {
                "calculation_engine_version": ENGINE_VERSION,
                "nav_snapshot_id": self.nav_snapshot_id,
                "nav_snapshot_checksum": _nav_snapshot_checksum(conn, self.nav_snapshot_id),
                "scheme_mapping_version": SCHEME_MAPPING_VERSION,
                "config_hash": "generator-1.0.0",
                "schema_migrations_hash": _migrations_hash(conn),
                "git_commit_sha": os.environ.get("GIT_COMMIT_SHA", "unrecorded-local"),
                "git_dirty": True,
                "rounding_policy": ROUNDING_POLICY,
            }
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM core.report_snapshot WHERE report_snapshot_id = %s", (snapshot_id,))
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"Snapshot {snapshot_id} not found")
            stored = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return {
            "calculation_engine_version": stored["calculation_engine_version"],
            "nav_snapshot_id": stored["nav_snapshot_id"],
            "nav_snapshot_checksum": None,
            "scheme_mapping_version": stored["scheme_mapping_version"],
            "config_hash": stored["config_hash"],
            "schema_migrations_hash": _migrations_hash(conn),
            "git_commit_sha": os.environ.get("GIT_COMMIT_SHA", "unrecorded-local"),
            "git_dirty": True,
            "rounding_policy": stored["rounding_policy"],
        }

    def generate(
        self,
        account_id: int,
        period_start: date,
        period_end: date,
        known_as_of: datetime,
        *,
        generated_at: datetime | None = None,
    ) -> int:
        known_as_of = known_as_of if known_as_of.tzinfo else known_as_of.replace(tzinfo=timezone.utc)
        generated_at = generated_at or known_as_of
        payload = build_payload(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            known_as_of=known_as_of,
            nav_snapshot_id=self.nav_snapshot_id,
            valuation=self.valuation,
            performance=self.performance,
            generated_at=generated_at,
        )
        payload_hash = canonical_payload_hash(payload)
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO core.report_snapshot (account_id, period_start, period_end, known_as_of, generated_at,"
                    " calculation_engine_version, nav_snapshot_id, payload, payload_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING report_snapshot_id",
                    (account_id, period_start, period_end, known_as_of, generated_at, ENGINE_VERSION, self.nav_snapshot_id, json.dumps(payload), payload_hash),
                )
                snapshot_id = cur.fetchone()[0]
            conn.commit()
        return snapshot_id

    def retrieve(self, snapshot_id: int) -> dict:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM core.report_snapshot WHERE report_snapshot_id = %s", (snapshot_id,))
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Snapshot {snapshot_id} not found")
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]

    def replay(self, snapshot_id: int) -> str:
        """Recompute from stored metadata and compare hashes (never from the stored payload)."""
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id, period_start, period_end, known_as_of, generated_at, payload, payload_sha256"
                    " FROM core.report_snapshot WHERE report_snapshot_id = %s",
                    (snapshot_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"Snapshot {snapshot_id} not found")
        account_id, period_start, period_end, known_as_of, generated_at, stored_payload, expected_hash = row
        if isinstance(stored_payload, str):
            stored_payload = json.loads(stored_payload)
        recomputed = build_payload(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            known_as_of=known_as_of,
            nav_snapshot_id=self.nav_snapshot_id,
            valuation=self.valuation,
            performance=self.performance,
            generated_at=generated_at,
        )
        actual_hash = canonical_payload_hash(recomputed)
        if stored_payload["calculation_engine_version"] != ENGINE_VERSION:
            return "ENGINE_VERSION_MISMATCH"
        if stored_payload["nav_snapshot_id"] != self.nav_snapshot_id:
            return "NAV_SNAPSHOT_MISMATCH"
        return "REPLAY_EXACT" if actual_hash == expected_hash else "PAYLOAD_MISMATCH"

    def restatement(self, snapshot_id: int, restated_known_as_of: datetime) -> dict:
        """Recompute the report at a later K and attribute the delta (never overwrites)."""
        stored = self.retrieve(snapshot_id)
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id, period_start, period_end FROM core.report_snapshot WHERE report_snapshot_id = %s",
                    (snapshot_id,),
                )
                account_id, period_start, period_end = cur.fetchone()
        restated = build_payload(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            known_as_of=restated_known_as_of,
            nav_snapshot_id=self.nav_snapshot_id,
            valuation=self.valuation,
            performance=self.performance,
        )
        deltas = {}
        for key in ("total_value", "cash", "holdings", "performance"):
            if stored.get(key) != restated.get(key):
                deltas[key] = {"original": stored.get(key), "restated": restated.get(key)}
        return {
            "status": "RESTATEMENT_GENERATED" if deltas else "NO_CHANGE",
            "snapshot_id": snapshot_id,
            "restated_known_as_of": restated_known_as_of.isoformat(),
            "deltas": deltas,
            "payload": restated,
            "payload_sha256": canonical_payload_hash(restated),
        }
