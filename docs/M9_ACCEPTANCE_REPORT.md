# M9 Final Acceptance Report (Dashboard / Power BI)

**Date:** 2026-11-10  
**Milestone:** M9 — Dashboard and SQL (PRD §11)  
**Overall status:** **OPEN (not accepted)** — core PBIP/data refinements implemented; **manual Power BI Desktop validation, 4 final screenshots, and clean double-reproduce hash verification not completed in this environment**.

## Scope and constraints respected
- PostgreSQL-only PBIP (`PostgreSQL.Database("localhost:5434","bitemporal_ledger")`), no MySQL/ODBC. No push/publish/tag/release. FundLens untouched.
- **No financial methodology or calculation engine changes.** **M8 sensitivity configuration/parameters frozen and unchanged** (frozen config hash `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`).
- Corrections/snapshots/restatements are deterministic demo evidence from real ledger/reporting services (not fabricated rows). Honest handling of missing/unsolved data (no silent zeroing/coercion; genuine zeros documented).

## What was implemented (this refinement)

### Data / marts (verified against PostgreSQL)
- **Page 1 grain fixed:** portfolio KPIs bound to **latest valuation date (2026-09-30)** measures — total 124,325,759.90, holdings 110,372,447.52, cash 13,953,312.38 INR; `portfolio = holdings + cash` diff **0.00** (unrounded). Historical series remains time-series by date (not summed for KPIs). `docs/DASHBOARD_VALIDATION_SQL.md`.
- **Page 2 holdings grain:** `marts.holdings_latest` = 1 row per account×scheme at account’s latest valuation (180 rows), with `scheme_display` and `valuation_date`; labeled for differing snapshot dates across accounts. Account relationships restored (`relationships.tmdl`) so slicers can filter related tables.
- **Page 3 restatement:** same acct 1 / 2024-01-01–2024-06-30. K1 original (snap 1, 2024-07-15T12:00:00Z, TWR 0.1584914951) vs K2 restated (snap 2, 2024-08-01T12:00:00Z, TWR 0.1585343924). **Δ +14,041.39 INR, Δ cash +0.02 INR, Δ TWR +0.428972888 bp (+0.0042897288 pp)**. 1 applied REPLACE (`SYN_TXN-000014`, rev 1→2), 1 rejected `MISSING_NAV_ALLOTMENT`, replay `REPLAY_EXACT` before/after; 2,287 original revisions; concepts distinct.
- **Page 4 sensitivity:** reconciled to frozen M8 — 344 eligible/30 selected, 1,040 windows, 11,436 detail rows, 654 solved, 386 excluded no-root, 0 multiple-root, 0 non-convergence. Precomputed per-parameter median/P95 (11 rows) — **not summed/averaged**; mis-sizing/missed-correction zeros genuine (`results/sensitivity_detail.csv`). E9 scatter data = 654 solved observations (drawdown bp vs XIRR−TWR bp).
- **Mart/view updates:** `marts.report_snapshots`/`restatement_comparison` expose numeric TWR/XIRR and `delta_twr_pp`; `marts.asset_allocation` = Top 10 + “Other schemes” with `scheme_display`/`sort_order` (11 rows, value preserved); `marts.holdings_latest` includes `scheme_display`. `scripts/build_portfolio_history.py` updated for compatible presentation schema (no valuation change).

### PBIP / visuals (41 visuals parse, no BOM)
- **Page 1:** INR-formatted latest-date KPI cards (value/holdings/cash), titled “Portfolio Value Over Time”, “Monthly Contributions and Withdrawals” (separate series), “Portfolio Allocation by Scheme (Top 10 + Other)” (scheme display names), snapshot table with numeric TWR/XIRR formatted as % and totals disabled (best-effort), synthetic-data disclosure footer.
- **Page 2:** single-select account slicer configured (best-effort), valuation-date slicer, **Selected Account Cash Balance** explicit measure, holdings table with account_id/valuation_date/scheme_display/units/NAV/market value/stale/NAV date and “latest snapshot per account” labeling, value-over-time chart, transaction ledger with amount/units shown without meaningless grand totals (best-effort) and titles; disclosure footer. Relationships present for account filtering (requires Desktop verification).
- **Page 3 (de-cramped layout):** KPI row (2287/1/1/2) + explicit delta cards (value/cash/TWR bp), applied-correction & replay-status detail (affected txn/type/reason/replay/new revision) and rejected-correction table, dedicated **K1/K2 Original vs Restated Comparison** table (K1/K2, values INR, TWR %, Δ value/cash, Δ TWR bp & pp), revision-count-by-kind chart (actual revision records) and revision/correction audit detail; totals disabled where applicable; disclosure footer.
- **Page 4:** taller KPI cards with explicit measures (30/1040/654/386/11436), corrected Δ labels (no garbled characters), scenario-level median |ΔXIRR| chart and median/P95 table using **precomputed per-parameter** measures (no grand total), **E9 scatter** visual `a4s1` (654 solved, X=drawdown bp, Y=XIRR−TWR bp, solved filter best-effort), disclosure footer.
- **Semantic model:** updated `ReportSnapshots` (numeric twr/xirr, formatting), `RestatementComparison` (+delta_twr_pp/measures), `AssetAllocation` (+scheme_display/sort_order), `HoldingsLatest` (+scheme_display), `PortfolioHistory` (+Selected Account Cash Balance), `AccountDrilldown`/`Sensitivity*` measures & formatting, aliases for compatibility.

## Validation performed

| Check | Result |
|---|---|
| PBIP JSON/TMDL integrity | 41 `visual.json` parse OK; no UTF-8 BOMs in `dashboard/PortfolioReport` artifacts. |
| SQL — P1 latest-date KPIs | 124,325,759.90 / 110,372,447.52 / 13,953,312.38; diff 0.00. |
| SQL — P3 deltas | +14,041.39 / +0.02 / +0.428972888 bp / +0.0042897288 pp (acct 1, 2024-01-01–2024-06-30, K1/K2). |
| SQL — P4 counts & grain | 654/1040 solved; meta 30/1040/654/386/11436; detail agg 11 params (precomputed). |
| Allocation | 11 rows (Top 10 + Other schemes), market values preserved. |
| Source vs bindings | Visual queries/measure references aligned to model tables/measures in repo (static check). |

## Not completed / outstanding (blocking acceptance)

1. **Power BI Desktop validation (manual, required):** open/refresh `Workbook.pbip` against `localhost:5434/bitemporal_ledger`, cancel/disable autodetect relationships if needed; confirm rendering, formats, titles, disclosures, totals-off behavior, and **filter interactions** (account single-select; acct 1 = 187 txns; holdings/ledger/cash/history respond correctly; date filters). Fix any Desktop-only issues.
2. **Final screenshots (manual):** capture and commit `docs/screenshots/page1_overview.png`, `page2_drilldown.png`, `page3_restatements.html/png replacement as required`, `page4_sensitivity.png` from Desktop.
3. **Clean `make reproduce` twice with identical hashes:** **not executed** in this session. `reproduce.py` rebuilds pipeline/RESULTS and includes demo; dashboard marts/views modified here (and `build_portfolio_history.py` schema/presentation) must be regenerated/verified post-reproduce for consistency. Double-run hash comparison and byte-identical RESULTS/hashes remain unverified.
4. **Migration checksum-tamper test:** test exists (`tests/integration/test_migration_checksum.py::test_checksum_tamper_fails_loudly_without_touching_db`) and was previously evidenced as completed in project records; **not re-run in this session**. Confirm in target validation environment.
5. **Full DAX↔SQL per-visual sign-off in Desktop:** SQL reconciliations provided (`docs/DASHBOARD_VALIDATION_SQL.md`); Desktop measure evaluation/interaction proof pending.
6. **Portfolio-level TWR/XIRR:** not fabricated/averaged; snapshot performance shown where archived (2 snapshots). Any additional aggregate series requires approved methodology and evidence.

## Release / evidence notes
- `docs/DASHBOARD_AUDIT.md`, `docs/M9_STATUS.md`, `docs/DASHBOARD_VALIDATION_SQL.md` updated for this pass. M10/release evidence must reflect final validated state (screenshots, hashes, audit) before any RC/tag consideration — **not done**. No push/publish/tag/release.

## Acceptance decision
**M9 remains OPEN** until items 1–3 (and Desktop-verified 4–5 as applicable) pass with evidence attached.
