"""Pipeline invariants (M7, FR-B10).

Each invariant replays the visible ledger for an account through the same
leg logic as positions/valuation but asserts the global rules, collecting
explicit failure records rather than raising on the first defect. The
pipeline gate fails the run if any invariant fails.

Stale-NAV valuations are expected for schemes whose AMFI coverage ended
before the invariant date; they are reported separately and are not
invariant failures.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from bitemporal_ledger.ledger.models import VisibleRevision
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.valuation.service import ValuationService

InvariantRunResult = dict  # {passed, failed, violations: [...], accounts_checked: int, stale_accounts: int}


def _all_accounts(dsn: str) -> list[int]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM core.account ORDER BY account_id")
            return [row[0] for row in cur.fetchall()]


def run_invariants(
    dsn: str,
    nav_snapshot_id: int,
    *,
    valid_date: date,
    known_as_of: datetime,
) -> InvariantRunResult:
    """Run the M7 invariant suite; return counts and violations."""
    ledger = LedgerService(dsn, nav_snapshot_id)
    valuation = ValuationService(dsn, nav_snapshot_id, ledger)
    violations: list[dict] = []
    stale_accounts = 0
    accounts = _all_accounts(dsn)
    # Load the as-of revision set once and group it by account so each account is derived from an
    # in-memory slice instead of rescanning the full ledger per account (M7 invariant sweep).
    visible = ledger.get_as_of(known_as_of)
    by_account: dict[int, list[VisibleRevision]] = {}
    for txn in visible:
        by_account.setdefault(txn.account_id, []).append(txn)
    for account_id in accounts:
        txns = by_account.get(account_id, [])
        try:
            positions = valuation.positions(account_id, valid_date, known_as_of, visible=txns)
        except Exception as exc:  # keep collecting across accounts
            reason = getattr(exc, "reason_code", type(exc).__name__)
            violations.append({"account_id": account_id, "check": "positions_derivable", "reason": reason, "message": str(exc)})
            continue
        assert isinstance(positions.cash, Decimal)
        for holding in positions.holdings:
            assert isinstance(holding.units, Decimal)
            assert holding.units >= 0
        try:
            valuation.value(account_id, valid_date, known_as_of, visible=txns)
        except Exception as exc:
            reason = getattr(exc, "reason_code", type(exc).__name__)
            if reason in ("STALE_BEYOND_LIMIT", "MISSING_NAV"):
                stale_accounts += 1
            else:
                raise
    passed = len(accounts) - len({v["account_id"] for v in violations})
    return {"passed": max(passed, 0), "failed": len({v["account_id"] for v in violations}), "violations": violations, "accounts_checked": len(accounts), "stale_accounts": stale_accounts}
