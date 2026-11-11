# Results

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Date | 2026-11-11 (v1.0.0 verification baseline) |
| Data | Synthetic accounts/transactions; real AMFI NAV inputs. Educational prototype; not investment advice. |
| NAV snapshot | `amfi_nav_m1` (id 1); 1811703 observations |
| Generator | `generator-1.0.0`; seed 20261109; config hash `ed9891222f7817344b596408ffa1947da0724140067592c89ca7d5d94fa6afbb` |
| Dataset hash | `833f7f5703c1bbbd8142f0db5c11945b97bf2f844307c9a59887b886b62a2f8a` |

## E1 — Calculation correctness

- Cases: 17 hand-computed fixtures from `docs/METHODOLOGY.md` (§§5–8), all passing.
- Independent reference: separately written bisection XIRR solver (`performance/reference.py`) agrees within 1 bp on eligible fixtures; maximum absolute differences are below the assertion tolerance.
- Max absolute error: within the test tolerances (no production function is called from the reference).

## E2 — Archived report replay

- Original snapshot (demo, account 1, 2024-01-01–2024-06-30, K1=2024-07-15T12:00:00+00:00): id 1, replay `REPLAY_EXACT`.
- Original snapshot replayed again after later correction (K1 unchanged): `REPLAY_EXACT`.
- Archived report snapshots in DB: 1. Replay is reported as exact canonical-hash equality (count), not a percentage.

## E3 — Overwrite comparator

- The comparator retains only current rows; after applying the correction workload the corrected account's pre-correction numbers are unreproducible. Counts are reported by the integration test (1 of 2 reproducible in the fixture).

## E4 — Restatement register

- Correction intents generated (M2): 14926.
- Demo applied correction operations (accepted revisions, revision_no>1): 1 (applied=1).
- Demo rejected correction attempts: 1 (rejected=1, reason `MISSING_NAV_ALLOTMENT`).
- Restatement at K2=2024-08-01T12:00:00+00:00: status `RESTATEMENT_GENERATED` (source snapshot 1).
- Counts and shares are generator-driven / deterministic demo-driven.

## E5 — Invariants

- Accounts checked: 1000; passed: 1000; failed: 0.
- Violations: []

## E6 — As-of query performance

- Environment: Windows-11-10.0.26300-SP0; Intel64 Family 6 Model 183 Stepping 1, GenuineIntel; 16 logical cores; 15.7 GB RAM; PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu in Docker (`postgres:16`).
- Rows: accounts 1,000; business transactions 209,937; immutable revisions 209,938; NAV observations 1,811,703.
- Runs: 30 measured + 3 warm-up per knowledge point; measured statement is the exact as-of SQL used by `LedgerService.get_as_of`.

| Knowledge point | Visible revisions | Without index p50 (ms) | Without index p95 (ms) | With index p50 (ms) | With index p95 (ms) |
|---|---:|---:|---:|---:|---:|
| p25 (2019-07-29) | 52,486 | 268.48 | 281.83 | 262.31 | 278.55 |
| p50 (2022-05-05) | 104,970 | 539.27 | 561.32 | 527.07 | 547.99 |
| p75 (2024-06-24) | 157,453 | 795.20 | 822.14 | 792.76 | 873.00 |
| max (2026-10-31) | 209,938 | 1315.60 | 1368.38 | 1299.42 | 1372.61 |

- As-of result digests identical with and without the index: **True**.
- Full query plans (indexes used, execution time, buffer counts) and raw samples are in `results/E6_BENCHMARK.json`; summary in `results/E6_BENCHMARK.md`.
- Latency is specific to the stated environment and is not a portable performance guarantee.

## E7 — Reproducibility

- Dataset hash (this run): `833f7f5703c1bbbd8142f0db5c11945b97bf2f844307c9a59887b886b62a2f8a`
- Two clean `make reproduce` runs from an empty database must produce byte-identical `RESULTS.md` and identical logical hashes (see the pipeline gate).

## E8/E9 — Sensitivity

- Run from the frozen pre-registration in `config/sensitivity.yaml` (M8). See `results/sensitivity_summary.json`, `results/sensitivity_detail.csv`, `results/E9_COVERAGE.md`.
- Coverage: 344 eligible schemes, 30 selected paths, 40 quarterly windows (1,200 path-window universe); 1,040 windows have a complete monthly SIP history. **E9 solved 1,040/1,040, excluded 0** under the documented solver domain.
- The original 2026-11-09 run excluded 386 windows because of a terminal-valuation/backdating implementation defect. The frozen config was not changed; the defect, correction and preserved original evidence are documented in `results/E9_EXCLUSION_ANALYSIS.md` and `docs/E9_EXCLUSION_INVESTIGATION.md`.
- Metric: **annualised XIRR minus period TWR over the same 12-month SIP window** (two different measures, not an error metric).

## Limitations

- Correction magnitudes are controlled parameters, not observed error rates.
- The study measures sensitivity, not user benefit.
- The grid scan can miss even-multiplicity tangential roots (METHODOLOGY §7.7).
