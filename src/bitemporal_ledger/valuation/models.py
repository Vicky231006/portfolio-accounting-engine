"""M4 result models and errors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class ValuationError(RuntimeError):
    """Explicit NAV failure (stale beyond limit or no NAV at all)."""

    def __init__(self, reason_code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details or {}


class InvariantError(RuntimeError):
    """Negative cash/units or reconciliation mismatch in a position replay."""

    def __init__(self, reason_code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details or {}


@dataclass(frozen=True)
class Holding:
    scheme_code: str
    units: Decimal


@dataclass(frozen=True)
class PositionsResult:
    account_id: int
    valid_date: date
    known_as_of: datetime
    cash: Decimal
    holdings: tuple[Holding, ...]
    as_of_revision_count: int

    def units_for(self, scheme_code: str) -> Decimal:
        for holding in self.holdings:
            if holding.scheme_code == scheme_code:
                return holding.units
        return Decimal("0")


@dataclass(frozen=True)
class NavPrice:
    scheme_code: str
    nav_snapshot_id: int
    price: Decimal
    price_date: date
    is_stale: bool
    stale_days: int


@dataclass(frozen=True)
class ValuedHolding:
    scheme_code: str
    units: Decimal
    price: Decimal
    price_date: date
    is_stale: bool
    stale_days: int
    value: Decimal


@dataclass(frozen=True)
class ValuationResult:
    account_id: int
    valid_date: date
    known_as_of: datetime
    nav_snapshot_id: int
    cash: Decimal
    holdings: tuple[ValuedHolding, ...]
    fresh_value: Decimal
    stale_value: Decimal
    portfolio_value: Decimal
    positions: PositionsResult
