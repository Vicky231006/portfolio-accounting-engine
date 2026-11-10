"""M5 formula tests against METHODOLOGY hand-computed fixtures (D-028).

Every expected value below is taken verbatim from docs/METHODOLOGY.md
§5–§8 (§9 in the integration replay test). Production functions are called
only to compare; no expected value is computed by calling them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bitemporal_ledger.performance import dietz, twr, xirr
from bitemporal_ledger.performance.models import FlowPoint
from bitemporal_ledger.performance.reference import reference_xirr


def test_twr_zero_flow() -> None:
    assert twr.start_to_end(Decimal("100000"), Decimal("105000")) == Decimal("0.05")


def test_twr_contribution() -> None:
    flow = FlowPoint(date(2026, 1, 1), Decimal("20000"))
    value = twr.with_flows(Decimal("100000"), flow, Decimal("122000"))
    assert value.quantize(Decimal("0.000001")) == Decimal("0.016667")


def test_twr_withdrawal() -> None:
    flow = FlowPoint(date(2026, 1, 1), Decimal("-20000"))
    value = twr.with_flows(Decimal("100000"), flow, Decimal("82000"))
    assert value == Decimal("0.025")


def test_twr_same_day() -> None:
    flow = FlowPoint(date(2026, 2, 10), Decimal("10000"))
    value = twr.with_flows(Decimal("100000"), flow, Decimal("111000"))
    assert value.quantize(Decimal("0.000001")) == Decimal("0.009091")


def test_twr_mid_period() -> None:
    r1 = Decimal("102000") / Decimal("100000") - 1
    r2 = (Decimal("152000") - Decimal("102000") - Decimal("50000")) / (Decimal("102000") + Decimal("50000"))
    r3 = Decimal("154000") / Decimal("152000") - 1
    value = twr.compounded([r1, r2, r3])
    assert value.quantize(Decimal("0.000001")) == Decimal("0.033421")
    production = twr.compute_twr(
        start_value=Decimal("100000"),
        end_value=Decimal("154000"),
        flows=[(date(2026, 2, 26), Decimal("102000"), Decimal("50000"), Decimal("152000"))],
        period_start=date(2026, 2, 2),
        period_end=date(2026, 2, 28),
    )
    assert production.quantize(Decimal("0.000001")) == Decimal("0.033421")


def test_dietz_mid_period() -> None:
    value = dietz.modified_dietz(
        Decimal("100000"),
        [FlowPoint(date(2026, 2, 26), Decimal("50000"))],
        Decimal("154000"),
        period_start=date(2026, 2, 2),
        period_end=date(2026, 2, 28),
    )
    assert value.quantize(Decimal("0.000001")) == Decimal("0.037895")


def test_dietz_zero_and_same_day() -> None:
    zero = dietz.modified_dietz(
        Decimal("100000"), [], Decimal("105000"),
        period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
    )
    assert zero == Decimal("0.05")
    same_day = dietz.modified_dietz(
        Decimal("100000"), [FlowPoint(date(2026, 2, 10), Decimal("10000"))], Decimal("111000"),
        period_start=date(2026, 2, 10), period_end=date(2026, 2, 11),
    )
    assert same_day.quantize(Decimal("0.000001")) == Decimal("0.009091")


def test_xirr_simple() -> None:
    flows = [(date(2026, 1, 1), Decimal("-100000")), (date(2027, 1, 1), Decimal("110000"))]
    result = xirr.solve(flows)
    assert result["status"] == "SUCCESS"
    assert result["rate"].quantize(Decimal("0.000001")) == Decimal("0.1")


def test_twr_vs_xirr_gap() -> None:
    flows = [
        (date(2025, 1, 1), Decimal("-1000")),
        (date(2026, 1, 1), Decimal("-1000")),
        (date(2027, 1, 1), Decimal("2200")),
    ]
    result = xirr.solve(flows)
    assert result["status"] == "SUCCESS"
    assert abs(result["rate"] - Decimal("0.0652475842")) < Decimal("0.000001")
    twr_value = twr.compounded(
        [Decimal("1100") / Decimal("1000") - 1, Decimal("2200") / Decimal("2100") - 1]
    )
    assert abs(twr_value - Decimal("0.1523809524")) < Decimal("0.000001")


def test_xirr_multiple_roots() -> None:
    flows = [
        (date(2025, 1, 1), Decimal("-100")),
        (date(2026, 1, 1), Decimal("230")),
        (date(2027, 1, 1), Decimal("-132")),
    ]
    result = xirr.solve(flows)
    assert result["status"] == "MULTIPLE_ROOTS"
    rates = sorted(float(r) for r in result["rates"])
    assert rates[0] == pytest.approx(0.10, abs=1e-6)
    assert rates[1] == pytest.approx(0.20, abs=1e-6)


def test_xirr_no_root_proven() -> None:
    flows = [
        (date(2025, 1, 1), Decimal("-100")),
        (date(2026, 1, 1), Decimal("1")),
        (date(2027, 1, 1), Decimal("-100")),
    ]
    result = xirr.solve(flows)
    assert result["status"] == "NO_ROOT_PROVEN"
    assert result["rate"] is None


def test_xirr_no_root_in_domain() -> None:
    flows = [(date(2025, 1, 1), Decimal("-100")), (date(2026, 1, 1), Decimal("100200"))]
    result = xirr.solve(flows)
    assert result["status"] == "NO_ROOT_IN_DOMAIN"
    assert result["nearest_root_outside_domain"] == pytest.approx(Decimal("1001"), abs=Decimal("1"))


def test_xirr_invalid_flows() -> None:
    assert xirr.solve([(date(2025, 1, 1), Decimal("-100"))])["status"] == "INVALID_CASH_FLOWS"
    assert xirr.solve([(date(2025, 1, 1), Decimal("-100")), (date(2026, 1, 1), Decimal("-50"))])["status"] == "INVALID_CASH_FLOWS"


def test_sip_returns() -> None:
    period_start = date(2026, 3, 1)
    period_end = date(2026, 3, 31)
    sip = FlowPoint(date(2026, 3, 5), Decimal("5000"))
    twr_value = twr.compute_twr(
        start_value=Decimal("10000"),
        end_value=Decimal("15400"),
        flows=[(date(2026, 3, 5), Decimal("10000"), Decimal("5000"), Decimal("15000"))],
        period_start=period_start,
        period_end=period_end,
    )
    assert twr_value.quantize(Decimal("0.000001")) == Decimal("0.026667")
    dietz_value = dietz.modified_dietz(Decimal("10000"), [sip], Decimal("15400"), period_start=period_start, period_end=period_end)
    assert dietz_value.quantize(Decimal("0.000001")) == Decimal("0.027865")


def test_returns_scale_invariant() -> None:
    base = twr.with_flows(Decimal("100000"), FlowPoint(date(2026, 1, 1), Decimal("20000")), Decimal("122000"))
    scaled = twr.with_flows(Decimal("300000"), FlowPoint(date(2026, 1, 1), Decimal("60000")), Decimal("366000"))
    assert base == scaled


def test_no_flow_xirr_equals_period_return() -> None:
    flows = [(date(2025, 1, 1), Decimal("-100000")), (date(2026, 1, 1), Decimal("105000"))]
    result = xirr.solve(flows)
    period_return = twr.start_to_end(Decimal("100000"), Decimal("105000"))
    assert abs(result["rate"] - period_return) < Decimal("0.000001")


def test_reference_xirr_matches_production() -> None:
    flows = [
        (date(2025, 1, 1), Decimal("-1000")),
        (date(2026, 1, 1), Decimal("-1000")),
        (date(2027, 1, 1), Decimal("2200")),
    ]
    production = xirr.solve(flows)
    reference = reference_xirr(flows)
    assert production["status"] == "SUCCESS"
    assert reference is not None
    error = abs(production["rate"] - reference)
    assert error < Decimal("0.000001")
    # E1-style bound: production must be within 1bp of the independent reference.
    assert error < Decimal("0.0001")
