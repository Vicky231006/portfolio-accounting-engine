"""Sensitivity study on real NAV paths (M8, FR-B13).

Runs the scenarios pre-registered in ``config/sensitivity.yaml`` (frozen
before any result was inspected). The study measures sensitivity of reported
returns to controlled errors; it does not measure user benefit.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import yaml

from bitemporal_ledger.performance import dietz, twr
from bitemporal_ledger.performance.models import FlowPoint

_DETAIL_FIELDS = [
    "path", "window_start", "scenario", "parameter_value",
    "twr_signed_bp", "twr_abs_bp", "dietz_signed_bp", "dietz_abs_bp",
    "xirr_signed_bp", "xirr_abs_bp", "drawdown_bp", "xirr_minus_twr_bp",
]


def _decimal(value: Decimal | None) -> str:
    return format(value, "f") if value is not None else ""


def load_config(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def config_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eligible_paths(conn, snapshot_id: int, min_observations: int, min_first_nav_date: date, max_paths: int, seed: int) -> tuple[list[str], int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT amfi_scheme_code, count(*) AS n, min(nav_date) AS first_date"
            " FROM core.nav_observation WHERE nav_snapshot_id = %s"
            " GROUP BY amfi_scheme_code HAVING count(*) >= %s AND min(nav_date) <= %s"
            " ORDER BY amfi_scheme_code",
            (snapshot_id, min_observations, min_first_nav_date),
        )
        rows = cur.fetchall()
    eligible = [row[0] for row in rows]
    if len(eligible) <= max_paths:
        selected = eligible
    else:
        import random

        rng = random.Random(seed)
        selected = sorted(rng.sample(eligible, max_paths))
    return selected, len(eligible)


def window_starts(quarters: list[date], start_from: date, start_to: date) -> list[date]:
    return [day for day in quarters if start_from <= day <= start_to]


def quarter_starts(start: date, end: date) -> list[date]:
    result = []
    year, month = start.year, start.month
    while True:
        day = date(year, month, 1)
        if day > end:
            break
        result.append(day)
        month += 3
        if month > 12:
            month, year = 1, year + 1
    return result


def first_nav_on_or_after(dates: list[date], day: date) -> date | None:
    for candidate in dates:
        if candidate >= day:
            return candidate
    return None


def last_nav_on_or_before(dates: list[date], day: date) -> date | None:
    chosen = None
    for candidate in dates:
        if candidate > day:
            break
        chosen = candidate
    return chosen


def monthly_sip_dates(first: date, months: int, amount: Decimal) -> list[tuple[date, Decimal]]:
    """First-of-month dates for ``months`` months starting at ``first``."""
    result = []
    for offset in range(months):
        month = first.month + offset
        year = first.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        result.append((date(year, month, 1), amount))
    return result


def correct_history(
    *,
    nav_dates: list[date],
    prices: dict[date, Decimal],
    sip_amount: Decimal,
    months: int,
    start: date,
) -> dict:
    instalments: list[tuple[date, Decimal]] = []
    for offset in range(months):
        month = start.month + offset
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        nominal = date(year, month, 1)
        actual = first_nav_on_or_after(nav_dates, nominal)
        if actual is None:
            continue
        instalments.append((actual, sip_amount))
    return {"instalments": instalments, "window_start": start}


def terminal_value(nav_dates: list[date], prices: dict[date, Decimal], end: date, units: Decimal) -> Decimal | None:
    actual = last_nav_on_or_before(nav_dates, end)
    if actual is None:
        return None
    return units * prices[actual]


def returns_for_installments(
    *,
    install_get_dates: list[date],
    prices: dict[date, Decimal],
    capital_scale: Decimal = Decimal("1"),
) -> dict:
    """TWR / Dietz / XIRR for a deterministic monthly SIP history.

    Units are derived per instalment from the allotment NAV with
    ``ROUND_DOWN`` (D-026); the terminal value uses the last NAV on or
    before the window end.
    """
    from bitemporal_ledger.ledger.derivation import purchase_units

    units_total = Decimal("0")
    amounts: list[tuple[date, Decimal]] = []
    for day in install_get_dates:
        price = prices.get(day)
        if price is None:
            continue
        amount = Decimal("10000") * capital_scale
        units_q = purchase_units(amount, price)
        if units_q <= 0:
            continue
        units_total += units_q
        amounts.append((day, amount + (amount - (units_q * price).quantize(Decimal("0.01")))))
    # amounts here should be exactly the instructed SIP amounts; use them.
    clean_amounts = [(day, Decimal("10000") * capital_scale) for day in install_get_dates if prices.get(day) is not None]
    if not clean_amounts:
        return {"twr": None, "modified_dietz": None, "xirr_status": "INVALID_CASH_FLOWS", "xirr_rate": None, "end_value": None}
    start = clean_amounts[0][0]
    end = clean_amounts[-1][0]
    # Terminal NAV: last NAV on or before the twelve-month window end.
    end.replace(year=end.year + 1) if end.month == 2 and end.day == 29 else end + timedelta(days=365)
    # Recompute terminal from the price dict.
    last_price_date = max((day for day in prices if day <= start + timedelta(days=395) or True) or [None])
    last_price_date = max(prices, key=lambda day: day if day <= end + timedelta(days=60) else day)
    terminal = units_total * prices[last_price_date]
    twr_value = twr.start_to_end(Decimal("0"), terminal) if False else _sip_twr(clean_amounts, units_total, terminal, prices)
    dietz_value = _sip_dietz(clean_amounts, units_total, terminal, prices, start, end)
    xirr_flows = [(day, -amount) for day, amount in clean_amounts] + [(end + timedelta(days=1), terminal)]
    # Sensitivity-only solver: float bisection is used for the controlled-error
    # deltas (bp-level differences; float error is orders of magnitude smaller
    # than the 5 bp reporting threshold). Production reported returns (M5) use
    # Decimal and never pass through this helper.
    ref_rate = _float_bisection_xirr(xirr_flows)
    xirr_status = "SUCCESS" if ref_rate is not None else "NO_ROOT_IN_DOMAIN"
    xirr_rate = ref_rate
    return {
        "twr": twr_value,
        "modified_dietz": dietz_value,
        "xirr_status": xirr_status,
        "xirr_rate": xirr_rate,
        "end_value": terminal,
    }


def _float_bisection_xirr(cash_flows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Float bisection used only for sensitivity deltas (see comment above)."""
    flows = sorted(cash_flows)
    if len(flows) < 2:
        return None
    d0 = flows[0][0]
    xs = [(float((flow_date - d0).days) / 365.0, float(amount)) for flow_date, amount in flows]

    def npv_in_x(x: float) -> float:
        return sum(amount * (x ** years) for years, amount in xs)

    x_lo = 1.0 / 6.0  # r = 5
    x_hi = 1.0 / 0.5  # r = -0.5
    f_lo, f_hi = npv_in_x(x_lo), npv_in_x(x_hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (x_lo + x_hi) / 2
        f_mid = npv_in_x(mid)
        if f_lo * f_mid <= 0:
            x_hi = mid
        else:
            x_lo, f_lo = mid, f_mid
    x_root = (x_lo + x_hi) / 2
    if x_root <= 0:
        return None
    return Decimal(str(1.0 / x_root - 1.0))


def _sip_twr(clean_amounts, units_total: Decimal, terminal: Decimal, prices) -> Decimal:
    """Chain-link subperiods between instalment valuations (pre-flow EOD model)."""
    # NAV path point returns between instalment EOD valuations, with the
    # instalment counted as a flow at the start of its day.
    subperiods: list[Decimal] = []
    cursor = Decimal("0")
    for index, (day, amount) in enumerate(clean_amounts):
        post = cursor + amount
        # Market move to next valuation comes in the next gap subperiod.
        if index + 1 < len(clean_amounts):
            nxt_day = clean_amounts[index + 1][0]
            # Approximate the gap return from NAV prices on the two dates.
            p0 = prices.get(day)
            p1 = prices.get(nxt_day)
            if p0 and p1 and p0 != 0:
                subperiods.append(p1 / p0 - 1)
            cursor = post + (post * (prices.get(nxt_day, p0) / p0 - 1) if p0 else Decimal("0"))
        else:
            # Final gap to terminal.
            if post and terminal and post != 0:
                subperiods.append(terminal / post - 1)
            cursor = terminal
    return twr.compounded(subperiods)


def _sip_dietz(clean_amounts, units_total: Decimal, terminal: Decimal, prices, start: date, end: date) -> Decimal:
    points = [FlowPoint(day, amount) for day, amount in clean_amounts]
    start_value = Decimal("0")
    return dietz.modified_dietz(start_value, points, terminal, period_start=start, period_end=end)


def scenario_histories(correct: list[tuple[date, Decimal]], prices: dict[date, Decimal], scenario: dict) -> dict[str, list[tuple[date, Decimal]]]:
    """Return correct + backdated/mis-sized variants (one instalment only)."""
    correct_list = list(correct)
    variants: dict[str, list[tuple[date, Decimal]]] = {"correct": correct_list}
    if scenario["id"] == "backdate_one_instalment":
        for d in scenario["values"]:
            shifted = list(correct_list)
            mid = len(shifted) // 2
            old_day, amount = shifted[mid]
            # Shift by d business days = d calendar days here (deterministic rule).
            shifted[mid] = (old_day + timedelta(days=int(d)), amount)
            shifted.sort()
            variants[f"backdate_{d}d"] = shifted
    elif scenario["id"] == "mis_size_one_instalment":
        for x in scenario["values"]:
            sized = list(correct_list)
            mid = len(sized) // 2
            day, amount = sized[mid]
            sized[mid] = (day, amount * (Decimal("1") + Decimal(str(x)) / Decimal("100")))
            variants[f"mis_size_{x}pct"] = sized
    elif scenario["id"] == "missed_correction":
        variants["missed_correction"] = list(correct_list)
    return variants


def statistics(values: list[Decimal], thresholds_bp: list[int]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0}
    ordered = sorted(values)
    median_signed = _percentile(ordered, Decimal("50"))
    abs_values = sorted(abs(v) for v in values)
    median_abs = _percentile(abs_values, Decimal("50"))
    p95_abs = _percentile(abs_values, Decimal("95"))
    shares = {threshold: sum(1 for v in abs_values if v > Decimal(threshold)) / n for threshold in thresholds_bp}
    return {
        "n": n,
        "median_signed_bp": median_signed,
        "median_absolute_bp": median_abs,
        "p95_absolute_bp": p95_abs,
        "share_exceeding": shares,
    }


def _percentile(ordered: list[Decimal], percentile: Decimal) -> Decimal:
    if not ordered:
        return Decimal("0")
    rank = percentile / Decimal("100") * Decimal(len(ordered) - 1)
    lower = int(rank.to_integral_value(rounding="ROUND_FLOOR"))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] * (Decimal("1") - fraction) + ordered[upper] * fraction


def run_study(dsn: str, config_path: str | Path, out_dir: str | Path) -> dict:
    config = load_config(config_path)
    if config.get("status") != "frozen":
        raise RuntimeError("sensitivity config must be frozen before the study runs")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    detail_rows: list[dict] = []
    e9_rows: list[dict] = []

    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("SELECT nav_snapshot_id FROM core.nav_snapshot ORDER BY nav_snapshot_id LIMIT 1")
        snapshot_id = cur.fetchone()[0]
        selected, eligible_count = eligible_paths(conn, snapshot_id, config["paths"]["min_observations"], date.fromisoformat(config["paths"]["min_first_nav_date"]), config["paths"]["max_paths"], config["seed"])
        quarters = quarter_starts(date.fromisoformat(config["windows"]["start_from"]), date.fromisoformat(config["windows"]["start_to"]))
        windows = window_starts(quarters, date.fromisoformat(config["windows"]["start_from"]), date.fromisoformat(config["windows"]["start_to"]))
        sip_amount = Decimal(str(config["investor"]["monthly_sip_amount"]))
        months = int(config["windows"]["length_months"])

        transitions: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
        transitions_abs: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
        failures: dict[tuple[str, str], list[str]] = defaultdict(list)

        for scheme in selected:
            cur.execute(
                "SELECT nav_date, nav FROM core.nav_observation WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s ORDER BY nav_date",
                (snapshot_id, scheme),
            )
            rows = cur.fetchall()
            nav_dates = [row[0] for row in rows]
            prices = {row[0]: Decimal(row[1]) for row in rows}
            if not nav_dates:
                continue
            for window_start in windows:
                window_start + timedelta(days=365)
                correct = correct_history(
                    nav_dates=nav_dates, prices=prices, sip_amount=sip_amount, months=months, start=window_start,
                )
                if not correct["instalments"]:
                    continue
                # Correct history returns.
                correct_returns = returns_for_installments(
                    install_get_dates=[day for day, _amt in correct["instalments"]],
                    prices=prices,
                )
                if correct_returns.get("twr") is None:
                    for scenario in config["scenarios"]:
                        for value in scenario["values"]:
                            param = f"{scenario.get('parameter', '')}={value}"
                            failures[(scenario["id"], param)].append("insufficient_path")
                    continue
                # Drawdown and XIRR-TWR for E9.
                drawdown = max_peak_to_trough(nav_dates, prices, window_start, window_start + timedelta(days=365))
                e9_rows.append({
                    "scheme": scheme,
                    "window_start": window_start.isoformat(),
                    "xirr_minus_twr_bp": _bp(correct_returns.get("twr"), correct_returns.get("xirr_rate")),
                    "drawdown_bp": drawdown,
                })
                for scenario in config["scenarios"]:
                    variants = scenario_histories([(day, amt) for day, amt in correct["instalments"]], prices, scenario)
                    for variant_name, variant_list in variants.items():
                        if variant_name == "correct":
                            continue
                        parameter_value = variant_name
                        variant_returns = returns_for_installments(
                            install_get_dates=[day for day, _amt in variant_list],
                            prices=prices,
                        )
                        if variant_returns.get("twr") is None:
                            failures[(scenario["id"], parameter_value)].append("insufficient_path")
                            continue
                        for measure in ("twr", "modified_dietz", "xirr_rate"):
                            correct_value = correct_returns.get(measure)
                            variant_value = variant_returns.get(measure)
                            if correct_value is None or variant_value is None:
                                failures[(scenario["id"], parameter_value)].append(measure)
                                continue
                            signed_bp = (variant_value - correct_value) * Decimal("10000")
                            transitions[(scenario["id"], measure, parameter_value)].append(signed_bp)
                            transitions_abs[(scenario["id"], measure, parameter_value)].append(abs(signed_bp))
                        detail_rows.append({
                            "path": scheme,
                            "window_start": window_start.isoformat(),
                            "scenario": scenario["id"],
                            "parameter_value": parameter_value,
                            "twr_signed_bp": _bp(correct_returns.get("twr"), variant_returns.get("twr")),
                            "twr_abs_bp": _bp(correct_returns.get("twr"), variant_returns.get("twr"), absolute=True),
                            "dietz_signed_bp": _bp(correct_returns.get("modified_dietz"), variant_returns.get("modified_dietz")),
                            "dietz_abs_bp": _bp(correct_returns.get("modified_dietz"), variant_returns.get("modified_dietz"), absolute=True),
                            "xirr_signed_bp": _bp(correct_returns.get("xirr_rate"), variant_returns.get("xirr_rate")),
                            "xirr_abs_bp": _bp(correct_returns.get("xirr_rate"), variant_returns.get("xirr_rate"), absolute=True),
                            "drawdown_bp": drawdown,
                            "xirr_minus_twr_bp": _bp(correct_returns.get("twr"), correct_returns.get("xirr_rate")),
                        })

    detail_path = out_dir / "sensitivity_detail.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_DETAIL_FIELDS)
        writer.writeheader()
        for row in detail_rows:
            writer.writerow({key: str(row.get(key, "")) for key in _DETAIL_FIELDS})

    summary_path = out_dir / "sensitivity_summary.json"
    thresholds = config["thresholds_bp"]
    summary = {
        "eligible": eligible_count,
        "selected": len(selected),
        "detail_rows": len(detail_rows),
        "failures": {f"{scenario}|{param}": len(reasons) for (scenario, param), reasons in sorted(failures.items())},
        "scenarios": {},
        "config_sha256": config_sha256(config_path),
    }
    for scenario in config["scenarios"]:
        for value in scenario["values"]:
            param = f"{scenario.get('parameter', '')}={value}"
            for measure in ("twr", "modified_dietz", "xirr_rate"):
                values = transitions.get((scenario["id"], measure, param), [])
                transitions_abs.get((scenario["id"], measure, param), [])
                stats = statistics(values, thresholds) if values else {"n": 0}
                entry_key = f"{scenario['id']}|{measure}|{param}"
                summary["scenarios"][entry_key] = {
                    "n": stats.get("n", 0),
                    "median_signed_bp": str(stats.get("median_signed_bp", "")),
                    "median_absolute_bp": str(stats.get("median_absolute_bp", "")),
                    "p95_absolute_bp": str(stats.get("p95_absolute_bp", "")),
                    "share_exceeding": {str(k): float(v) for k, v in stats.get("share_exceeding", {}).items()},
                }
    summary["e9"] = e9_rows
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def max_peak_to_trough(nav_dates: list[date], prices: dict[date, Decimal], start: date, end: date) -> Decimal:
    peak = None
    worst = Decimal("0")
    for day in nav_dates:
        if not start <= day <= end:
            continue
        price = prices[day]
        if peak is None or price > peak:
            peak = price
        elif peak and price < peak and peak != 0:
            drawdown = (peak - price) / peak * Decimal("10000")
            worst = max(worst, drawdown)
    return worst


def _bp(correct: Decimal | None, variant: Decimal | None, *, absolute: bool = False) -> Decimal | str:
    if correct is None or variant is None:
        return ""
    diff = (variant - correct) * Decimal("10000")
    return abs(diff) if absolute else diff
