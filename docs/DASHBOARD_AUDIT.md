# M9 Dashboard Audit (final refinement pass)

**Date:** 2026-11-10  
**Scope:** PBIP semantic model + report visuals/marts for Pages 1–4 (PostgreSQL-only, `localhost:5434/bitemporal_ledger`). **No financial methodology or frozen M8 configuration changed.**

## Data sources / grain (verified)

| Area | Source | Grain / truth |
|---|---|---|
| Portfolio valuation KPIs & history | `marts.portfolio_history_total` (M4 `ValuationService`, quarterly, OK rows) | **Latest common eligible date 2026-09-30**: total 124,325,759.90, holdings 110,372,447.52, cash 13,953,312.38 INR; **reconcile diff 0.00** (unrounded). Historical sum across all dates must not be used for point-in-time KPIs. |
| Account valuation history | `marts.portfolio_history` | Per `account_id, valuation_date` (612 rows, 593 OK). |
| Holdings | `marts.holdings_latest` | **One row per account×scheme at that account’s latest valuation snapshot** (180 rows). Includes `scheme_display`, `valuation_date`, `nav_date`; snapshot dates may differ across accounts (labeled). |
| Asset allocation | `marts.asset_allocation` | Latest holdings aggregated by scheme, **Top 10 + “Other schemes”** (11 rows), `scheme_display`, `sort_order`; values preserved. |
| Flows | `marts.monthly_flows` | Per month (164): contributions and withdrawals as separate signed series. |
| Ledger / drilldown | `marts.account_drilldown` (2,287 rows) | Per transaction revision view; account counts e.g. acct 1 = 187, total 2,287. |
| Restatements / audit | `marts.report_snapshots`, `marts.restatement_comparison`, `marts.demo_correction_detail`, `core`/`marts.correction_audit`, `marts.rejected_corrections` | 2 snapshots, same acct 1 & period 2024-01-01–2024-06-30: K1 original (2024-07-15T12:00:00Z) vs K2 restated (2024-08-01T12:00:00Z). Δ +14,041.39 INR, Δ cash +0.02 INR, Δ TWR +0.428972888… bp (+0.0042897288… pp). 1 applied REPLACE (`SYN_TXN-000014`, rev 1→2), 1 rejected `MISSING_NAV_ALLOTMENT`, replay `REPLAY_EXACT` before/after. 2,287 original revisions. Concepts kept distinct (revisions vs correction ops vs rejections vs snapshots/replay/restatement). |
| Sensitivity (M8, frozen) | `marts.sensitivity_e9`, `marts.sensitivity_detail_agg`, `marts.sensitivity_meta` | 344 eligible / 30 selected, 1,040 windows, 11,436 detail rows, 654 solved, 386 excluded no-root, 0 multiple-root, 0 non-convergence. Detail agg: 11 precomputed per-parameter rows (median/P95 |ΔXIRR|, median |ΔTWR|) — **not summed/averaged across groups**. Mis-sizing & missed-correction zeros verified genuine in `results/sensitivity_detail.csv`. E9 scatter: 654 solved observations (drawdown_bp vs xirr_minus_twr_bp). |

## PBIP visual map (refinement)

### Page 1 — Portfolio Overview
- **Cards (INR, latest date):** synthetic accounts, total transactions, portfolio total value, holdings value, cash (`PortfolioHistoryTotal` latest-date measures). Snapshot count.
- **Portfolio Value Over Time:** `PortfolioHistoryTotal` by `valuation_date` (time series, not summed for KPI).
- **Monthly Contributions and Withdrawals:** separate series (`MonthlyFlows` measures).
- **Portfolio Allocation by Scheme (Top 10 + Other):** `AssetAllocation.scheme_display` / market value (sorted), “Other schemes” aggregates remainder.
- **Archived Report Snapshots:** `ReportSnapshots` (numeric TWR/XIRR formatted %, INR values), table totals disabled (best-effort). No account-return averaging.
- **Disclosure:** synthetic-data footer textbox on page.

### Page 2 — Account Drilldown
- **Selectors:** account slicer (`PortfolioOverview.account_id`, single-select configured best-effort) + valuation date/period slicer.
- **KPIs:** Transaction Count (`AccountDrilldown`, should filter by selected account via relationship) and **Selected Account Cash Balance** (explicit measure: cash at latest `valuation_date` in filter context).
- **Holdings (Latest Snapshot per Account):** account_id, valuation_date, scheme_display, units, NAV, market value, stale NAV, NAV date; labeled for differing snapshot dates across accounts; totals disabled.
- **Account Portfolio Value Over Time:** `PortfolioHistory` by account/date.
- **Transaction Ledger:** includes txn/type/effective/recorded/scheme/amount/units/voided; amount/units shown without meaningless grand totals (best-effort).
- **Disclosure:** synthetic-data footer textbox.

### Page 3 — Restatements & Audit
- **KPIs:** 2,287 original revisions, 1 applied correction, 1 rejected correction, 2 snapshots, plus explicit delta cards (Δ portfolio value INR, Δ cash INR, Δ TWR bp).
- **Applied Correction & Replay Status:** `DemoCorrectionDetail` (affected txn, type, reason, replay status, new revision). **Rejected Correction Attempts:** detail table.
- **K1/K2 Original vs Restated Comparison:** dedicated table (account/period/K1/K2, original/restated total & cash INR, Δ total/cash, original/restated TWR %, Δ TWR bp & pp). Totals disabled.
- **Revision Count by Kind:** actual revision records chart; **Transaction Revisions / Correction Audit Detail** table.
- **Layout:** de-cramped (non-overlapping regions) with disclosure footer.

### Page 4 — Sensitivity (real NAV paths, frozen M8)
- **KPIs (explicit measures):** Selected Paths (30), E9 Eligible Windows (1,040), Solved Gaps (654), Excluded No-Root (386), Detail Rows (11,436).
- **Scenario-Level Median |ΔXIRR| by Parameter:** precomputed per-parameter measure (not summed).
- **Scenario-Level Median/P95 table:** scenario, parameter, n, median |ΔXIRR|, P95 |ΔXIRR|, median |ΔTWR| (all precomputed per parameter); grand total disabled.
- **E9 Scatter:** 654 solved observations, X = drawdown (bp), Y = XIRR − TWR (bp), filter `solved=true` (best-effort), labeled to frozen config.
- **Disclosure:** synthetic-data footer textbox.

## Validations performed in this environment

- **PBIP integrity:** 41 `visual.json` files parse; no UTF-8 BOMs in PBIP artifacts.
- **SQL reconciliation:** latest-date P1 totals and 0.00 diff; restatement deltas (+14,041.39 / +0.02 / +0.42897 bp / +0.0042897 pp); sensitivity counts (654/1040, meta 30/1040/654/386/11436, 11 allocation rows top10+Other). See `docs/DASHBOARD_VALIDATION_SQL.md`.
- **Marts compatibility:** `scripts/build_portfolio_history.py` updated to emit `scheme_display` and top10+Other `asset_allocation` (presentation only; valuation methodology unchanged).

## Not completed / manual (M9 remains open)

- **Power BI Desktop GUI validation:** refresh, rendering, measure evaluation in Desktop, slicer/filter interactions (incl. single-select behavior, acct 1→187 txns), cross-filtering, tooltip/format rendering, and correction of any Desktop-only issues.
- **Screenshots:** 4 final PNGs (`docs/screenshots/page1_overview.png`–`page4_sensitivity.png`) not captured (no Desktop). Existing HTML previews are not Desktop screenshots.
- **Per-visual DAX↔Desktop sign-off:** full in-report DAX expressions/interaction proof beyond SQL/model definitions.
- **Full `make reproduce` twice with identical hashes:** not executed in this session (see acceptance report). Marts added/modified may require rebuild steps post-reproduce.
- **Remote CI:** not executed.

No FundLens changes. No push/publish/tag/release.
