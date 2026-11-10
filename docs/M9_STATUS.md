# M9 Status (Power BI / Dashboard)

**Date:** 2026-11-10 (frozen by Vicky)  
**Status:** **Visually accepted (frozen).** M9 visual design is accepted. The E9 drawdown-quintile bar chart is the final chosen alternative to the scatter plot. **No further layout, styling, chart, or visual iterations.** Preserve the current PBIP report. Only fix a reported Desktop rendering error if needed.

## Final acceptance / freeze
- **Decision (Vicky, 2026-11-10):** Freeze the Power BI dashboard. M9 visually accepted. Proceed to M10 final release verification only.
- **PBIP preserved:** `dashboard/PortfolioReport/Workbook.pbip` (PostgreSQL-only, `localhost:5434` / `bitemporal_ledger`, 4 pages, 42 visuals). Model/marts include Page 4 E9 quintile correction (`marts.sensitivity_e9_quintiles`, `SensitivityE9Quintiles`, `a4s1` bar + `a4t1` table) — presentation-only; no M8/config/financial/methodology changes.
- **Final screenshots (saved in repo):** `docs/screenshots/page1_overview.png`, `docs/screenshots/page2_drilldown.png`, `docs/screenshots/page3_restatements.png`, `docs/screenshots/page4_sensitivity.png` (also copied as `page2_account_drilldown.png`, `page3_restatements_audit.png` for naming convenience). **Desktop-captured finality/refresh against current model must be confirmed by Vicky** (this environment cannot render Power BI Desktop).
- **Frozen M8 preserved:** `config/sensitivity.yaml` SHA-256 `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`; `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `results/E9_COVERAGE.md` unchanged.

## Page 4 E9 (final, validated in-repo/DB)
- Replaced unreliable scatter with **“XIRR–TWR Difference by Drawdown Band”** (bar `a4s1`) + supporting table `a4t1` (no grand total). No scatter plot.
- **Source:** `marts.sensitivity_e9`, 654 solved observations (386 no-root/unsolved excluded). Fields `observation_key`, `drawdown_bp`, `xirr_minus_twr_bp` (sign preserved).
- **Deterministic quintiles:** 5 ordered bands Q1–Q5 by `drawdown_bp` (sorted `drawdown_bp ASC, observation_key ASC`; split indices `ceil(n*i/5)-1`). **Tie-handling:** identical `drawdown_bp` kept in same band (earliest initial band for that value); no value split. **Counts:** Q1=131, Q2=131, Q3=131, Q4=131, Q5=130 (sum 654, each once, 654 distinct).
- **Metrics (per band, from underlying observations):** n, min/max/median drawdown (bp), median signed XIRR−TWR (bp, primary), median |XIRR−TWR| (bp), P95 |XIRR−TWR| (bp). Per-band stats independently recomputed from detail and match quintile table exactly.
- **~6,000–9,000 bp medians (investigated, no methodology change):** `xirr_minus_twr_bp = (xirr_rate - twr)*10000` over the same 12-month SIP window/inputs. TWR = chained **period** return; XIRR = **annualised** money-weighted rate (actual/365) — reported gap is **annualised XIRR minus period TWR** (same window), consistent with M8/E9/METHODOLOGY (differences expected, not errors). Underlying solved range ~−3,762 to +35,741 bp. Approved methodology/config/values unchanged.

## Known presentation limitations (accepted)
- **Desktop validation/screenshot finality is manual:** this environment cannot open Power BI Desktop or verify render/interaction; Vicky should confirm refreshed Desktop render matches frozen PBIP (incl. Page 4 bars/table/KPIs, zero line visibility, no clipping/broken fields) and that saved screenshots reflect the frozen state.
- PBIP uses `localhost:5434` PostgreSQL datasource; consumers must refresh against an equivalent populated DB.
- Live Power BI execution/interaction evidence and per-visual DAX↔Desktop sign-off remain manual (not claimed here). CI remote execution not performed.
- No historical-snapshot summation; E9 excludes 386 no-root observations by design (documented).

## Non-GUI validations performed
- 42 PBIP `visual.json` parse OK; no BOMs.
- SQL: quintiles sum 654, 654 distinct/once, per-band recompute matches; P1 latest diff 0.00; P3 restatement deltas match (see `docs/DASHBOARD_VALIDATION_SQL.md`, `docs/DASHBOARD_AUDIT.md`).

**Dashboard/Page 4 frozen.** See `docs/DASHBOARD_AUDIT.md`, `docs/DASHBOARD_VALIDATION_SQL.md`, `docs/M9_ACCEPTANCE_REPORT.md`.
