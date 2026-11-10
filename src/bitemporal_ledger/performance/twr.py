"""Time-weighted return (M5, METHODOLOGY §5)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bitemporal_ledger.performance.models import FlowPoint


class PerformanceError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def start_to_end(start_value: Decimal, end_value: Decimal) -> Decimal:
    """Zero-flow return `V_E/V_S − 1` (METHODOLOGY §5.3)."""
    if start_value <= 0:
        raise PerformanceError("INVALID_DENOMINATOR", "start value must be positive")
    return end_value / start_value - 1


def with_flows(start_value: Decimal, flow: FlowPoint, end_value: Decimal) -> Decimal:
    """Single-flow return `(V_E − V_S − CF)/(V_S + CF)` (METHODOLOGY §5.4–§5.6)."""
    denominator = start_value + flow.amount
    if denominator <= 0:
        raise PerformanceError("INVALID_DENOMINATOR", "start value plus flow must be positive")
    return (end_value - start_value - flow.amount) / denominator


def compounded(subperiod_returns: list[Decimal]) -> Decimal:
    """Chain-link subperiod returns `(1+r_t) − 1` (METHODOLOGY §5.2, §5.7)."""
    result = Decimal("1")
    for item in subperiod_returns:
        result *= 1 + item
    return result - 1


def compute_twr(
    *,
    start_value: Decimal,
    end_value: Decimal,
    flows: list[tuple[date, Decimal, Decimal, Decimal]],
    period_start: date,
    period_end: date,
) -> Decimal:
    """Production TWR from end-of-day valuations.

    Each flow entry is `(flow_date, pre_flow_value, flow_amount, flow_day_eod_value)`
    where `pre_flow_value` is the EOD value on the day before the flow date and
    `flow_day_eod_value` is the EOD value on the flow date itself (inclusive of
    the flow and that day's market move). Gap subperiods are `end/start − 1`.
    """
    subperiods: list[Decimal] = []
    cursor_value = start_value
    for flow_date, pre_flow, amount, flow_eod in sorted(flows):
        if pre_flow != cursor_value:
            # Gap from cursor to pre-flow (usually zero-length in fixture inputs).
            if cursor_value <= 0:
                raise PerformanceError("INVALID_DENOMINATOR", "cursor value must be positive")
            subperiods.append(pre_flow / cursor_value - 1)
        denominator = pre_flow + amount
        if denominator <= 0:
            raise PerformanceError("INVALID_DENOMINATOR", "pre-flow value plus flow must be positive")
        subperiods.append((flow_eod - pre_flow - amount) / denominator)
        cursor_value = flow_eod
    if end_value != cursor_value:
        if cursor_value <= 0:
            raise PerformanceError("INVALID_DENOMINATOR", "cursor value must be positive")
        subperiods.append(end_value / cursor_value - 1)
    if not subperiods:
        subperiods.append(start_to_end(start_value, end_value))
    return compounded(subperiods)
