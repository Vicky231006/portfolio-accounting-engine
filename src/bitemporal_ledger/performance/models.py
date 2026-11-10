"""Performance engine models (M5, FR-B7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class FlowPoint:
    flow_date: date
    amount: Decimal  # portfolio perspective: + contribution, - withdrawal


@dataclass(frozen=True)
class XirrResult:
    status: str
    rate: Decimal | None
    rates: tuple[Decimal, ...]
    iterations: int
    method: str
    residual: Decimal | None
    reason: str
    domain: tuple[Decimal, Decimal]
    grid_points: int
    nearest_root_outside_domain: Decimal | None = None


@dataclass(frozen=True)
class PerformanceResult:
    twr: Decimal
    modified_dietz: Decimal
    xirr: XirrResult
    start_value: Decimal
    end_value: Decimal
    flows: tuple[FlowPoint, ...]
    period_start: date
    period_end: date
