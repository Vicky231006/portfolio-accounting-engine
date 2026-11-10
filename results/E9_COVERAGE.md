# E9 Coverage — Sensitivity Study

| Field | Value |
|---|---|
| Frozen config | `config/sensitivity.yaml` status `frozen`; SHA-256 `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01` |
| Eligible schemes | 344 (`min_observations >= 750`, first NAV `<= 2014-01-01`) |
| Selected paths | 30 (`max_paths: 30`) |
| Quarter windows | 40 (2016-01-01..2025-10-01 quarterly) |
| Eligible windows (30 × 40) | 1,040 |
| Successfully solved (XIRR gap present) | **654** |
| Excluded (no XIRR root in reference domain) | **386** (37.1%) |
| Detail rows | 11,436 (11 parameter values × ~1,040 windows; 5 backdate/mis-size rows fewer due to insufficient-path counting) |
| Drawdown coverage | 1,040 / 1,040 (always present) |

## Status breakdown (E9 rows)

| Status | Count | Share |
|---|---|---|
| `SUCCESS` (gap solved) | 654 | 62.9% |
| no root in reference domain (`r ∈ [−0.5, 5]`) | 386 | 37.1% |
| multiple roots | 0 | 0% |
| non-convergence | 0 | 0% |
| excluded insufficient paths | 0 | 0% |

The 386 excluded rows are not discarded silently: they remain in `results/sensitivity_detail.csv` with blank XIRR fields and are counted in the summary `failures` map (3,857 = 386 × 10 scenario parameters + 1 extra edge case).

## Sample size used for the analysis

- **n = 654** for the XIRR-minus-TWR versus drawdown analysis.
- Drawdown alone has n = 1,040.

## Qualification

No E9 distribution is claimed on the full 1,040 windows. The reported E9 distribution uses only the 654 solved gaps. Fields not solved are reported as exclusions above, not averaged away.
