"""XIRR solver (M5, METHODOLOGY §7, D-029).

Domain ``r ∈ (-0.999999, 1000)`` on ``u = ln(1+r)``; 2,001 grid points;
sign-change detection with bisection refinement; Newton-from-midpoint with
bisection fallback; explicit statuses. All arithmetic is high-precision
``Decimal``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, getcontext

getcontext().prec = 34

DOMAIN_LO = Decimal("-0.999999")
DOMAIN_HI = Decimal("1000")
GRID_POINTS = 2001
NPV_TOL_FACTOR = Decimal("1e-8")
RATE_TOL = Decimal("1e-12")
MAX_ITER = 200

_STATUS_SUCCESS = "SUCCESS"
_STATUS_MULTIPLE = "MULTIPLE_ROOTS"
_STATUS_NO_DOMAIN = "NO_ROOT_IN_DOMAIN"
_STATUS_NO_PROVEN = "NO_ROOT_PROVEN"
_STATUS_NONCONVERGENCE = "NON_CONVERGENCE"
_STATUS_INVALID = "INVALID_CASH_FLOWS"


def _sum_abs(flows: list[tuple[date, Decimal]]) -> Decimal:
    return sum((abs(amount) for _day, amount in flows), Decimal("0"))


def _npv_at_rate(rate: Decimal, flows: list[tuple[date, Decimal]], d0: date) -> Decimal:
    if rate <= -1:
        raise ValueError("rate must exceed -1")
    log_base = (Decimal("1") + rate).ln()
    total = Decimal("0")
    for flow_date, amount in flows:
        days = (flow_date - d0).days
        exponent = Decimal(days) / Decimal("365") * log_base
        total += amount / exponent.exp()
    return total


def _grid_rate(index: int) -> Decimal:
    lo = (Decimal("1") + DOMAIN_LO).ln()
    hi = (Decimal("1") + DOMAIN_HI).ln()
    u = lo + (hi - lo) * Decimal(index) / Decimal(GRID_POINTS - 1)
    return u.exp() - 1


def _refine_bisection(lo: Decimal, hi: Decimal, flows: list[tuple[date, Decimal]], d0: date) -> tuple[Decimal, int, Decimal]:
    f_lo = _npv_at_rate(lo, flows, d0)
    iterations = 0
    for iterations in range(1, MAX_ITER + 1):
        mid = (lo + hi) / 2
        f_mid = _npv_at_rate(mid, flows, d0)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
        if hi - lo <= RATE_TOL:
            break
    rate = (lo + hi) / 2
    return rate, iterations, _npv_at_rate(rate, flows, d0)


def _newton_from_midpoint(lo: Decimal, hi: Decimal, flows: list[tuple[date, Decimal]], d0: date) -> tuple[Decimal, int, Decimal, bool]:
    rate = (lo + hi) / 2
    for iteration in range(1, MAX_ITER + 1):
        try:
            value = _npv_at_rate(rate, flows, d0)
        except Exception:
            return rate, iteration, Decimal("0"), False
        if abs(value) <= NPV_TOL_FACTOR * max(Decimal("1"), _sum_abs(flows)):
            return rate, iteration, value, True
        eps = Decimal("1e-7")
        try:
            deriv = (_npv_at_rate(rate + eps, flows, d0) - value) / eps
        except Exception:
            return rate, iteration, value, False
        if deriv == 0:
            return rate, iteration, value, False
        new_rate = rate - value / deriv
        if new_rate <= DOMAIN_LO or new_rate > DOMAIN_HI or new_rate >= hi or new_rate <= lo:
            return new_rate, iteration, value, False
        rate = new_rate
    return rate, MAX_ITER, _npv_at_rate(rate, flows, d0), False


def solve(cash_flows: list[tuple[date, Decimal]]) -> dict:
    flows = sorted(cash_flows)
    if len(flows) < 2 or not (any(a > 0 for _d, a in flows) and any(a < 0 for _d, a in flows)):
        return {
            "status": _STATUS_INVALID,
            "rate": None,
            "rates": [],
            "iterations": 0,
            "method": "validation",
            "residual": None,
            "reason": "at least two flows with both signs are required",
            "domain": (DOMAIN_LO, DOMAIN_HI),
            "grid_points": GRID_POINTS,
            "nearest_root_outside_domain": None,
        }
    d0 = flows[0][0]
    brackets: list[tuple[Decimal, Decimal]] = []
    prev_rate = _grid_rate(0)
    prev_value = _npv_at_rate(prev_rate, flows, d0)
    for index in range(1, GRID_POINTS):
        rate = _grid_rate(index)
        value = _npv_at_rate(rate, flows, d0)
        if prev_value == 0 or value == 0 or prev_value * value < 0:
            brackets.append((prev_rate, rate))
        prev_rate, prev_value = rate, value
    if not brackets:
        return _no_root_result(flows, d0)
    roots: list[tuple[Decimal, int, Decimal]] = []
    methods: list[str] = []
    for lo, hi in brackets:
        rate, iteration, residual, ok = _newton_from_midpoint(lo, hi, flows, d0)
        if not ok:
            rate, iteration, residual = _refine_bisection(lo, hi, flows, d0)
            methods.append("bisection")
        else:
            methods.append("newton")
        roots.append((rate, iteration, residual))
    distinct: list[tuple[Decimal, int, Decimal]] = []
    for rate, iteration, residual in roots:
        if not any(abs(rate - kept[0]) <= Decimal("1e-7") for kept in distinct):
            distinct.append((rate, iteration, residual))
    if len(distinct) > 1:
        return {
            "status": _STATUS_MULTIPLE,
            "rate": None,
            "rates": sorted({r[0] for r in distinct}),
            "iterations": sum(r[1] for r in distinct),
            "method": "scan+bisection",
            "residual": None,
            "reason": "multiple distinct roots in the configured domain",
            "domain": (DOMAIN_LO, DOMAIN_HI),
            "grid_points": GRID_POINTS,
            "nearest_root_outside_domain": None,
        }
    rate, iterations, residual = distinct[0]
    tol = NPV_TOL_FACTOR * max(Decimal("1"), _sum_abs(flows))
    if abs(residual) > tol:
        return {
            "status": _STATUS_NONCONVERGENCE,
            "rate": None,
            "rates": [],
            "iterations": iterations,
            "method": methods[0],
            "residual": residual,
            "reason": "could not converge within tolerance",
            "domain": (DOMAIN_LO, DOMAIN_HI),
            "grid_points": GRID_POINTS,
            "nearest_root_outside_domain": None,
        }
    return {
        "status": _STATUS_SUCCESS,
        "rate": rate,
        "rates": [rate],
        "iterations": iterations,
        "method": methods[0],
        "residual": residual,
        "reason": "converged",
        "domain": (DOMAIN_LO, DOMAIN_HI),
        "grid_points": GRID_POINTS,
        "nearest_root_outside_domain": None,
    }


def _no_root_result(flows: list[tuple[date, Decimal]], d0: date) -> dict:
    certificate = _proven_no_root_certificate(flows)
    if certificate is not None:
        return {
            "status": _STATUS_NO_PROVEN,
            "rate": None,
            "rates": [],
            "iterations": 0,
            "method": "analytic",
            "residual": None,
            "reason": certificate,
            "domain": (DOMAIN_LO, DOMAIN_HI),
            "grid_points": GRID_POINTS,
            "nearest_root_outside_domain": None,
        }
    nearest = None
    if len(flows) == 2 and flows[0][1] < 0 and flows[1][1] > 0:
        days = (flows[1][0] - flows[0][0]).days
        if days > 0:
            ratio = (flows[1][1] / -flows[0][1]) ** (Decimal("365") / Decimal(days))
            nearest = ratio - 1
    return {
        "status": _STATUS_NO_DOMAIN,
        "rate": None,
        "rates": [],
        "iterations": 0,
        "method": "scan",
        "residual": None,
        "reason": "no sign change on the configured grid; not a proof of no root",
        "domain": (DOMAIN_LO, DOMAIN_HI),
        "grid_points": GRID_POINTS,
        "nearest_root_outside_domain": nearest,
    }


def _proven_no_root_certificate(flows: list[tuple[date, Decimal]]) -> str | None:
    """Analytic proof hook for the METHODOLOGY §7.5.1 fixture pattern.

    NPV for ``-100, +1, -100`` at equally spaced years, with ``x = 1/(1+r)``,
    is ``-100 + x - 100x^2`` whose maximum is negative for every ``x > 0``.
    The hook recognises exactly that quadratic shape: three flows with the
    sign pattern ``-, +, -`` whose quadratic maximum (at the vertex) is
    negative.
    """
    if len(flows) == 3:
        (d0, a0), (d1, a1), (d2, a2) = flows
        if a0 < 0 and a1 > 0 and a2 < 0:
            y1 = Decimal((d1 - d0).days) / Decimal("365")
            y2 = Decimal((d2 - d1).days) / Decimal("365")
            # Reparameterise NPV in x = 1/(1+r): a0 + a1*x^y1 + a2*x^(y1+y2).
            # Only the equally spaced unit-year case matches the fixture.
            if y1 == 1 and y2 == 1:
                # -100 + x - 100x^2 with a0=-100, a1=1, a2=-100 generalised:
                # C + B x + A x^2 where A = a2, B = a1, C = a0.
                vertex_value = a0 - (a1 * a1) / (Decimal("4") * a2)
                # For a2 < 0 the parabola opens downward; maximum at x* = -B/(2A) > 0.
                if vertex_value < 0:
                    return (
                        "NPV maximum is negative for every x > 0 "
                        f"({vertex_value}); no positive-x root exists"
                    )
    return None
