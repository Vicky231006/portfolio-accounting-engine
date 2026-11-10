"""Allotment and posting derivations (M3, D-045).

Posting computations only: given an instruction and the allotment NAVs,
derive units/proceeds/cash legs per METHODOLOGY §2.1–§2.3 / §3.3–§3.6.
No portfolio valuation and no return calculation happens here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Derived:
    """Derived posting quantities for one transaction instruction."""

    units: Decimal | None
    proceeds: Decimal | None
    actual_cash: Decimal | None
    residual: Decimal | None


def quant_units(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_DOWN)


def quant_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def purchase_units(amount: Decimal, nav: Decimal) -> Decimal:
    """Units for an amount-instructed purchase (ROUND_DOWN, D-026)."""
    if nav <= 0:
        raise ValueError("NAV must be positive")
    return quant_units(amount / nav)


def purchase_actual_cash(units: Decimal, nav: Decimal) -> Decimal:
    return quant_amount(units * nav)


def redemption_proceeds(units: Decimal, nav: Decimal) -> Decimal:
    return quant_amount(units * nav)


def switch_derived(units_out: Decimal, source_nav: Decimal, target_nav: Decimal) -> Derived:
    """Switch derivation with non-negative residual (METHODOLOGY §3.5)."""
    proceeds = redemption_proceeds(units_out, source_nav)
    units_target = purchase_units(proceeds, target_nav)
    target_cost = purchase_actual_cash(units_target, target_nav)
    while target_cost > proceeds and units_target > 0:
        units_target -= Decimal("0.001")
        target_cost = purchase_actual_cash(units_target, target_nav)
    residual = proceeds - target_cost
    if residual < 0:
        raise ValueError("Switch residual must be non-negative")
    return Derived(units=units_target, proceeds=proceeds, actual_cash=target_cost, residual=residual)
