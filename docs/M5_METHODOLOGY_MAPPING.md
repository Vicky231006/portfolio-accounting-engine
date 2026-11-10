# M5 Methodology — Formula-to-Test Mapping

| Field | Value |
|---|---|
| Milestone | M5 — Performance Engine |
| Date | 2026-11-09 |
| Source | `docs/METHODOLOGY.md` §5–§8 (approved by Vicky 2026-11-09) |

## Conventions (inclusive full-calendar-day, D-028)

- `S = start_date 00:00`, `E = (end_date + 1 day) 00:00`, `T = (E − S).days`, `t_i = (d_i − S).days`.
- External flows at start of day; `V_S` precedes flows on `S`; `V_E` includes flows through `end_date`.
- Signs from the portfolio perspective: contribution `+`, withdrawal `−`. Internal purchases/redemptions/switches are never flows. SIP contribution counted once; purchase internal.
- TWR and Modified Dietz are period returns; XIRR is annualised (actual/365). All arithmetic is `Decimal`.

## Fixture → production → test mapping

| Methodology fixture | Expected value | Production function | Test |
|---|---|---|---|
| §5.3 Zero-flow TWR | 5.0000% | `twr.start_to_end` | `test_twr_zero_flow` |
| §5.4 Contribution (TWR) | 1.6667% | `twr.with_flows` (single flow) | `test_twr_contribution` |
| §5.5 Withdrawal (TWR) | 2.5000% | `twr.with_flows` | `test_twr_withdrawal` |
| §5.6 Same-day flow | 0.9091% | `twr.with_flows` | `test_twr_same_day` |
| §5.7 Mid-period flow | 3.3421% | `twr.compounded` (3 subperiods) | `test_twr_mid_period` |
| §6.2 Modified Dietz mid-period | 3.7895% | `dietz.modified_dietz` | `test_dietz_mid_period` |
| §6.3 Zero-flow / same-day | 5.0000% / 0.9091% | `dietz.modified_dietz` | `test_dietz_zero_and_same_day` |
| §7.2 Simple XIRR | 10.0000% | `xirr.solve` | `test_xirr_simple` |
| §7.3 TWR vs XIRR | TWR 15.2381%, XIRR 6.5248% | `twr` + `xirr` | `test_twr_vs_xirr_gap` |
| §7.4 Multiple roots | `MULTIPLE_ROOTS` [10%, 20%] | `xirr.solve` | `test_xirr_multiple_roots` |
| §7.5.1 Proven no root | `NO_ROOT_PROVEN` | `xirr.solve` | `test_xirr_no_root_proven` |
| §7.5.2 Out-of-domain root | `NO_ROOT_IN_DOMAIN` (nearest 1,001) | `xirr.solve` | `test_xirr_no_root_in_domain` |
| §7.6 Invalid flows | `INVALID_CASH_FLOWS` | `xirr.solve` | `test_xirr_invalid_flows` |
| §8.1 SIP TWR/Dietz | TWR 2.6667%, Dietz 2.7865% | `twr.compounded` + `dietz` | `test_sip_returns` |
| §9 K1/K2 | K1 TWR 0.4000% / XIRR 4.8125%; K2 0.4800% / 5.8001% | account series via `ValuationService` + `twr`/`dietz`/`xirr` | `test_k1_k2_performance_replay` |
| Property: scale invariance | returns unchanged under uniform scaling | `twr`/`dietz` | `test_returns_scale_invariant` |
| Property: no-flow XIRR = period return | XIRR == `V_E/V_S − 1` | `xirr` vs `twr` | `test_no_flow_xirr_equals_period_return` |

## Independent reference

`src/bitemporal_ledger/performance/reference.py` contains a separately written bisection solver that does **not** call the production XIRR code. Tests compare production vs reference rates (tolerance `1e-8`) and report the maximum absolute error (E1-style) without calling the production function from the reference.

## Boundary notes

- TWR subperiods: flow-day subperiods use `(V_t − V_(t−1) − CF) / (V_(t−1) + CF)`; gap subperiods use `V_end/V_start − 1` (PRODUCTION `compute_twr` drives this from `ValuationService` end-of-day values: `V_(d−1)` is the value at the day before each flow date).
- Modified Dietz denominator `<= 0` → `INVALID_DENOMINATOR`; same for any TWR subperiod denominator.
- XIRR domain/grid/tolerances per METHODOLOGY §7.7 exactly (2,001-point `ln(1+r)` scan, bisection refine, Newton-from-midpoint with bisection fallback, `1e-8 × max(1, Σ|CF|)` NPV tolerance, `1e-12` rate tolerance, 200 iterations).
