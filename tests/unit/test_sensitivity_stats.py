"""Sensitivity statistics and pre-registration tests (M8, D-022/D-031)."""

from __future__ import annotations

from decimal import Decimal

from bitemporal_ledger.evaluation.sensitivity import statistics


def test_statistics_report_signed_and_absolute() -> None:
    values = [Decimal("-10"), Decimal("-5"), Decimal("0"), Decimal("5"), Decimal("10")]
    stats = statistics(values, [5, 10])
    assert stats["n"] == 5
    assert stats["median_signed_bp"] == Decimal("0")
    assert stats["median_absolute_bp"] == Decimal("5")
    assert stats["p95_absolute_bp"] == Decimal("10")
    assert stats["share_exceeding"][5] == 0.4  # |x| > 5 strictly: +-10 only


def test_statistics_empty() -> None:
    assert statistics([], [5]) == {"n": 0}


def test_statistics_percentile_interpolates() -> None:
    values = [Decimal("0"), Decimal("10")]
    stats = statistics(values, [100])
    assert stats["median_signed_bp"] == Decimal("5.000000000000000000000000000000")
    assert stats["p95_absolute_bp"] == Decimal("9.5")
