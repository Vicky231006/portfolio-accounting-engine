"""M6 snapshot replay / restatement / comparator tests (FR-B8/B9/B14)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
import pytest

from bitemporal_ledger.ledger.models import CorrectionRequest
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.performance.service import PerformanceService
from bitemporal_ledger.reporting.comparator import OverwriteComparator
from bitemporal_ledger.reporting.snapshot import SnapshotService
from bitemporal_ledger.valuation.service import ValuationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; M6 tests require PostgreSQL 16",
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
            " VALUES (%s, '100001', '2026-01-10', 50.000000, 'GROWTH', 'm6-seed') ON CONFLICT DO NOTHING",
            (snapshot_id,),
        )
        cur.execute(
            "INSERT INTO core.nav_observation (nav_snapshot_id, amfi_scheme_code, nav_date, nav, option_type, source_file_sha256)"
            " VALUES (%s, '100001', '2026-01-31', 52.000000, 'GROWTH', 'm6-seed') ON CONFLICT DO NOTHING",
            (snapshot_id,),
        )
        cur.execute("TRUNCATE core.report_snapshot, core.correction_rejection, core.txn_revision_period, core.txn_version_current, core.txn_revision, core.correction_group, core.txn_business RESTART IDENTITY CASCADE")
        cur.execute("DELETE FROM core.account WHERE synthetic_ref LIKE 'SYN_ACC-M6-%'")
        cur.execute("DELETE FROM core.investor WHERE synthetic_ref LIKE 'SYN_INV-M6-%'")
        cur.execute(
            "INSERT INTO core.investor (investor_id, synthetic_ref, display_name) VALUES (940001, 'SYN_INV-M6-0001', 'Synthetic Investor M6 01') ON CONFLICT DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.account (account_id, synthetic_ref, investor_id, display_name, account_status, currency, opened_date)"
            " VALUES (940001, 'SYN_ACC-M6-0001', 940001, 'Synthetic Account M6 01', 'ACTIVE', 'INR', '2026-01-01') ON CONFLICT DO NOTHING"
        )
    conn.commit()
    conn.close()
    ledger = LedgerService(dsn, snapshot_id)
    valuation = ValuationService(dsn, snapshot_id, ledger)
    performance = PerformanceService(valuation)
    yield ledger, validation_fix(valuation, performance, dsn, snapshot_id)
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE core.report_snapshot, core.correction_rejection, core.txn_revision_period, core.txn_version_current, core.txn_revision, core.correction_group, core.txn_business, core.account, core.investor RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


def validation_fix(valuation, performance, dsn, snapshot_id):
    return SnapshotService(dsn, snapshot_id, valuation, performance)


def _create_txn(ledger: LedgerService, txn_group_id: str, txn_type: str, effective: date, recorded: datetime, *, amount=None, scheme=None):
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO core.txn_business (txn_group_id, account_id, investor_id, data_class, synthetic_label)"
                " VALUES (%s, 940001, 940001, 'synthetic_accounts_real_nav', 'synthetic_accounts_real_nav') ON CONFLICT DO NOTHING",
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


def test_replay_is_original_and_restatement_separate(pair) -> None:
    ledger, snapshots = pair
    _create_txn(ledger, "M6-T1", "CONTRIBUTION", date(2026, 1, 1), _utc(2026, 1, 1, 18), amount=Decimal("100000.00"))
    _create_txn(ledger, "M6-T2", "PURCHASE", date(2026, 1, 10), _utc(2026, 1, 10, 18), amount=Decimal("10000.00"), scheme="100001")
    snapshot_id = snapshots.generate(940001, date(2026, 1, 1), date(2026, 1, 31), _utc(2026, 1, 31, 9))
    ledger.apply_correction(
        CorrectionRequest(
            txn_group_id="M6-T2", correction_type="REPLACE", reason_code="AMOUNT_CORRECTION", reason_note="test",
            source_ref="synthetic_intent", actor_id="SYN_OP-001", recorded_at=_utc(2026, 2, 5, 11),
            proposed_amount=Decimal("12000.00"),
        )
    )
    assert snapshots.replay(snapshot_id) == "REPLAY_EXACT"
    archived = snapshots.retrieve(snapshot_id)
    assert archived["total_value"] == "100400.00"
    restated = snapshots.restatement(snapshot_id, _utc(2026, 2, 6))
    assert restated["status"] == "RESTATEMENT_GENERATED"
    assert restated["payload"]["total_value"] == "100480.00"
    assert "total_value" in restated["deltas"]
    # The original is unchanged after restatement.
    assert snapshots.retrieve(snapshot_id)["total_value"] == "100400.00"


def test_comparator_reports_lost_history(pair) -> None:
    ledger, snapshots = pair
    _create_txn(ledger, "M6-T1", "CONTRIBUTION", date(2026, 1, 1), _utc(2026, 1, 1, 18), amount=Decimal("100000.00"))
    _create_txn(ledger, "M6-T2", "PURCHASE", date(2026, 1, 10), _utc(2026, 1, 10, 18), amount=Decimal("10000.00"), scheme="100001")
    ledger.apply_correction(
        CorrectionRequest(
            txn_group_id="M6-T2", correction_type="REPLACE", reason_code="TEST", reason_note="test",
            source_ref="synthetic_intent", actor_id="SYN_OP-001", recorded_at=_utc(2026, 2, 5, 11),
            proposed_amount=Decimal("12000.00"),
        )
    )
    comparator = OverwriteComparator(snapshots.dsn, snapshots.nav_snapshot_id)
    count = comparator.ingest_current()
    assert count == 2
    report = comparator.compare_after_corrections(["M6-T1", "M6-T2"])
    assert report["reproducible"] == ["M6-T1"]
    assert report["unreproducible"] == ["M6-T2"]
    assert report["reproducible_count"] == 1 and report["total_count"] == 2
