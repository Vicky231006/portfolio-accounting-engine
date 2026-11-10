"""K1/K2 performance replay over the ledger (M5, METHODOLOGY §9)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
import pytest

from bitemporal_ledger.ledger.models import CorrectionRequest
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.performance.service import PerformanceService
from bitemporal_ledger.valuation.service import ValuationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; M5 replay test requires PostgreSQL 16",
)


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture()
def pair():
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT nav_snapshot_id FROM core.nav_snapshot ORDER BY nav_snapshot_id LIMIT 1")
        snapshot_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.nav_observation (nav_snapshot_id, amfi_scheme_code, nav_date, nav, option_type, source_file_sha256)"
            " VALUES (%s, '100001', '2026-01-10', 50.000000, 'GROWTH', 'm5-seed') ON CONFLICT DO NOTHING",
            (snapshot_id,),
        )
        cur.execute(
            "INSERT INTO core.nav_observation (nav_snapshot_id, amfi_scheme_code, nav_date, nav, option_type, source_file_sha256)"
            " VALUES (%s, '100001', '2026-01-31', 52.000000, 'GROWTH', 'm5-seed') ON CONFLICT DO NOTHING",
            (snapshot_id,),
        )
        cur.execute("TRUNCATE core.correction_rejection, core.txn_revision_period, core.txn_version_current, core.txn_revision, core.correction_group, core.txn_business RESTART IDENTITY CASCADE")
        cur.execute("DELETE FROM core.account WHERE synthetic_ref LIKE 'SYN_ACC-M5-%'")
        cur.execute("DELETE FROM core.investor WHERE synthetic_ref LIKE 'SYN_INV-M5-%'")
        cur.execute(
            "INSERT INTO core.investor (investor_id, synthetic_ref, display_name) VALUES (930001, 'SYN_INV-M5-0001', 'Synthetic Investor M5 01') ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.account (account_id, synthetic_ref, investor_id, display_name, account_status, currency, opened_date)"
            " VALUES (930001, 'SYN_ACC-M5-0001', 930001, 'Synthetic Account M5 01', 'ACTIVE', 'INR', '2026-01-01') ON CONFLICT DO NOTHING"
        )
    conn.commit()
    conn.close()
    ledger = LedgerService(dsn, snapshot_id)
    valuation = ValuationService(dsn, snapshot_id, ledger)
    yield ledger, valuation
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE core.correction_rejection, core.txn_revision_period, core.txn_version_current, core.txn_revision, core.correction_group, core.txn_business, core.account, core.investor RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


def _create_txn(ledger: LedgerService, txn_group_id: str, txn_type: str, effective: date, recorded: datetime, *, amount=None, scheme=None):
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO core.txn_business (txn_group_id, account_id, investor_id, data_class, synthetic_label)"
                " VALUES (%s, 930001, 930001, 'synthetic_accounts_real_nav', 'synthetic_accounts_real_nav') ON CONFLICT DO NOTHING",
                (txn_group_id,),
            )
            allotment = ledger._first_nav_on_or_after(cur, scheme, effective) if scheme else None
            cur.execute(
                "INSERT INTO core.txn_revision (txn_group_id, revision_no, revision_kind, revision_status, txn_type, instruction_date,"
                " effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code, source_scheme_code,"
                " target_scheme_code, amount_instructed, units_instructed, recorded_at) VALUES (%s, 1, 'ORIGINAL', 'ACCEPTED', %s, %s, %s, %s, NULL, NULL, 10, %s, NULL, NULL, %s, NULL, %s) RETURNING txn_revision_id",
                (txn_group_id, txn_type, effective, effective, allotment, scheme, amount, recorded),
            )
            revision_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO core.txn_revision_period (txn_revision_id, txn_group_id, system_period)"
                " VALUES (%s, %s, tstzrange(%s, 'infinity', '[)'))",
                (revision_id, txn_group_id, recorded),
            )
            cur.execute(
                "INSERT INTO core.txn_version_current (txn_group_id, latest_revision_id, revision_no, txn_type, instruction_date, effective_date,"
                " allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code, source_scheme_code, target_scheme_code,"
                " amount_instructed, units_instructed, recorded_at, is_voided)"
                " VALUES (%s, %s, 1, %s, %s, %s, %s, NULL, NULL, 10, %s, NULL, NULL, %s, NULL, %s, FALSE)",
                (txn_group_id, revision_id, txn_type, effective, effective, allotment, scheme, amount, recorded),
            )
        conn.commit()
    return revision_id


def test_k1_k2_performance_replay(pair) -> None:
    ledger, valuation = pair
    # METHODOLOGY §9: opening contribution + 10,000 purchase on 2026-01-10,
    # NAV 52 on 2026-01-31. But the opening contribution posts 2026-01-01 and
    # the account is at zero before, so V_S (day before) is 0.
    _create_txn(ledger, "M5-T1", "CONTRIBUTION", date(2026, 1, 1), _utc(2026, 1, 1, 18), amount=Decimal("100000.00"))
    _create_txn(ledger, "M5-T2", "PURCHASE", date(2026, 1, 10), _utc(2026, 1, 10, 18), amount=Decimal("10000.00"), scheme="100001")
    service = PerformanceService(valuation)
    k1 = service.compute(930001, date(2026, 1, 1), date(2026, 1, 31), _utc(2026, 1, 31, 9))
    ledger.apply_correction(
        CorrectionRequest(
            txn_group_id="M5-T2", correction_type="REPLACE", reason_code="TEST", reason_note="test",
            source_ref="synthetic_intent", actor_id="SYN_OP-001", recorded_at=_utc(2026, 2, 5, 11),
            proposed_amount=Decimal("12000.00"),
        )
    )
    k2 = service.compute(930001, date(2026, 1, 1), date(2026, 1, 31), _utc(2026, 2, 6))
    assert k1.start_value == Decimal("0")
    assert k1.end_value == Decimal("100400.00")
    assert k1.twr.quantize(Decimal("0.0001")) == Decimal("0.0040")
    assert k1.xirr["status"] == "SUCCESS"
    assert abs(k1.xirr["rate"] - Decimal("0.048125")) < Decimal("0.000001")
    assert k2.end_value == Decimal("100480.00")
    assert k2.twr.quantize(Decimal("0.0001")) == Decimal("0.0048")
    assert k2.xirr["status"] == "SUCCESS"
    assert abs(k2.xirr["rate"] - Decimal("0.0580006")) < Decimal("0.0001")
