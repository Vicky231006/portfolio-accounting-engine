# E9 Coverage — Sensitivity Study

| Field | Value |
|---|---|
| Frozen config | `config/sensitivity.yaml` status `frozen`; SHA-256 `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01` |
| Eligible schemes | 344 (`min_observations >= 750`, first NAV `<= 2014-01-01`) |
| Selected paths | 30 (`max_paths: 30`) |
| Quarter windows | 40 |
| Path-window universe | 1200 (selected paths × quarter windows) |
| Windows with SIP instalments | **1040** |
| Solved (XIRR gap present) | **1040** |
| Excluded (no XIRR root in documented domain) | **0** |
| Solved rate | 100.0% |
| Solver domain | `r ∈ (-0.999999, 1000)` |
| Detail rows | 11440 |

## Status breakdown (E9 rows)

| Status | Count | Share |
|---|---|---|
| `SUCCESS` | 1040 | 100.0% |

## Solved / excluded by window year

| Window year | Windows | Solved | Excluded |
|---|---:|---:|---:|
| 2016 | 112 | 112 | 0 |
| 2017 | 112 | 112 | 0 |
| 2018 | 112 | 112 | 0 |
| 2019 | 112 | 112 | 0 |
| 2020 | 110 | 110 | 0 |
| 2021 | 108 | 108 | 0 |
| 2022 | 98 | 98 | 0 |
| 2023 | 92 | 92 | 0 |
| 2024 | 92 | 92 | 0 |
| 2025 | 92 | 92 | 0 |

## Sample size used for the analysis

- **n = 1040** for the XIRR-minus-TWR versus drawdown analysis.
- Drawdown alone has n = 1040.

## Qualification

No E9 distribution is claimed on the full path-window universe unless every eligible window has a valid root. Excluded rows remain in `results/sensitivity_detail.csv` with blank XIRR fields and are counted in the summary `failures` map; they are never averaged away.

The metric is **annualised XIRR minus period TWR over the same 12-month SIP window**. It compares two different return measures and is not an error metric.
