"""Sensitivity study on real NAV paths (M8, FR-B13).

Runs the scenarios pre-registered in ``config/sensitivity.yaml`` (frozen
before any result was inspected). The study measures sensitivity of reported
returns to controlled errors; it does not measure user benefit.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
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

# Sensitivity-only solver domain. This matches the documented production XIRR
# domain (METHODOLOGY §7.1) rather than the narrower provisional domain used by
# the superseded 2026-11-09 run.
SENSITIVITY_DOMAIN_LO = Decimal("-0.999999")
SENSITIVITY_DOMAIN_HI = Decimal("1000")


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


def add_months(start: date, months: int) -> date:
    """Calendar month arithmetic with end-of-month clamping."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def returns_for_installments(
    *,
    install_get_dates: list[date],
    prices: dict[date, Decimal],
    window_end: date,
    capital_scale: Decimal = Decimal("1"),
) -> dict:
    """TWR / Dietz / XIRR for a deterministic monthly SIP history.

    Every variant is valued at the **same** terminal NAV date: the last NAV on
    or before the 12-month window end, matching the frozen study rule
    ``terminal_valuation: last_available_nav_on_or_before_window_end``.

    Units are derived per instalment from the allotment NAV with ``ROUND_DOWN``
    (D-026). TWR chain-links the NAV subperiod returns between instalments and
    the terminal valuation date. The sensitivity-only XIRR solver uses the same
    documented domain as the production solver (``r in (-0.999999, 1000)``).
    """
    from bitemporal_ledger.ledger.derivation import purchase_units

    nav_dates = sorted(prices)
    terminal_date = last_nav_on_or_before(nav_dates, window_end)
    if terminal_date is None:
        return {
            "twr": None,
            "modified_dietz": None,
            "xirr_status": "NO_TERMINAL_NAV",
            "xirr_rate": None,
            "end_value": None,
            "terminal_nav_date": None,
            "window_end": window_end,
        }

    clean_amounts = [
        (day, Decimal("10000") * capital_scale)
        for day in install_get_dates
        if prices.get(day) is not None and day <= terminal_date
    ]
    if not clean_amounts:
        return {
            "twr": None,
            "modified_dietz": None,
            "xirr_status": "INVALID_CASH_FLOWS",
            "xirr_rate": None,
            "end_value": None,
            "terminal_nav_date": terminal_date,
            "window_end": window_end,
        }

    units_total = Decimal("0")
    for day, amount in clean_amounts:
        price = prices[day]
        units_q = purchase_units(amount, price)
        if units_q <= 0:
            continue
        units_total += units_q

    terminal = units_total * prices[terminal_date]
    twr_value = _sip_twr([day for day, _amount in clean_amounts], prices, terminal_date)
    dietz_value = _sip_dietz(clean_amounts, terminal, terminal_date)
    xirr_flows = [(day, -amount) for day, amount in clean_amounts] + [(terminal_date, terminal)]
    # Sensitivity-only solver: float bisection is used for the controlled-error
    # deltas (bp-level differences; float error is orders of magnitude smaller
    # than the 5 bp reporting threshold). Production reported returns (M5) use
    # Decimal and never pass through this helper.
    ref_rate = _bisection_xirr(xirr_flows)
    xirr_status = "SUCCESS" if ref_rate is not None else "NO_ROOT_IN_DOMAIN"
    return {
        "twr": twr_value,
        "modified_dietz": dietz_value,
        "xirr_status": xirr_status,
        "xirr_rate": ref_rate,
        "end_value": terminal,
        "terminal_nav_date": terminal_date,
        "window_end": window_end,
    }


def _bisection_xirr(cash_flows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Float bisection over the documented XIRR domain.

    Solving in ``u = ln(x)`` with ``x = 1/(1+r)`` keeps the search numerically
    stable over the full production domain, including deeply negative annualised
    returns. Sign changes are bracketed on the domain boundary; no root returns
    ``None`` and is reported as ``NO_ROOT_IN_DOMAIN``.
    """
    flows = sorted(cash_flows)
    if len(flows) < 2:
        return None
    if not (any(amount > 0 for _day, amount in flows) and any(amount < 0 for _day, amount in flows)):
        return None
    d0 = flows[0][0]
    xs = [(float((flow_date - d0).days) / 365.0, float(amount)) for flow_date, amount in flows]

    def npv_in_u(u: float) -> float:
        x = math.exp(u)
        return sum(amount * (x ** years) for years, amount in xs)

    u_lo = math.log(1.0 / float(1 + SENSITIVITY_DOMAIN_HI))  # r = +1000
    u_hi = math.log(1.0 / float(1 + SENSITIVITY_DOMAIN_LO))  # r -> -1
    f_lo, f_hi = npv_in_u(u_lo), npv_in_u(u_hi)
    if f_lo == 0:
        x_root = math.exp(u_lo)
        return Decimal(str(1.0 / x_root - 1.0))
    if f_hi == 0:
        x_root = math.exp(u_hi)
        return Decimal(str(1.0 / x_root - 1.0))
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (u_lo + u_hi) / 2
        f_mid = npv_in_u(mid)
        if f_lo * f_mid <= 0:
            u_hi = mid
        else:
            u_lo, f_lo = mid, f_mid
    x_root = math.exp((u_lo + u_hi) / 2)
    if x_root <= 0:
        return None
    return Decimal(str(1.0 / x_root - 1.0))


def _sip_twr(flow_dates: list[date], prices: dict[date, Decimal], terminal_date: date) -> Decimal:
    """Chain-link NAV subperiod returns between instalments and terminal date."""
    dates = sorted(day for day in flow_dates if day <= terminal_date)
    if not dates:
        raise ValueError("TWR requires at least one flow date")
    if dates[-1] != terminal_date:
        dates.append(terminal_date)
    subperiods: list[Decimal] = []
    for earlier, later in zip(dates, dates[1:]):
        p0 = prices[earlier]
        p1 = prices[later]
        if p0 <= 0:
            raise ValueError("NAV must be positive")
        subperiods.append(p1 / p0 - 1)
    if not subperiods:
        return Decimal("0")
    return twr.compounded(subperiods)


def _sip_dietz(clean_amounts, terminal: Decimal, period_end: date) -> Decimal:
    points = [FlowPoint(day, amount) for day, amount in clean_amounts]
    start_value = Decimal("0")
    return dietz.modified_dietz(
        start_value,
        points,
        terminal,
        period_start=clean_amounts[0][0],
        period_end=period_end,
    )


def _shift_business_days(day: date, business_days: int) -> date:
    """Shift by whole weekdays (no exchange-holiday calendar)."""
    remaining = abs(business_days)
    step = 1 if business_days >= 0 else -1
    while remaining:
        day = day + timedelta(days=step)
        if day.weekday() < 5:
            remaining -= 1
    return day


def scenario_histories(correct: list[tuple[date, Decimal]], prices: dict[date, Decimal], scenario: dict) -> dict[str, list[tuple[date, Decimal]]]:
    """Return correct + backdated/mis-sized variants (one instalment only)."""
    correct_list = list(correct)
    nav_dates = sorted(prices)
    variants: dict[str, list[tuple[date, Decimal]]] = {"correct": correct_list}
    if scenario["id"] == "backdate_one_instalment":
        for d in scenario["values"]:
            shifted = list(correct_list)
            mid = len(shifted) // 2
            old_day, amount = shifted[mid]
            nominal = _shift_business_days(old_day, int(d))
            # The shifted SIP is allotted at the first available NAV on or after
            # the shifted business date. It must not silently disappear when the
            # nominal date falls on a weekend or holiday.
            allotment = first_nav_on_or_after(nav_dates, nominal)
            if allotment is None:
                continue
            shifted[mid] = (allotment, amount)
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
                window_end = add_months(window_start, months)
                correct = correct_history(
                    nav_dates=nav_dates, prices=prices, sip_amount=sip_amount, months=months, start=window_start,
                )
                if not correct["instalments"]:
                    continue
                # Correct history returns, valued at the same terminal date as
                # every scenario variant.
                correct_returns = returns_for_installments(
                    install_get_dates=[day for day, _amt in correct["instalments"]],
                    prices=prices,
                    window_end=window_end,
                )
                if correct_returns.get("twr") is None:
                    for scenario in config["scenarios"]:
                        for value in scenario["values"]:
                            param = f"{scenario.get('parameter', '')}={value}"
                            failures[(scenario["id"], param)].append("insufficient_path")
                    continue
                # Drawdown and XIRR-TWR for E9.
                drawdown = max_peak_to_trough(nav_dates, prices, window_start, window_end)
                e9_rows.append({
                    "scheme": scheme,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "terminal_nav_date": (
                        correct_returns["terminal_nav_date"].isoformat()
                        if correct_returns.get("terminal_nav_date") is not None
                        else None
                    ),
                    "xirr_status": correct_returns.get("xirr_status"),
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
                            window_end=window_end,
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
    # Statistics are aggregated from the measured transitions themselves, keyed by
    # (scenario, measure, parameter_value), so reported n/median/p95/share are always
    # consistent with the rows that were actually computed (never a fabricated n=0).
    for (scenario_id, measure, parameter_value), values in sorted(transitions.items()):
        if not values:
            continue
        stats = statistics(values, thresholds)
        summary["scenarios"][f"{scenario_id}|{measure}|{parameter_value}"] = {
            "n": stats.get("n", 0),
            "median_signed_bp": str(stats.get("median_signed_bp", "")),
            "median_absolute_bp": str(stats.get("median_absolute_bp", "")),
            "p95_absolute_bp": str(stats.get("p95_absolute_bp", "")),
            "share_exceeding": {str(k): float(v) for k, v in stats.get("share_exceeding", {}).items()},
        }
    summary["e9"] = e9_rows
    solved_rows = [row for row in e9_rows if str(row.get("xirr_minus_twr_bp", "")).strip() != ""]
    excluded_rows = [row for row in e9_rows if str(row.get("xirr_minus_twr_bp", "")).strip() == ""]
    status_counts = Counter(str(row.get("xirr_status")) for row in e9_rows)
    summary["e9_coverage"] = {
        "eligible_schemes": eligible_count,
        "selected_paths": len(selected),
        "quarter_windows": len(windows),
        "path_window_universe": len(selected) * len(windows),
        "windows_with_instalments": len(e9_rows),
        "solved": len(solved_rows),
        "excluded": len(excluded_rows),
        "solved_rate": (len(solved_rows) / len(e9_rows)) if e9_rows else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "solver_domain": [str(SENSITIVITY_DOMAIN_LO), str(SENSITIVITY_DOMAIN_HI)],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_e9_coverage(summary, out_dir / "E9_COVERAGE.md")
    return summary


def write_e9_coverage(summary: dict, out_path: str | Path) -> None:
    coverage = summary.get("e9_coverage", {})
    rows = summary.get("e9", [])
    by_year: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        year = str(row["window_start"])[:4]
        by_year[year][0 if str(row.get("xirr_minus_twr_bp", "")).strip() != "" else 1] += 1
    lines = [
        "# E9 Coverage — Sensitivity Study",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Frozen config | `config/sensitivity.yaml` status `frozen`; SHA-256 `{summary['config_sha256']}` |",
        f"| Eligible schemes | {coverage.get('eligible_schemes', '')} (`min_observations >= 750`, first NAV `<= 2014-01-01`) |",
        f"| Selected paths | {coverage.get('selected_paths', '')} (`max_paths: 30`) |",
        f"| Quarter windows | {coverage.get('quarter_windows', '')} |",
        f"| Path-window universe | {coverage.get('path_window_universe', '')} (selected paths × quarter windows) |",
        f"| Windows with SIP instalments | **{coverage.get('windows_with_instalments', 0)}** |",
        f"| Solved (XIRR gap present) | **{coverage.get('solved', 0)}** |",
        f"| Excluded (no XIRR root in documented domain) | **{coverage.get('excluded', 0)}** |",
        f"| Solved rate | {coverage.get('solved_rate', 0.0):.1%} |",
        f"| Solver domain | `r ∈ ({SENSITIVITY_DOMAIN_LO}, {SENSITIVITY_DOMAIN_HI})` |",
        f"| Detail rows | {summary.get('detail_rows', '')} |",
        "",
        "## Status breakdown (E9 rows)",
        "",
        "| Status | Count | Share |",
        "|---|---|---|",
    ]
    total = max(coverage.get("windows_with_instalments", 0), 1)
    for status, count in coverage.get("status_counts", {}).items():
        lines.append(f"| `{status}` | {count} | {count / total:.1%} |")
    lines += [
        "",
        "## Solved / excluded by window year",
        "",
        "| Window year | Windows | Solved | Excluded |",
        "|---|---:|---:|---:|",
    ]
    for year in sorted(by_year):
        solved, excluded = by_year[year]
        lines.append(f"| {year} | {solved + excluded} | {solved} | {excluded} |")
    lines += [
        "",
        "## Sample size used for the analysis",
        "",
        f"- **n = {coverage.get('solved', 0)}** for the XIRR-minus-TWR versus drawdown analysis.",
        f"- Drawdown alone has n = {coverage.get('windows_with_instalments', 0)}.",
        "",
        "## Qualification",
        "",
        "No E9 distribution is claimed on the full path-window universe unless every "
        "eligible window has a valid root. Excluded rows remain in "
        "`results/sensitivity_detail.csv` with blank XIRR fields and are counted in "
        "the summary `failures` map; they are never averaged away.",
        "",
        "The metric is **annualised XIRR minus period TWR over the same 12-month SIP "
        "window**. It compares two different return measures and is not an error metric.",
        "",
    ]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


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
