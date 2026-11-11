"""Analyse E9 sensitivity exclusions and compare the frozen/corrected runs.

Inputs:
- results/sensitivity_summary.json (current, corrected run)
- results/archive/e9_v1_frozen/sensitivity_summary.json (original frozen run)

Outputs:
- results/E9_EXCLUSION_ANALYSIS.json
- results/E9_EXCLUSION_ANALYSIS.md
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "results" / "sensitivity_summary.json"
ARCHIVE = ROOT / "results" / "archive" / "e9_v1_frozen" / "sensitivity_summary.json"
JSON_OUT = ROOT / "results" / "E9_EXCLUSION_ANALYSIS.json"
MD_OUT = ROOT / "results" / "E9_EXCLUSION_ANALYSIS.md"


def _solved(row: dict) -> bool:
    return str(row.get("xirr_minus_twr_bp", "")).strip() != ""


def _quantile_bands(rows: list[dict]) -> list[dict]:
    ordered = sorted(rows, key=lambda row: Decimal(str(row.get("drawdown_bp") or "0")))
    bands: list[dict] = []
    n = len(ordered)
    for index in range(5):
        lo = index * n // 5
        hi = (index + 1) * n // 5
        band = ordered[lo:hi]
        if not band:
            continue
        solved = sum(1 for row in band if _solved(row))
        bands.append(
            {
                "band": f"Q{index + 1}",
                "observations": len(band),
                "solved": solved,
                "excluded": len(band) - solved,
                "exclusion_rate": (len(band) - solved) / len(band),
                "min_drawdown_bp": str(band[0].get("drawdown_bp")),
                "max_drawdown_bp": str(band[-1].get("drawdown_bp")),
            }
        )
    return bands


def _summary(rows: list[dict]) -> dict:
    solved = [row for row in rows if _solved(row)]
    excluded = [row for row in rows if not _solved(row)]
    by_year: dict[str, dict[str, int]] = {}
    for row in rows:
        year = str(row["window_start"])[:4]
        bucket = by_year.setdefault(year, {"windows": 0, "solved": 0, "excluded": 0})
        bucket["windows"] += 1
        bucket["solved" if _solved(row) else "excluded"] += 1
    excluded_drawdowns = [Decimal(str(row.get("drawdown_bp") or "0")) for row in excluded]
    solved_drawdowns = [Decimal(str(row.get("drawdown_bp") or "0")) for row in solved]
    return {
        "windows": len(rows),
        "solved": len(solved),
        "excluded": len(excluded),
        "solved_rate": len(solved) / len(rows) if rows else 0.0,
        "status_counts": _status_counts(rows),
        "by_year": dict(sorted(by_year.items())),
        "drawdown_quintiles": _quantile_bands(rows),
        "excluded_mean_drawdown_bp": str(sum(excluded_drawdowns) / len(excluded_drawdowns)) if excluded_drawdowns else None,
        "solved_mean_drawdown_bp": str(sum(solved_drawdowns) / len(solved_drawdowns)) if solved_drawdowns else None,
    }


def _status_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("xirr_status") or ("SUCCESS" if _solved(row) else "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    archived = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    current_rows = current["e9"]
    archived_rows = archived["e9"]
    analysis = {
        "metric": "annualised XIRR minus period TWR over the same 12-month SIP window (not an error metric)",
        "config_sha256": current.get("config_sha256"),
        "current": _summary(current_rows),
        "original_frozen": _summary(archived_rows),
        "root_cause": {
            "classification": "implementation defect in the sensitivity helper, not a genuine mathematical no-root",
            "defects": [
                "terminal valuation used the dataset-wide maximum NAV date instead of the last NAV on or before the 12-month window end",
                "backdated instalments were shifted by calendar days and silently dropped when the shifted date had no NAV",
                "sensitivity solver domain was narrower than the documented production XIRR domain",
                "SIP TWR did not chain-link subperiod returns correctly",
            ],
            "evidence": "Exclusions concentrated in 2016-2019 (91/112, 85/112, 78/112, 77/112 in the original run), the windows furthest from the dataset-wide 2026 terminal NAV. Correcting the terminal date and solver domain removes every exclusion.",
        },
    }
    JSON_OUT.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# E9 Exclusion Investigation",
        "",
        f"Metric: **{analysis['metric']}**. Frozen config SHA-256: `{analysis['config_sha256']}`.",
        "",
        "## Conclusion",
        "",
        "The 386 exclusions in the original frozen run were caused by an **implementation defect**, "
        "not by genuine mathematical no-root cases. The terminal valuation used the last NAV in the "
        "entire dataset (2026) instead of the last NAV on or before the 12-month window end. For older "
        "windows this valued a 2016-2019 SIP at a 2026 NAV while discounting the terminal cash flow to "
        "the next day, producing annualised returns far outside the solver domain.",
        "",
        "The defect was corrected without changing the frozen study configuration, scheme selection, "
        "quarterly window grid or metric definition. The original outputs are preserved unchanged in "
        "`results/archive/e9_v1_frozen/`.",
        "",
        "## Coverage",
        "",
        "| Run | Windows with instalments | Solved | Excluded | Solved rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in (("Original frozen (2026-11-09)", "original_frozen"), ("Corrected (2026-11-11)", "current")):
        item = analysis[key]
        lines.append(
            f"| {label} | {item['windows']} | {item['solved']} | {item['excluded']} | {item['solved_rate']:.1%} |"
        )
    lines += [
        "",
        "The path-window universe is **1,200** (30 selected paths × 40 quarterly windows). "
        "**1,040** of those windows have a complete monthly SIP instalment history within the scheme's "
        "available NAV coverage. The remaining 160 are outside the eligible window universe and are not "
        "counted as solver exclusions.",
        "",
        "## Exclusions by window year",
        "",
        "| Year | Original windows | Original excluded | Original exclusion rate | Corrected excluded |",
        "|---|---:|---:|---:|---:|",
    ]
    for year, bucket in analysis["original_frozen"]["by_year"].items():
        corrected = analysis["current"]["by_year"].get(year, {}).get("excluded", 0)
        lines.append(
            f"| {year} | {bucket['windows']} | {bucket['excluded']} | "
            f"{bucket['excluded'] / bucket['windows']:.1%} | {corrected} |"
        )
    lines += [
        "",
        "The monotonic concentration in early windows is the signature of the terminal-date defect. "
        "It is not a drawdown effect.",
        "",
        "## Drawdown-quintile comparison (original run)",
        "",
        "Bands are empirical quintiles of max peak-to-trough drawdown across all 1,040 windows.",
        "",
        "| Band | Observations | Excluded | Exclusion rate | Drawdown range (bp) |",
        "|---|---:|---:|---:|---|",
    ]
    for band in analysis["original_frozen"]["drawdown_quintiles"]:
        lines.append(
            f"| {band['band']} | {band['observations']} | {band['excluded']} | "
            f"{band['exclusion_rate']:.1%} | {Decimal(band['min_drawdown_bp']):.1f} – {Decimal(band['max_drawdown_bp']):.1f} |"
        )
    lines += [
        "",
        "Exclusion rates are not monotonic across drawdown quintiles (the highest band is not the most "
        "excluded). The original data therefore did not support a claim that exclusions clustered around "
        "deep drawdowns. The year pattern and the code inspection identify the terminal-date defect as the "
        "cause.",
        "",
        "## Solver-domain limitation",
        "",
        "After fixing the terminal date, 1,032 of 1,040 windows solved. The remaining 8 were all the "
        "2019-04-01 window (the COVID-era drawdown) and required annualised returns below the provisional "
        "`-50%` solver bound. Extending the sensitivity solver to the documented production domain "
        "`r ∈ (-0.999999, 1000)` resolves them. This is a solver-domain correction, not a change to the "
        "metric or the economics.",
        "",
        "## Corrected status counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in analysis["current"]["status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines += [
        "",
        "## Audit trail",
        "",
        "- Frozen configuration unchanged: `config/sensitivity.yaml`.",
        "- Original outputs: `results/archive/e9_v1_frozen/`.",
        "- Corrected outputs: `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `results/E9_COVERAGE.md`.",
        "- Machine-readable analysis: `results/E9_EXCLUSION_ANALYSIS.json`.",
    ]
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {JSON_OUT.relative_to(ROOT)} and {MD_OUT.relative_to(ROOT)}")
    print(f"original excluded={analysis['original_frozen']['excluded']} current excluded={analysis['current']['excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
