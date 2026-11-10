# Results

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Date | 2026-11-09 (baseline generation) / 2026-11-10 (M10 verification notes) |
| Data | Synthetic accounts/transactions/corrections; real AMFI NAV inputs. Educational prototype; not investment advice. |
| NAV snapshot | **Canonical** `amfi_nav_m1` (core.nav_snapshot id 3): **1,811,703** observations (2006-04-02–2026-11-06, approved 85 ranges), 0 duplicate `(snapshot, scheme, date)` keys. 6 seed/test fixture rows isolated in `core.nav_snapshot` id 4 `test_fixture_nav_seeds` (DB total 1,811,709) — **verified/reconciled 2026-11-10** (`docs/NAV_RECONCILIATION_6_EXTRA.md`) |
| Generator | `generator-1.0.0`; seed 20261109; config hash `c0e8e515677698c4e9dbc2720089ad7ce39091447f482bce9f97d195b32ae81a` |
| Dataset hash | `94839c5cb0119c6501f592da2f7fef56ca3f6cbb04e5e49ba4adfaf3308b6cda` (baseline) |

## E1 — Calculation correctness

- Cases: 17 hand-computed fixtures from `docs/METHODOLOGY.md` (§5–8), all passing (recorded).
- Independent reference: separately written bisection XIRR solver (`performance/reference.py`) agrees within 1 bp on eligible fixtures (recorded).
- **M10 2026-11-10:** not re-executed in this environment (pytest/deps unavailable).

## E2 — Archived report replay

- Snapshots replayed exactly in M6 integration evidence (canonical hash equality), count-based (not %). Deterministic demo replay `REPLAY_EXACT` materialized in pipeline design.
- **M10 2026-11-10:** not re-executed as a fresh clean-run evidence set.

## E3 — Overwrite comparator

- Comparator retains only current rows; corrected account pre-correction numbers unreproducible (fixture evidence, e.g. 1 of 2 reproducible). Count-based.
- **M10 2026-11-10:** not re-executed.

## E4 — Restatement register

- M2 intent sample: 18 applied / 2 rejected with explicit reason codes (baseline). Demo restatement (deterministic, K1→K2) materialized (Δ portfolio/cash/TWR/XIRR as documented in marts/docs).
- **M10 2026-11-10:** not re-executed end-to-end.

## E5 — Invariants

- Accounts checked: 12; passed: 12; failed: 0 (baseline recorded). Violations: [].
- **M10 2026-11-10:** not re-executed.

## E6 — As-of query performance

- Deterministic repeated queries asserted in M4 (recorded); p50/p95 benchmarking **not claimed**.

## E7 — Reproducibility

- Dataset hash (baseline): `94839c5cb0119c6501f592da2f7fef56ca3f6cbb04e5e49ba4adfaf3308b6cda`.
- Prior documented: two clean `make reproduce` runs from empty DB produced identical logical hashes / `RESULTS.md` hash `ac6257e2…` (baseline). 
- **M10 2026-11-10:** **two clean `make reproduce` runs with matching logical hashes NOT executed** in this environment (deps/clean-DB run not performed). Fresh RC determinism must be re-established in a prepared validation environment.

## E8/E9 — Sensitivity (M8 frozen, preserved)

- Frozen config: `config/sensitivity.yaml` SHA-256 `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01` (unchanged). `results/sensitivity_detail.csv` (11,436 rows), `results/sensitivity_summary.json`, `results/E9_COVERAGE.md` preserved.
- **E8:** complete (recorded). **E9:** 1,040 eligible windows, **654 solved** (n=654), 386 excluded (no-root/unsolved, documented).
- **Dashboard E9 (presentation, validated 2026-11-10):** drawdown-quintile bar chart (final), 5 bands Q1–Q5 (131/131/131/131/130), deterministic tie-handling, per-band stats independently recomputed from observations and matching (`marts.sensitivity_e9_quintiles/detail`). Gap reported as **annualised XIRR minus period TWR** over the same 12-mo SIP window (by definition; not an error). No M8/config/methodology changes.

## M10 verification notes (2026-11-10)

- **Verified (DB/files):** canonical NAV snapshot 3 / 1,811,703 obs (approved 85 ranges, 6 fixture rows isolated in snapshot 4), 0 duplicates; 7 migrations applied with checksums matching `sql/migrations/*.sql`; migration runner fails on checksum mismatch (code-level). E9 marts 654 distinct/once, per-band validation OK. M8 config hash preserved. Git/secret scan and audits completed (local dev DB config hardened to 127.0.0.1 + `.env` password; `.env` not committed). Dashboard frozen; screenshots present (Desktop finality manual).
- **Not executed:** full pytest suite, Ruff, checksum-tamper regression test rerun, NAV idempotency rerun from source, two clean `make reproduce` runs with matching logical hashes, Power BI Desktop validation, remote CI. Prior local claims (75 tests, Ruff clean, double reproduce `ac6257e2…`, tamper exercised) are **recorded but not re-run** this session.
- See `docs/V1_0_0_RC_FINAL_REPORT.md`.

## Limitations

- Correction magnitudes are controlled parameters, not observed error rates. The study measures sensitivity, not user benefit.
- XIRR grid scan can miss even-multiplicity tangential roots (METHODOLOGY §7.7). E9 partial by solver domain (654/1,040).
- TWR/XIRR differences are expected (different metrics/conventions: period TWR vs annualised XIRR). E6 p50/p95 not claimed.
- Live Power BI execution/interaction and screenshot finality manual; CI remote execution not performed. No push/publish/tag/release without Vicky’s explicit approval. No further feature development.
