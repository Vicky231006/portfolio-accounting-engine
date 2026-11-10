# Dashboard / PBIP Validation (SQL reconciliation)

Date: 2026-11-10. DB: `bitemporal_ledger` @ `localhost:5434` (synthetic accounts/txns, real AMFI NAV). Power BI Desktop visual rendering/interaction not executable here.

## 1) Portfolio valuation aggregation (Page 1)

**Grain:** `marts.portfolio_history_total` = one row per `valuation_date` (quarterly), aggregated across accounts where `marts.portfolio_history.status='OK'` (M4 `ValuationService`).

| Check | SQL | Result |
|---|---|---|
| Latest common eligible valuation date | `SELECT max(valuation_date) FROM marts.portfolio_history_total;` | `2026-09-30` |
| Totals at latest date | `SELECT total_value,total_holdings_value,total_cash FROM marts.portfolio_history_total WHERE valuation_date=(SELECT max(valuation_date) FROM marts.portfolio_history_total);` | `124325759.90`, `110372447.52`, `13953312.38` |
| Reconciliation (unrounded) | `... SELECT (total_value - total_holdings_value - total_cash) ...` at latest date | `0.00` |
| Historical series grain | `SELECT count(*) FROM marts.portfolio_history_total;` | `51` rows (one per quarter) |
| Prior incorrect grain (if summed across all dates) | `SELECT sum(total_value),sum(total_holdings_value),sum(total_cash) FROM marts.portfolio_history_total;` | `2405060756.59, 2072294101.39, 332766655.20` (must NOT be used for point-in-time KPIs) |

**PBIP fix:** Page 1 KPI measures use latest-date values (`CALCULATE(..., valuation_date = [Latest Valuation Date])`), not sums across all snapshot dates. Chart uses `valuation_date` as category (time series) — correct grain.

## 2) Holdings / drilldown (Page 2)

| Check | SQL | Result |
|---|---|---|
| Holdings grain | `marts.holdings_latest`: per `account_id, scheme_code` at account's latest valuation | 180 rows total; per-account counts e.g. acct 1→18 schemes @ 2026-09-30, acct 5→18 @ 2021-12-31 |
| No cross-date summing per row | one `valuation_date`/NAV context per account snapshot row; table must be read with account filter | e.g. acct 1 = 18 rows, mv sum 15,589,377.05 |
| Transaction counts by account | `SELECT account_id,count(*) FROM marts.account_drilldown GROUP BY 1;` | 1→187 … 10→427 … total 2,287 |
| Filter expectation | `AccountDrilldown` related to `PortfolioOverview` on `account_id`; slicer uses `PortfolioOverview.account_id` | TransactionCount KPI must respond to account selection (verify in Desktop) |

## 3) Restatements (Page 3)

| Check | SQL | Result |
|---|---|---|
| Same account/period, K1 vs K2 | `SELECT * FROM marts.restatement_comparison;` | acct 1, 2024-01-01–2024-06-30, K1 `2024-07-15T12:00:00Z` (original, snap 1), K2 `2024-08-01T12:00:00Z` (restated, snap 2) |
| Values/deltas | same | orig total 18,072,865.14 / restated 18,086,906.53 / Δ +14,041.39 INR; cash 2,620,536.15→2,620,536.17 / Δ +0.02; TWR 0.1584914951→0.1585343924 / Δ +0.0000428973 = **+0.42897 bp** |
| Counts | `core.txn_revision rev>1`, `core.correction_rejection`, `core.report_snapshot` | 1 applied, 1 rejected, 2 snapshots |
| Correction/replay | `demo_report.json` / `marts.demo_correction_detail` | REPLACE `SYN_TXN-000014` (rev 1→2), reason APPLIED, replay `REPLAY_EXACT` before/after; rejection `MISSING_NAV_ALLOTMENT` |

## 4) Sensitivity (Page 4)

| Check | SQL / source | Result |
|---|---|---|
| Meta counts | `SELECT * FROM marts.sensitivity_meta;` | 344 eligible, 30 selected, 1,040 windows, 11,436 detail, 654 solved, 386 no-root, 0 multiple-root, 0 non-convergence |
| E9 windows/solved | `SELECT count(*), count(*) filter (where solved) FROM marts.sensitivity_e9;` | 1,040 / 654 |
| Mis-sizing/missed-correction zeros | `results/sensitivity_detail.csv` scan (xirr_abs_bp) | **Genuine**: mis_size_* and missed_correction = 0 for all 1,040 obs each (max 0E-15); backdating has 652–653 nonzero (max ~3792.68 bp) |
| Per-parameter stats (precomputed, correct grain) | `SELECT * FROM marts.sensitivity_detail_agg;` | 11 rows (1 per scenario/parameter) with median/P95 |ΔXIRR| bp; backdate medians 23.26/36.09/27.06/101.54 bp, others 0 — must not be summed across groups |
| P95/extremes | detail agg | e.g. backdate_5d P95 1184.70 bp; extreme detail obs drive P95 (per frozen study) |

## Limitations of this validation
- No Power BI Desktop rendering/measure-evaluation/interaction testing performed here; screenshots not captured.
- Portfolio-level TWR/XIRR as aggregate series not computed (snapshot performance shown where archived; no account-return averaging).
- Per-visual DAX expressions in Desktop and filter cross-highlighting require manual verification against this SQL.
- Clean `make reproduce` twice with identical hashes not executed in this session. M9 remains open.


## 5) E9 final visual correction — Drawdown Quintile Bar Chart (replaces scatter)

**Source:** `marts.sensitivity_e9` (654 solved observations; 386 no-root/unsolved excluded). Fields: `observation_key`, `drawdown_bp`, `xirr_minus_twr_bp` (all non-null for solved). Sign convention preserved as stored (no transformation). No fabricated/imputed values.

**Quintile construction (deterministic, reporting-only; M8 config unchanged):**
- Sorted by `drawdown_bp ASC, observation_key ASC` (654 rows).
- Initial split points at row indices `ceil(n*i/5)-1` for i=1..4 (n=654 → 130, 261, 392, 523).
- **Tie-handling:** identical `drawdown_bp` values kept in the same band by assigning each drawdown value the earliest (minimum) initial band among its occurrences; no drawdown value split across bands. Band sizes may differ slightly from equal fifths due to ties (actual: 131, 131, 131, 131, 130).

**Bands (from `marts.sensitivity_e9_quintiles`, per-band statistics computed independently from `marts.sensitivity_e9_quintile_detail`):**
| Band | n | Min DD (bp) | Max DD (bp) | Median DD (bp) | Median XIRR−TWR (bp) | Median |XIRR−TWR| (bp) | P95 |XIRR−TWR| (bp) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1 Lowest | 131 | 229.1126062432990972233012725888404 | 772.1127219416843134060921974262909 | 652.0150882553003 | 6155.557566264992 | 6155.557566264992 | 21085.53627673645 |
| Q2 Lower-middle | 131 | 776.6470273165506159614354579539368 | 1110.116799349177755825440176651752 | 937.537789526925 | 9478.670293509938 | 9478.670293509938 | 25859.469202442 |
| Q3 Middle | 131 | 1110.154905335628227194492254733219 | 1461.808062263064944369751386797059 | 1299.424472244162 | 7125.300357991289 | 7125.300357991289 | 30363.249337302885 |
| Q4 Upper-middle | 131 | 1463.907325720410603124871171208311 | 1804.362943702001572231964685251255 | 1649.7181094894356 | 7118.453519803219 | 7118.453519803219 | 20946.25933025619 |
| Q5 Highest | 130 | 1809.948347838392414915446119012241 | 4002.161383285302593659942363112392 | 2093.9248619268337 | 9473.553306314423 | 9473.553306314423 | 33545.50310623995 |

**SQL validation (independent, reproducible):**
- `SELECT sum(observations) FROM marts.sensitivity_e9_quintiles;` → **654**. `SELECT count(*) bands FROM marts.sensitivity_e9_quintiles;` → **5**.
- `SELECT count(*), count(distinct observation_key) FROM marts.sensitivity_e9_quintile_detail;` → **654, 654**. `SELECT observation_key,count(*) c FROM ... GROUP BY 1 HAVING count(*)>1;` → **0 rows** (each obs exactly once).
- Source coverage: `SELECT count(*) FROM marts.sensitivity_e9 WHERE solved=true AND observation_key IS NOT NULL AND drawdown_bp IS NOT NULL AND xirr_minus_twr_bp IS NOT NULL;` → **654**. No-root/unsolved excluded.
- **Per-band independent recompute** from `marts.sensitivity_e9_quintile_detail` (`count`, `min/max/percentile_cont(0.5)` drawdown, `percentile_cont(0.5)` signed diff, `percentile_cont(0.5)` abs, `percentile_cont(0.95)` abs) matches `marts.sensitivity_e9_quintiles` exactly for all 5 bands.

**Investigation: ~6,000–9,000 bp median XIRR−TWR differences (validated, no methodology change):**
- `xirr_minus_twr_bp = (xirr_rate - twr) * 10000` per solved 12-month window (M8 E9, `src/bitemporal_ledger/evaluation/sensitivity.py`: `_bp(correct_returns["twr"], correct_returns["xirr_rate"])`).
- **Same window/inputs:** each observation is computed on the same deterministic SIP schedule, same NAV path/window (12 months, `config/sensitivity.yaml`), and same terminal valuation for that window (correct baseline). Period coverage is comparable.
- **Convention:** `twr` is the chained **period** time-weighted return over the window (`performance/twr.py`); `xirr_rate` is the solved **annualised** money-weighted rate (`performance/xirr.py`, actual/365, `solve` over window cash flows + terminal). Therefore the reported gap is **(annualised XIRR − period TWR)** in bp for the same 12-month SIP window — different metrics by definition (MWRR vs TWR), as studied by E9/M8 and consistent with METHODOLOGY (TWR/XIRR differences are expected and must not be presented as error).
- **Underlying observations:** solved values range approximately −3,762.08 to +35,741.32 bp (median ~7,942.12 bp overall); band medians 6,156–9,479 bp reflect the actual distribution of solved observations (not fabricated/imputed). Approved methodology/config unchanged.

**PBIP:** bar chart `a4s1` “XIRR–TWR Difference by Drawdown Band” (category Q1–Q5 by `band_order`, value = signed **Median XIRR−TWR Difference (bp)** via measure, zero reference line best-effort, tooltips n/range/median abs/P95 abs, subtitle notes “annualised XIRR minus period TWR, same 12-mo SIP window”) + supporting table `a4t1` with all required columns (Band, Observations, Min/Max/Median drawdown bp, Median signed XIRR−TWR bp, Median absolute, P95 absolute; no grand total). Page 4 KPI labels shortened for readability without layout changes. Scatter plot not used. **Desktop render/screenshot validation pending.**
