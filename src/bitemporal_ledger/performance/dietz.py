"""Modified Dietz return (M5, METHODOLOGY §6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bitemporal_ledger.performance.models import FlowPoint
from bitemporal_ledger.performance.twr import PerformanceError


def modified_dietz(
    start_value: Decimal,
    flows: list[FlowPoint],
    end_value: Decimal,
    *,
    period_start: date,
    period_end: date,
) -> Decimal:
    """`R = (V_E − V_S − Σ CF) / (V_S + Σ w_i CF_i)`, `w_i = (T − t_i)/T`."""
    # Inclusive full-calendar-day convention: T = (E - S).days where
    # E = (end_date + 1 day), i.e. the inclusive calendar-day count.
    total_days = (period_end - period_start).days + 1
    if total_days <= 0:
        raise PerformanceError("INVALID_DENOMINATOR", "period must span at least one day")
    sum_cf = sum((flow.amount for flow in flows), Decimal("0"))
    weighted = sum(
        (
            (Decimal(total_days - (flow.flow_date - period_start).days) / Decimal(total_days)) * flow.amount
            for flow in flows
        ),
        Decimal("0"),
    )
    denominator = start_value + weighted
    if denominator <= 0:
        raise PerformanceError("INVALID_DENOMINATOR", "start value plus weighted flows must be positive")
    return (end_value - start_value - sum_cf) / denominator
