# E9 Exclusion Investigation

Metric: **annualised XIRR minus period TWR over the same 12-month SIP window (not an error metric)**. Frozen config SHA-256: `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`.

## Conclusion

The 386 exclusions in the original frozen run were caused by an **implementation defect**, not by genuine mathematical no-root cases. The terminal valuation used the last NAV in the entire dataset (2026) instead of the last NAV on or before the 12-month window end. For older windows this valued a 2016-2019 SIP at a 2026 NAV while discounting the terminal cash flow to the next day, producing annualised returns far outside the solver domain.

The defect was corrected without changing the frozen study configuration, scheme selection, quarterly window grid or metric definition. The original outputs are preserved unchanged in `results/archive/e9_v1_frozen/`.

## Coverage

| Run | Windows with instalments | Solved | Excluded | Solved rate |
|---|---:|---:|---:|---:|
| Original frozen (2026-11-09) | 1040 | 654 | 386 | 62.9% |
| Corrected (2026-11-11) | 1040 | 1040 | 0 | 100.0% |

The path-window universe is **1,200** (30 selected paths × 40 quarterly windows). **1,040** of those windows have a complete monthly SIP instalment history within the scheme's available NAV coverage. The remaining 160 are outside the eligible window universe and are not counted as solver exclusions.

## Exclusions by window year

| Year | Original windows | Original excluded | Original exclusion rate | Corrected excluded |
|---|---:|---:|---:|---:|
| 2016 | 112 | 91 | 81.2% | 0 |
| 2017 | 112 | 85 | 75.9% | 0 |
| 2018 | 112 | 78 | 69.6% | 0 |
| 2019 | 112 | 77 | 68.8% | 0 |
| 2020 | 110 | 54 | 49.1% | 0 |
| 2021 | 108 | 0 | 0.0% | 0 |
| 2022 | 98 | 1 | 1.0% | 0 |
| 2023 | 92 | 0 | 0.0% | 0 |
| 2024 | 92 | 0 | 0.0% | 0 |
| 2025 | 92 | 0 | 0.0% | 0 |

The monotonic concentration in early windows is the signature of the terminal-date defect. It is not a drawdown effect.

## Drawdown-quintile comparison (original run)

Bands are empirical quintiles of max peak-to-trough drawdown across all 1,040 windows.

| Band | Observations | Excluded | Exclusion rate | Drawdown range (bp) |
|---|---:|---:|---:|---|
| Q1 | 208 | 48 | 23.1% | 87.8 – 835.2 |
| Q2 | 208 | 85 | 40.9% | 835.2 – 1146.2 |
| Q3 | 208 | 96 | 46.2% | 1148.0 – 1466.9 |
| Q4 | 208 | 62 | 29.8% | 1468.2 – 1867.7 |
| Q5 | 208 | 95 | 45.7% | 1867.7 – 4267.0 |

Exclusion rates are not monotonic across drawdown quintiles (the highest band is not the most excluded). The original data therefore did not support a claim that exclusions clustered around deep drawdowns. The year pattern and the code inspection identify the terminal-date defect as the cause.

## Solver-domain limitation

After fixing the terminal valuation and backdating, an intermediate state solved **1,032 of 1,040** windows. The remaining 8 were all the **2019-04-01** window (the COVID-era drawdown), which required annualised returns below the provisional `-50%` solver bound. Extending the sensitivity solver to the documented production domain `r ∈ (-0.999999, 1000)` resolved those 8. This is a solver-domain correction, not a change to the metric or the economics.

The final corrected run therefore solves **all 1,040** eligible windows with **0 exclusions**.

| Run | Windows with instalments | Solved | Excluded | Solved rate |
|---|---:|---:|---:|---:|
| Intermediate after terminal-date + backdating fixes | 1,040 | 1,032 | 8 | 99.2% |
| Final corrected (terminal date + backdating + solver domain + TWR chain) | 1,040 | **1,040** | **0** | **100.0%** |

## Audit trail

- Frozen configuration unchanged: `config/sensitivity.yaml`.
- Original outputs: `results/archive/e9_v1_frozen/`.
- Corrected outputs: `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `results/E9_COVERAGE.md`.
- Machine-readable analysis: `results/E9_EXCLUSION_ANALYSIS.json`.
