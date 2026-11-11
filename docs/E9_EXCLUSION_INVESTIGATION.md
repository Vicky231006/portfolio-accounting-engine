# E9 Exclusion Investigation

**Status:** closed 2026-11-11. Frozen study configuration unchanged.
**Machine-readable evidence:** `results/E9_EXCLUSION_ANALYSIS.json`
**Human-readable evidence:** `results/E9_EXCLUSION_ANALYSIS.md`

## Question

The original frozen M8 run (2026-11-09) solved E9 for **654 of 1,040** eligible
SIP windows and excluded **386**. The exclusions were concentrated in older
windows. Were they genuine mathematical no-root cases, or an implementation
defect?

## Method

1. Preserved the original outputs byte-for-byte under
   `results/archive/e9_v1_frozen/`. They were not overwritten.
2. Reproduced the original exclusion pattern and tabulated it by window year
   and by drawdown quintile.
3. Inspected the sensitivity helper (`evaluation/sensitivity.py`) against the
   frozen study rules and the production performance methodology.
4. Corrected only the implementation defects found, keeping the frozen
   `config/sensitivity.yaml` (SHA-256
   `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`),
   the eligible-scheme selection, the 40-quarter window grid and the metric
   definition unchanged.
5. Re-ran the study and compared coverage, status counts and result digests.

## Findings

Four implementation defects were confirmed:

| # | Defect | Effect |
|---|---|---|
| 1 | Terminal valuation used the dataset-wide maximum NAV date (2026) instead of the last NAV on or before the 12-month window end | Older windows were valued at a 2026 NAV while the terminal cash flow was discounted to the next day, producing annualised returns far outside any sensible domain |
| 2 | Backdated instalments were shifted by **calendar** days and silently dropped when the shifted date had no NAV | Scenario histories lost an instalment instead of rolling to the next available NAV |
| 3 | The sensitivity-only XIRR solver used a narrower domain (`r ∈ [-0.5, 5]`) than the documented production domain `r ∈ (-0.999999, 1000)` | Genuine roots beyond `-50%` p.a. were reported as no-root |
| 4 | The SIP TWR helper did not chain-link NAV subperiod returns correctly | TWR could be mis-stated independently of the XIRR coverage issue |

The year pattern is direct evidence for defect 1: exclusion rates fall
monotonically as the window moves closer to the terminal date (2016: 91/112;
2017: 85/112; 2018: 78/112; 2019: 77/112; 2020: 54/110; 2022: 1/98; 2023–2025:
0). Exclusion rates across drawdown quintiles are **not** monotonic, so the
original data did not support a drawdown-clustering explanation.

## Result

The final corrected run solves **all 1,040** eligible windows with **0 exclusions** (solved rate **100.0%**).

| Run | Windows with SIP instalments | Solved | Excluded | Solved rate |
|---|---:|---:|---:|---:|
| Original frozen (2026-11-09) | 1,040 | 654 | 386 | 62.9% |
| Corrected final (2026-11-11) | 1,040 | **1,040** | **0** | **100.0%** |

## Interpretation rules retained

- The **1,200** path-window universe (30 selected paths × 40 quarters) is not
  the E9 sample. Only the **1,040** windows with a complete monthly SIP
  instalment history enter E9.
- The metric is **annualised XIRR minus period TWR over the same 12-month SIP
  window**. It compares two different return measures and is **not an error
  metric**.
- Excluded rows, if any occur in future runs, remain in
  `results/sensitivity_detail.csv` with blank XIRR fields and are counted in
  the summary `failures` map; they are never averaged away.

## Reproduction

```powershell
$env:DATABASE_URL = "postgresql://postgres:<pw>@127.0.0.1:5434/bitemporal_ledger"
python scripts/run_sensitivity.py --out-dir results --force
python scripts/analyze_e9_exclusions.py
```

`scripts/run_sensitivity.py` refuses to overwrite existing evidence unless
`--force` is supplied.
