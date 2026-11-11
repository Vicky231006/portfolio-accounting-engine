"""As-of position derivation and NAV valuation service (M4, FR-B5/FR-B6)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import psycopg

from bitemporal_ledger.ledger.derivation import (
    purchase_actual_cash,
    purchase_units,
    redemption_proceeds,
    switch_derived,
)
from bitemporal_ledger.ledger.models import VisibleRevision
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.valuation.models import (
    Holding,
    InvariantError,
    NavPrice,
    PositionsResult,
    ValuationError,
    ValuationResult,
    ValuedHolding,
)

DEFAULT_STALE_LIMIT_DAYS = 5


class ValuationService:
    """As-of positions and valuation over an M1 NAV snapshot."""

    def __init__(self, dsn: str, nav_snapshot_id: int, ledger: LedgerService | None = None) -> None:
        self.dsn = dsn
        self.nav_snapshot_id = nav_snapshot_id
        self.ledger = ledger if ledger is not None else LedgerService(dsn, nav_snapshot_id)

    # ---------------------------------------------------------- helpers

    def _nav_price_for_derivation(self, cur, scheme_code: str, nav_date: date) -> Decimal | None:
        cur.execute(
            "SELECT nav FROM core.nav_observation WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s AND nav_date = %s",
            (self.nav_snapshot_id, scheme_code, nav_date),
        )
        row = cur.fetchone()
        return Decimal(row[0]) if row else None

    def _latest_nav(self, scheme_code: str, valid_date: date, *, conn=None) -> NavPrice | None:
        """Latest NAV at or before ``valid_date`` for the M1 snapshot (optionally over a caller-owned connection)."""
        if conn is None:
            with psycopg.connect(self.dsn) as new_conn:
                with new_conn.cursor() as cur:
                    return self._nav_latest(cur, scheme_code, valid_date)
        with conn.cursor() as cur:
            return self._nav_latest(cur, scheme_code, valid_date)

    def _nav_latest(self, cur, scheme_code: str, valid_date: date) -> NavPrice | None:
        cur.execute(
            "SELECT nav, nav_date FROM core.nav_observation"
            " WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s AND nav_date <= %s"
            " ORDER BY nav_date DESC LIMIT 1",
            (self.nav_snapshot_id, scheme_code, valid_date),
        )
        row = cur.fetchone()
        if row is None:
            return None
        price, price_date = Decimal(row[0]), row[1]
        stale_days = (valid_date - price_date).days
        return NavPrice(
            scheme_code=scheme_code,
            nav_snapshot_id=self.nav_snapshot_id,
            price=price,
            price_date=price_date,
            is_stale=stale_days > 0,
            stale_days=stale_days,
        )

    # ---------------------------------------------------------- positions

    def positions(
        self,
        account_id: int,
        valid_date: date,
        known_as_of: datetime,
        *,
        visible: list[VisibleRevision] | None = None,
    ) -> PositionsResult:
        """Derive (cash, units) as of ``valid_date`` using only revisions known at ``known_as_of``.

        ``visible`` lets a caller that already holds the as-of revision set (for example an
        account-grouped sweep) pass it in instead of rescanning the ledger per account; when it is
        omitted the ledger is queried as of ``known_as_of``.
        """
        known_as_of = self.ledger._as_utc(known_as_of)
        if visible is None:
            visible = self.ledger.get_as_of(known_as_of)
        txns = [txn for txn in visible if txn.account_id == account_id]
        legs: list[tuple[date, int, str, Decimal, Decimal, str | None]] = []
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for txn in txns:
                    txn_type = txn.txn_type
                    scheme = txn.scheme_code
                    source = txn.source_scheme_code
                    target = txn.target_scheme_code
                    amount = txn.amount_instructed
                    units = txn.units_instructed
                    seq = int(txn.posting_sequence)
                    if txn_type == "CONTRIBUTION":
                        legs.append((txn.effective_date, seq, txn.txn_group_id, amount or Decimal("0"), Decimal("0"), None))
                    elif txn_type == "WITHDRAWAL":
                        legs.append((txn.effective_date, seq, txn.txn_group_id, -(amount or Decimal("0")), Decimal("0"), None))
                    elif txn_type == "PURCHASE":
                        assert amount is not None and scheme is not None and txn.allotment_date is not None
                        price = self._nav_price_for_derivation(cur, scheme, txn.allotment_date)
                        if price is None:
                            raise ValuationError("MISSING_NAV", f"No NAV for {scheme} on {txn.allotment_date}", {"scheme_code": scheme, "nav_date": txn.allotment_date.isoformat()})
                        units_q = purchase_units(amount, price)
                        actual = purchase_actual_cash(units_q, price)
                        legs.append((txn.allotment_date, seq, txn.txn_group_id, -actual, units_q, scheme))
                    elif txn_type == "REDEMPTION":
                        assert units is not None and scheme is not None and txn.allotment_date is not None
                        price = self._nav_price_for_derivation(cur, scheme, txn.allotment_date)
                        if price is None:
                            raise ValuationError("MISSING_NAV", f"No NAV for {scheme} on {txn.allotment_date}", {"scheme_code": scheme, "nav_date": txn.allotment_date.isoformat()})
                        legs.append((txn.allotment_date, seq, txn.txn_group_id, redemption_proceeds(units, price), -units, scheme))
                    elif txn_type == "SIP_INSTALMENT":
                        assert amount is not None and scheme is not None and txn.allotment_date is not None
                        legs.append((txn.effective_date, seq, txn.txn_group_id, amount, Decimal("0"), None))
                        price = self._nav_price_for_derivation(cur, scheme, txn.allotment_date)
                        if price is None:
                            raise ValuationError("MISSING_NAV", f"No NAV for {scheme} on {txn.allotment_date}", {"scheme_code": scheme, "nav_date": txn.allotment_date.isoformat()})
                        units_q = purchase_units(amount, price)
                        actual = purchase_actual_cash(units_q, price)
                        legs.append((txn.allotment_date, seq, txn.txn_group_id, -actual, units_q, scheme))
                    elif txn_type == "SWITCH":
                        assert units is not None and source is not None and target is not None
                        assert txn.source_nav_date is not None and txn.target_allotment_date is not None
                        source_price = self._nav_price_for_derivation(cur, source, txn.source_nav_date)
                        target_price = self._nav_price_for_derivation(cur, target, txn.target_allotment_date)
                        if source_price is None or target_price is None:
                            raise ValuationError("MISSING_NAV", f"No NAV for switch {source}->{target}", {"source": source, "target": target})
                        derived = switch_derived(units, source_price, target_price)
                        assert derived.proceeds is not None
                        legs.append((txn.source_nav_date, seq, txn.txn_group_id, derived.proceeds, -units, source))
                        legs.append((txn.target_allotment_date, seq, txn.txn_group_id, -(derived.actual_cash or Decimal("0")), derived.units or Decimal("0"), target))
                    else:
                        raise InvariantError("INVARIANT_FAILED", f"Unknown type {txn_type}")
        legs.sort(key=lambda item: (item[0], item[1], item[2]))
        cash = Decimal("0")
        units_map: dict[str, Decimal] = {}
        for posting_date, seq, txn_group_id, cash_delta, units_delta, code in legs:
            if posting_date > valid_date:
                continue
            cash += cash_delta
            if code is not None:
                units_map[code] = units_map.get(code, Decimal("0")) + units_delta
                if units_map[code] < 0:
                    raise InvariantError("NEGATIVE_UNITS", f"Negative units for {code} at {posting_date}", {"scheme_code": code, "txn_group_id": txn_group_id})
            if cash < 0:
                raise InvariantError("NEGATIVE_CASH", f"Negative cash at {posting_date}", {"txn_group_id": txn_group_id})
        holdings = tuple(
            Holding(scheme_code=code, units=units_map[code]) for code in sorted(units_map)
        )
        return PositionsResult(
            account_id=account_id,
            valid_date=valid_date,
            known_as_of=known_as_of,
            cash=cash,
            holdings=holdings,
            as_of_revision_count=len(txns),
        )

    # ---------------------------------------------------------- valuation

    def value(
        self,
        account_id: int,
        valid_date: date,
        known_as_of: datetime,
        stale_limit_days: int = DEFAULT_STALE_LIMIT_DAYS,
        *,
        visible: list[VisibleRevision] | None = None,
    ) -> ValuationResult:
        """Value the as-of position with the M1 snapshot (see D-050/D-051)."""
        positions = self.positions(account_id, valid_date, known_as_of, visible=visible)
        valued: list[ValuedHolding] = []
        fresh_value = Decimal("0")
        stale_value = Decimal("0")
        for holding in positions.holdings:
            nav = self._latest_nav(holding.scheme_code, valid_date)
            if nav is None:
                raise ValuationError(
                    "MISSING_NAV",
                    f"No NAV at or before {valid_date.isoformat()} for scheme {holding.scheme_code}",
                    {"scheme_code": holding.scheme_code, "valid_date": valid_date.isoformat()},
                )
            if nav.stale_days > stale_limit_days:
                raise ValuationError(
                    "STALE_BEYOND_LIMIT",
                    f"Latest NAV {nav.price_date.isoformat()} is {nav.stale_days} days before valuation date "
                    f"(limit {stale_limit_days}) for scheme {holding.scheme_code}",
                    {"scheme_code": holding.scheme_code, "stale_days": nav.stale_days},
                )
            holding_value = (holding.units * nav.price).quantize(Decimal("0.01"))
            valued.append(
                ValuedHolding(
                    scheme_code=holding.scheme_code,
                    units=holding.units,
                    price=nav.price,
                    price_date=nav.price_date,
                    is_stale=nav.is_stale,
                    stale_days=nav.stale_days,
                    value=holding_value,
                )
            )
            if nav.is_stale:
                stale_value += holding_value
            else:
                fresh_value += holding_value
        holdings_value = fresh_value + stale_value
        portfolio_value = positions.cash + holdings_value
        # Reconciliation invariant: the value split must recombine exactly.
        assert holdings_value == fresh_value + stale_value
        if positions.cash + holdings_value != portfolio_value:
            raise InvariantError("RECONCILIATION_FAILED", "Portfolio value does not reconcile", {})
        return ValuationResult(
            account_id=account_id,
            valid_date=valid_date,
            known_as_of=positions.known_as_of,
            nav_snapshot_id=self.nav_snapshot_id,
            cash=positions.cash,
            holdings=tuple(valued),
            fresh_value=fresh_value,
            stale_value=stale_value,
            portfolio_value=portfolio_value,
            positions=positions,
        )
