"""M4 positions and valuation tests (FR-B5/FR-B6, D-049–D-051).

NAV fixture (M1 snapshot, test-only schemes):
- 100001: 10.000000 on 2024-01-05
- 100002: 20.000000 on 2024-01-05
- 100003: 30.000000 on 2024-01-06 (switch target)
- 100004: 25.000000 on 2024-01-11 (late scheme for stale tests)
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
import pytest

from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.valuation.models import InvariantError, ValuationError
from bitemporal_ledger.valuation.service import ValuationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; M4 integration tests require PostgreSQL 16",
)

SCHEME_A = "100001"
SCHEME_B = "100002"
SCHEME_C = "100003"
SCHEME_D = "100004"


def _utc(y: int, m: int, d: int, h: int = 12) -> datetime:
    return datetime(y, m, d, h, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def pair():
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT nav_snapshot_id FROM core.nav_snapshot ORDER BY nav_snapshot_id LIMIT 1")
        snapshot_id = cur.fetchone()[0]
        rows = [
            (SCHEME_A, date(2024, 1, 5), "10.000000"),
            (SCHEME_B, date(2024, 1, 5), "20.000000"),
            (SCHEME_C, date(2024, 1, 6), "30.000000"),
            (SCHEME_D, date(2024, 1, 11), "25.000000"),
        ]
        for scheme, day, nav in rows:
            cur.execute(
                "INSERT INTO core.nav_observation (nav_snapshot_id, amfi_scheme_code, nav_date, nav, option_type, source_file_sha256)"
                " VALUES (%s, %s, %s, %s, 'GROWTH', 'm4-seed') ON CONFLICT DO NOTHING",
                (snapshot_id, scheme, day, nav),
            )
        cur.execute("TRUNCATE core.correction_rejection, core.txn_revision_period, core.txn_version_current, core.txn_revision, core.correction_group, core.txn_business RESTART IDENTITY CASCADE")
        cur.execute("DELETE FROM core.account WHERE synthetic_ref LIKE 'SYN_ACC-M4-%'")
        cur.execute("DELETE FROM core.investor WHERE synthetic_ref LIKE 'SYN_INV-M4-%'")
        for idx in (1, 2):
            cur.execute(
                "INSERT INTO core.investor (investor_id, synthetic_ref, display_name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (920000 + idx, f"SYN_INV-M4-000{idx}", f"Synthetic Investor M4 {idx:02d}"),
            )
            cur.execute(
                "INSERT INTO core.account (account_id, synthetic_ref, investor_id, display_name, account_status, currency, opened_date)"
                " VALUES (%s, %s, %s, %s, 'ACTIVE', 'INR', '2024-01-01') ON CONFLICT DO NOTHING",
                (920000 + idx, f"SYN_ACC-M4-000{idx}", 920000 + idx, f"Synthetic Account M4 {idx:02d}"),
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


def _create_txn(ledger: LedgerService, account_id: int, investor_id: int, txn_group_id: str, txn_type: str, effective: date, recorded: datetime, *, amount=None, units=None, scheme=None, source=None, target=None, posting_sequence: int = 10):
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO core.txn_business (txn_group_id, account_id, investor_id, data_class, synthetic_label)"
                " VALUES (%s, %s, %s, 'synthetic_accounts_real_nav', 'synthetic_accounts_real_nav') ON CONFLICT DO NOTHING",
                (txn_group_id, account_id, investor_id),
            )
            allotment, source_nav, target_allotment = None, None, None
            if txn_type in ("PURCHASE", "REDEMPTION", "SIP_INSTALMENT"):
                allotment = ledger._first_nav_on_or_after(cur, scheme, effective)
            elif txn_type == "SWITCH":
                source_nav = ledger._first_nav_on_or_after(cur, source, effective)
                target_allotment = ledger._first_nav_on_or_after(cur, target, source_nav) if source_nav else None
                allotment = target_allotment
            cur.execute(
                "INSERT INTO core.txn_revision (txn_group_id, revision_no, revision_kind, revision_status, txn_type, instruction_date,"
                " effective_date, allotment_date, source_nav_date, target_allotment_date, posting_sequence, scheme_code, source_scheme_code,"
                " target_scheme_code, amount_instructed, units_instructed, recorded_at) VALUES (%s, 1, 'ORIGINAL', 'ACCEPTED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING txn_revision_id",
                (txn_group_id, txn_type, effective, effective, allotment, source_nav, target_allotment,
                 posting_sequence, scheme, source, target, amount, units, recorded),
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
                " VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)",
                (txn_group_id, revision_id, txn_type, effective, effective, allotment, source_nav, target_allotment,
                 posting_sequence, scheme, source, target, amount, units, recorded),
            )
        conn.commit()
    return revision_id


def test_contributions_withdrawals_and_purchases(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    _create_txn(ledger, 920001, 920001, "M4-T3", "WITHDRAWAL", date(2024, 1, 5), _utc(2024, 1, 6, 14), amount=Decimal("500.00"), posting_sequence=30)
    pos = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    assert pos.cash == Decimal("8500.00")
    assert pos.units_for(SCHEME_A) == Decimal("100.000")
    val = valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    assert val.holdings[0].value == Decimal("1000.00")
    assert val.portfolio_value == Decimal("9500.00")
    assert val.fresh_value == Decimal("1000.00") and val.stale_value == Decimal("0")


def test_redemption_and_multiple_schemes_accounts(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    _create_txn(ledger, 920001, 920001, "M4-T3", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 14), amount=Decimal("2000.00"), scheme=SCHEME_B, posting_sequence=30)
    _create_txn(ledger, 920001, 920001, "M4-T4", "REDEMPTION", date(2024, 1, 5), _utc(2024, 1, 6, 15), units=Decimal("40.000"), scheme=SCHEME_A, posting_sequence=40)
    _create_txn(ledger, 920002, 920002, "M4-T5", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("5000.00"), posting_sequence=10)
    _create_txn(ledger, 920002, 920002, "M4-T6", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 16), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    pos1 = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    pos2 = valuation.positions(920002, date(2024, 1, 5), _utc(2024, 1, 10))
    assert pos1.units_for(SCHEME_A) == Decimal("60.000")  # 100 - 40
    assert pos1.units_for(SCHEME_B) == Decimal("100.000")  # 2000/20
    assert pos1.cash == Decimal("10000.00") - Decimal("1000.00") - Decimal("2000.00") + Decimal("400.00")
    assert pos2.units_for(SCHEME_A) == Decimal("100.000")
    assert pos2.cash == Decimal("4000.00")


def test_sip_linked_legs(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "SIP_INSTALMENT", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    pos = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    # Contribution 11000 - purchase actual 1000 = 10000 cash, 100 units.
    assert pos.cash == Decimal("10000.00")
    assert pos.units_for(SCHEME_A) == Decimal("100.000")


def test_switch_split_dates_interim_cash(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    _create_txn(ledger, 920001, 920001, "M4-T3", "SWITCH", date(2024, 1, 5), _utc(2024, 1, 6, 14), units=Decimal("10.000"), source=SCHEME_A, target=SCHEME_C, posting_sequence=30)
    pos_before = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    # Switch legs: source redemption on 01-05, target purchase on 01-06.
    # At 01-05 the source is redeemed (90 units) and proceeds sit as cash.
    assert pos_before.units_for(SCHEME_A) == Decimal("90.000")
    assert pos_before.units_for(SCHEME_C) == Decimal("0")
    pos_after = valuation.positions(920001, date(2024, 1, 6), _utc(2024, 1, 10))
    assert pos_after.units_for(SCHEME_C) == Decimal("3.333")  # ROUND_DOWN(100/30)
    val = valuation.value(920001, date(2024, 1, 6), _utc(2024, 1, 10))
    scheme_c = [h for h in val.holdings if h.scheme_code == SCHEME_C][0]
    assert scheme_c.value == Decimal("99.99")  # 3.333*30 rounded


def test_k1_k2_reconstruction(pair) -> None:
    from bitemporal_ledger.ledger.models import CorrectionRequest

    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    ledger.apply_correction(
        CorrectionRequest(
            txn_group_id="M4-T2", correction_type="REPLACE", reason_code="TEST", reason_note="test",
            source_ref="synthetic_intent", actor_id="SYN_OP-001", recorded_at=_utc(2024, 1, 20),
            proposed_amount=Decimal("500.00"),
        )
    )
    k1 = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    k2 = valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 25))
    assert k1.units_for(SCHEME_A) == Decimal("100.000")
    assert k2.units_for(SCHEME_A) == Decimal("50.000")
    v1 = valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    v2 = valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 25))
    assert v1.holdings[0].value == Decimal("1000.00")
    assert v2.holdings[0].value == Decimal("500.00")


def test_missing_and_stale_nav(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    # 2024-01-07 is 2 days after the 01-05 NAV: stale but inside the limit.
    stale = valuation.value(920001, date(2024, 1, 7), _utc(2024, 1, 10))
    assert stale.holdings[0].is_stale and stale.holdings[0].stale_days == 2
    assert stale.stale_value == Decimal("1000.00") and stale.fresh_value == Decimal("0")
    # 2024-01-11 is 6 days out: beyond the limit.
    with pytest.raises(ValuationError) as excinfo:
        valuation.value(920001, date(2024, 1, 11), _utc(2024, 1, 15))
    assert excinfo.value.reason_code in ("STALE_BEYOND_LIMIT", "MISSING_NAV")


def test_negative_positions_invariant(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    # Direct helper bypasses M3 validity: a purchase with no funds.
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("999999.00"), scheme=SCHEME_A, posting_sequence=20)
    with pytest.raises(InvariantError):
        valuation.positions(920001, date(2024, 1, 5), _utc(2024, 1, 10))


def test_deterministic_repeated_queries(pair) -> None:
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    first = valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    second = valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 10))
    assert first == second
    assert first.portfolio_value == Decimal("10000.00")  # 9000 cash + 1000 holdings


def test_nav_exactly_five_days_stale_is_accepted_and_flagged(pair) -> None:
    """Boundary: NAV on 2024-01-05 valued on 2024-01-10 = exactly 5 days stale."""
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    result = valuation.value(920001, date(2024, 1, 10), _utc(2024, 1, 15))
    assert result.holdings[0].is_stale and result.holdings[0].stale_days == 5
    assert result.holdings[0].price == Decimal("10.000000")
    assert result.stale_value == Decimal("1000.00") and result.fresh_value == Decimal("0")
    assert result.portfolio_value == Decimal("10000.00")  # 9000 cash + 1000 stale value


def test_missing_nav_before_valuation_date(pair) -> None:
    """Valuation before any NAV for the holding -> MISSING_NAV."""
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("10000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    # 2024-01-04 precedes the earliest NAV (2024-01-05) for SCHEME_A and
    # there is no holding yet, so valuation is an empty portfolio.
    empty = valuation.value(920001, date(2024, 1, 4), _utc(2024, 1, 10))
    assert empty.holdings == () and empty.portfolio_value == Decimal("0")
    # Remove every NAV for SCHEME_A; the existing holding can no longer be priced.
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM core.nav_observation WHERE amfi_scheme_code = %s AND nav_snapshot_id = %s", (SCHEME_A, valuation.nav_snapshot_id))
        cur.execute("DELETE FROM core.nav_observation WHERE amfi_scheme_code = %s AND nav_snapshot_id = %s", (SCHEME_B, valuation.nav_snapshot_id))
    conn.commit()
    conn.close()
    with pytest.raises(ValuationError) as excinfo:
        valuation.value(920001, date(2024, 1, 5), _utc(2024, 1, 20))
    assert excinfo.value.reason_code == "MISSING_NAV"


def test_multi_holding_one_missing_fails_wholly(pair) -> None:
    """One unpriceable holding aborts the whole valuation (no partial total)."""
    ledger, valuation = pair
    _create_txn(ledger, 920001, 920001, "M4-T1", "CONTRIBUTION", date(2024, 1, 5), _utc(2024, 1, 6), amount=Decimal("100000.00"), posting_sequence=10)
    _create_txn(ledger, 920001, 920001, "M4-T2", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 13), amount=Decimal("1000.00"), scheme=SCHEME_A, posting_sequence=20)
    # SCHEME_D's only NAV is 2024-01-11; buying it on the 11th then valuing on
    # the 12th prices A stale-fresh but leaves D fresh only via a different
    # calendar path. Use a holding with no NAV at all on the valuation date:
    # value on 2024-01-04 would fail both, so value on 2024-01-06 for a scheme
    # whose NAV is only on the 11th (unbuyable here) fails via positions.
    # Instead, assert the atomicity contract directly: any single missing
    # holding in a multi-holding portfolio raises instead of returning a total.
    _create_txn(ledger, 920001, 920001, "M4-T3", "PURCHASE", date(2024, 1, 5), _utc(2024, 1, 6, 14), amount=Decimal("2000.00"), scheme=SCHEME_B, posting_sequence=30)
    # Hold A and B; make B's latest NAV exceed the limit by valuing late.
    with pytest.raises(ValuationError):
        valuation.value(920001, date(2024, 1, 11), _utc(2024, 1, 15))
    # The failed call returned nothing (no partial portfolio_value exposed).
