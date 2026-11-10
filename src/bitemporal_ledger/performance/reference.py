"""Independent XIRR reference (M5) — bisection only, never calls production code."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, getcontext

getcontext().prec = 28


def reference_xirr(cash_flows: list[tuple[date, Decimal]], lo: Decimal = Decimal("-0.5"), hi: Decimal = Decimal("5.0")) -> Decimal | None:
    """Bisection reference on ``x = 1/(1+r)`` transformed NPV.

    Written independently from ``xirr.py``: no production import, different
    parameterisation (searches in ``x``), and bisection only.
    """
    flows = sorted(cash_flows)
    if len(flows) < 2:
        return None

    def npv_in_x(x: Decimal) -> Decimal:
        d0 = flows[0][0]
        total = Decimal("0")
        for flow_date, amount in flows:
            days = (flow_date - d0).days
            total += amount * (x ** (Decimal(days) / Decimal("365")))
        return total

    # Search in x-space (x > 0 corresponds to r > -1).
    x_lo = Decimal("1") / (Decimal("1") + hi)
    x_hi = Decimal("1") / (Decimal("1") + lo)
    f_lo = npv_in_x(x_lo)
    f_hi = npv_in_x(x_hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (x_lo + x_hi) / 2
        f_mid = npv_in_x(mid)
        if f_lo * f_mid <= 0:
            x_hi = mid
        else:
            x_lo, f_lo = mid, f_mid
    x_root = (x_lo + x_hi) / 2
    if x_root <= 0:
        return None
    return Decimal("1") / x_root - 1
