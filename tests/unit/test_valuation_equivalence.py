"""Optimised as-of derivation must be equivalent to the ledger-query path (M7 invariant sweep).

The invariant sweep used to rescan the full ledger once per account (via ``positions`` and again
via ``value`` -> ``positions``). Callers may now pass a pre-loaded as-of revision set via the
keyword-only ``visible`` argument; these tests pin the equivalence of that optimised path against
the existing ledger-query path without weakening any assertion.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import bitemporal_ledger.valuation.service as valuation_service_module
from bitemporal_ledger.ledger.models import VisibleRevision
from bitemporal_ledger.valuation.service import ValuationService

K = datetime(2024, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def execute(self, *args, **kwargs) -> None:  # noqa: ARG002
        return None

    def fetchone(self) -> None:
        return None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args) -> bool:
        return False


class _FakeConn:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *args) -> bool:
        return False


class _StubLedger:
    """Minimal ledger double exposing only the as-of query surface used by the valuation service."""

    def __init__(self, revisions: list[VisibleRevision]) -> None:
        self.revisions = revisions
        self.get_as_of_calls = 0

    def _as_utc(self, value: datetime) -> datetime:
        return value

    def get_as_of(self, known_as_of: datetime) -> list[VisibleRevision]:
        self.get_as_of_calls += 1
        return list(self.revisions)


def _revision(txn_group_id: str, txn_type: str, account_id: int, effective_date: date, *, amount: Decimal | None, posting_sequence: int = 10) -> VisibleRevision:
    return VisibleRevision(
        txn_group_id=txn_group_id,
        txn_revision_id=1000,
        revision_no=1,
        revision_kind="ORIGINAL",
        revision_status="ACCEPTED",
        txn_type=txn_type,
        account_id=account_id,
        instruction_date=effective_date,
        effective_date=effective_date,
        allotment_date=None,
        source_nav_date=None,
        target_allotment_date=None,
        posting_sequence=posting_sequence,
        scheme_code=None,
        source_scheme_code=None,
        target_scheme_code=None,
        amount_instructed=amount,
        units_instructed=None,
        recorded_at=datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


def _valuation(revisions: list[VisibleRevision]) -> tuple[_StubLedger, ValuationService]:
    ledger = _StubLedger(revisions)
    return ledger, ValuationService("postgresql://stub", 1, ledger)


def test_positions_preloaded_visible_is_equivalent_to_ledger_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(valuation_service_module.psycopg, "connect", lambda dsn: _FakeConn())  # type: ignore[attr-defined]
    revisions = [
        _revision("T1", "CONTRIBUTION", 7, date(2024, 1, 5), amount=Decimal("10000.00")),
        _revision("T2", "WITHDRAWAL", 7, date(2024, 1, 5), amount=Decimal("2500.00")),
    ]
    ledger, valuation = _valuation(revisions)
    via_ledger = valuation.positions(7, date(2024, 1, 5), K)
    assert ledger.get_as_of_calls == 1
    assert via_ledger.cash == Decimal("7500.00")
    assert via_ledger.holdings == ()

    via_preload = valuation.positions(7, date(2024, 1, 5), K, visible=list(revisions))
    # Optimised path must not trigger a second ledger scan when the as-of set is supplied.
    assert ledger.get_as_of_calls == 1
    assert via_preload.cash == via_ledger.cash
    assert via_preload.as_of_revision_count == via_ledger.as_of_revision_count
    assert via_preload.holdings == via_ledger.holdings


def test_positions_preload_uses_account_group_slice_without_ledger_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(valuation_service_module.psycopg, "connect", lambda dsn: _FakeConn())  # type: ignore[attr-defined]
    revisions = [
        _revision("T1", "CONTRIBUTION", 7, date(2024, 1, 5), amount=Decimal("10000.00")),
        _revision("T2", "WITHDRAWAL", 8, date(2024, 1, 5), amount=Decimal("2500.00")),
    ]
    ledger, valuation = _valuation(revisions)
    group_slice = [txn for txn in revisions if txn.account_id == 7]
    via_slice = valuation.positions(7, date(2024, 1, 5), K, visible=group_slice)
    via_full_filter = valuation.positions(7, date(2024, 1, 5), K, visible=list(revisions))
    assert ledger.get_as_of_calls == 0
    assert via_slice.cash == via_full_filter.cash
    assert via_slice.as_of_revision_count == via_full_filter.as_of_revision_count
    assert via_slice.holdings == via_full_filter.holdings
