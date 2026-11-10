# Requirements Traceability Matrix

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` â€” Portfolio Accounting & Performance Engine |
| Status | M0 baseline; implementation and evidence columns will be updated at each milestone |
| Date | 2026-11-09 |
| Source requirements | `PRD.md` v2.0, FR-B1 to FR-B14; PRD sections 5â€“17 |
| Evidence rule | A requirement is not complete until its acceptance criterion, automated test and evidence are all present. |

Legend: **M0** = designed and traceable; **M1â€“M10** = implementation milestone; **Evidence** = actual test/report artefact (not a promise).

---

## 1. Functional requirements

| ID | Requirement | Planned component | Planned tests | Acceptance criterion | Evidence / status |
|---|---|---|---|---|---|
| FR-B1 | Synthetic master and generator with simulated clock | `src/bitemporal_ledger/generator/`, `config/generator.yaml`, `scripts/generate_synthetic.py` | `tests/unit/test_generator.py` (9), `tests/property/test_generator_determinism.py` (2) | Same seed gives identical logical records and result hashes; synthetic labelling present; exact counts and seed logged | M2 Approved 2026-11-09 (seed 20261109 â†’ `dataset_hash=94839c5câ€¦`, two clean runs byte-identical; 22 total tests passed) |
| FR-B2 | AMFI NAV import adapter | `src/bitemporal_ledger/navigation/fundlens_adapter.py`, `scripts/import_nav.py`, `sql/migrations/*_nav.sql` | `tests/unit/test_fundlens_adapter.py`, `tests/integration/test_migrations.py`, idempotency and conflict checks | Idempotent; provenance recorded; non-positive/invalid NAVs rejected; no fabricated NAVs | M1 Approved 2026-11-09 (local PASS; 1,811,703 rows idempotent; GitHub Actions workflow configured, remote execution not performed) |
| FR-B3 | Immutable transaction revision ledger | `src/bitemporal_ledger/ledger/`, `sql/migrations/004â€“005_*.sql` | `tests/integration/test_ledger_corrections.py` (17) | Stable business IDs; revisions never updated/deleted; every accepted version reconstructable | M3 Approved 2026-11-09 (D-047 split: `txn_revision` immutable + trigger, `txn_revision_period` projection, GiST moved); ingestion 2,287; trigger + rebuild tested |
| FR-B4 | Bitemporal corrections | `src/bitemporal_ledger/ledger/service.py`, `sql/migrations/004â€“005_*.sql` | `tests/integration/test_ledger_corrections.py` (17) | Replace, void, reverse-and-replace explicit; prior version queryable; overlapping system periods prevented; invalid corrections rejected | M3 Approved 2026-11-09; K1/K2, rollback, deterministic ordering retained; split-date SWITCH and replay-ordering supplement verified |
| FR-B5 | As-of positions | `src/bitemporal_ledger/valuation/service.py` | `tests/integration/test_positions.py` (11) | `positions(account, valid_date, known_as_of)` returns units and cash using only versions known at K | M4 Approved 2026-11-09 (boundary tests verified: 5-day stale, MISSING_NAV, atomic multi-holding failure) |
| FR-B6 | Valuation | `src/bitemporal_ledger/valuation/service.py` | `tests/integration/test_positions.py` (11) | Units Ã— NAV plus cash; stale and missing NAV reported separately; no silent forward-fill | M4 Approved 2026-11-09 |
| FR-B7 | Performance engine | `src/bitemporal_ledger/performance/` | `tests/unit/test_performance.py` (17), `tests/integration/test_performance_replay.py` (1) | TWR, Modified Dietz, XIRR under documented conventions; hand-computed and independent-reference tests pass; structured XIRR status | M5 Approved 2026-11-09 (D-053); fixtures + reference verified; K1/K2 replay verified |
| FR-B8 | Immutable report snapshots | `src/bitemporal_ledger/reporting/` | `tests/integration/test_snapshots.py` (2) | Stores parameters, account, period, simulated generation time, `known_as_of`, NAV snapshot ID, calculation version, canonical payload and hash; replay compares payloads | M6 implemented (D-055); replay/restatement tested; sign-off pending |
| FR-B9 | Restatement and attribution | `src/bitemporal_ledger/reporting/snapshot.py` | `tests/integration/test_snapshots.py` (2) | For K1 < K2 lists affected accounts/periods, original and restated values, deltas, changed revisions and reasons | M6 implemented; sign-off pending |
| FR-B10 | Invariants | `src/portfolio/invariants/`, `sql/functions/invariants.sql`, pipeline gate | `tests/integration/test_invariants.py`, negative tests | Pipeline fails on negative units, cash-rule violations, unbalanced legs, valuation mismatch, replay mismatch beyond rounding | M0 designed; M7 target |
| FR-B11 | Dashboard and exports | `dashboard/`, `sql/marts/`, PBIP definitions, screenshots | Manual verification checklist, SQL reconciliation tests, screenshot evidence | Power BI pages 1–4; filters by synthetic account, date range and report version; summary export; synthetic label | **M9 visually accepted & frozen (Vicky 2026-11-10).** PostgreSQL-only PBIP (4 pages), marts/views, final E9 drawdown-quintile bar (654 solved, validated), screenshots in `docs/screenshots/`. Live Desktop render/interaction/screenshot-finality validation **manual** (not executed here). No further visual iterations. |
| FR-B12 | Reproducible pipeline | `Makefile`, `make.ps1`, `src/portfolio/cli.py`, `scripts/reproduce.py` | Clean-database run, two-run hash comparison, CI workflow | `make reproduce` from empty DB runs all checks, writes `RESULTS.md`, exits non-zero on critical failure; CI runs unit/property/integration/migration tests | M0 designed; M7 target |
| FR-B13 | Sensitivity study on real NAV paths | `config/sensitivity.yaml`, `src/portfolio/evaluation/sensitivity.py`, `RESULTS.md` generator | `tests/unit/test_sensitivity_stats.py`, integration run from frozen config | Executes pre-registered scenarios; all reported with n; no selective reporting; signed + absolute statistics | M0 draft config; M8 target |
| FR-B14 | Overwrite-in-place comparator | `src/bitemporal_ledger/reporting/comparator.py` | `tests/integration/test_snapshots.py` (comparator test) | Naive schema fed same transactions; reports which historical reports it can still reproduce and exactly what it loses; no archived payload retrieval | M6 implemented; sign-off pending |

---

## 2. Non-functional requirements

| ID | Requirement | Planned component | Test / evidence | Status |
|---|---|---|---|---|
| NFR-1 | PostgreSQL 15+; reference PostgreSQL 16 | `docker-compose.yml`, migrations | CI clean-database migration test | M1 target |
| NFR-2 | Python 3.12+; local 3.14.10 compatible | `pyproject.toml` | CI matrix or documented version; local test run | M1 target |
| NFR-3 | Decimal/NUMERIC only in financial paths | Domain, persistence, SQL | Static grep/rules, unit tests, property tests | M5 target |
| NFR-4 | No secrets in Git | `.gitignore`, `.env.example`, CI scan | Secret scan; manual review | M1 target |
| NFR-5 | No real personal data | Generator only | Data card and review | M2 target |
| NFR-6 | No AMFI redistribution | `.gitignore`, docs | Git history review; data card | M1 target |
| NFR-7 | Deterministic canonical output | Snapshot canonicaliser | Two-run hash comparison | M7 target |
| NFR-8 | CI green before milestone closure | `.github/workflows/ci.yml` | CI run evidence | M1â€“M10 |
| NFR-9 | Accessible documentation and briefings | `docs/` | M0â€“M10 briefings | M0 in progress |
| NFR-10 | No regulatory-compliance claim | README, dashboard footer, results | Wording review | M0/M9 |

---

## 3. PRD evaluation results traceability

| Result | PRD requirement | Produced by | Planned test/evidence | Status |
|---|---|---|---|---|
| E1 | Calculation correctness and independent reference error | Performance engine + reference | Hand fixtures, independent reference, max absolute error and case count in `RESULTS.md` | M5 target |
| E2 | Archived report replay count | Snapshot/replay | Integration replay test; count in `RESULTS.md` | M6 target |
| E3 | Overwrite comparator capabilities and losses | Comparator | Reconstruction test; count and loss list in `RESULTS.md` | M6 target |
| E4 | Restatement counts and impact | Restatement register | Integration test; counts and threshold shares in `RESULTS.md` | M6 target |
| E5 | Invariant totals and failures | Invariant runner | Invariant test; types/count/pass/fail in `RESULTS.md` | M7 target |
| E6 | As-of query p50/p95 with hardware, row counts and plans | SQL/indexes + benchmark | Benchmark script; plans in `RESULTS.md` | M7 target |
| E7 | Reproducibility hashes | Pipeline | Two clean runs; canonical hashes in `RESULTS.md` | **M7 implemented (recorded).** Prior double-run hash `ac6257e2â€¦` documented; **two clean `make reproduce` runs with matching logical hashes not re-executed 2026-11-10** (fresh RC rerun required in prepared env). |
| E8 | NAV-path sensitivity | Sensitivity study | Pre-registered config; distributions with n in `RESULTS.md` | **M8 complete (frozen).** Config `93fb380bâ€¦` preserved, 11,436 detail rows. |
| E9 | TWR vs XIRR under SIP schedules | Performance + sensitivity | Deterministic SIP windows; distribution in `RESULTS.md` | **M8 partial (frozen, documented).** 654/1,040 solved (386 excluded). Dashboard: deterministic drawdown-quintile bar (5 bands, 654/654, per-band validated; annualised XIRR minus period TWR, same 12-mo window). No methodology/config change. |

---

## 4. Documentation deliverables traceability

| Deliverable | PRD section | Location | Status |
|---|---|---|---|
| README with results, baselines, n, dates, limitations | 15, 19 | `README.md` | M10 target |
| BRD with current-process gap | 15 | `docs/BRD.md` | M0 complete for review |
| User stories | 15 | `docs/USER_STORIES.md` | M0 complete for review |
| Data card | 5.4, 15 | `docs/DATA_CARD.md` | M0 complete for review |
| Methodology with hand-computed fixtures | 8, 15 | `docs/METHODOLOGY.md` | M0 complete for review |
| Decision log | 15 | `DECISIONS.md` | M0 updated for review |
| Results | 12, 15 | `RESULTS.md` | M7/M8/M10 target |
| Progress | 15 | `docs/PROGRESS.md` | M0 started |
| M0 design review | 16 | `docs/M0_DESIGN_REVIEW.md` | M0 complete for review |
| Briefings | 15 | `docs/briefings/M<n>.md` | M0 complete for review; later milestones target |
| Screenshots | 15 | `docs/screenshots/` | M9 target |
| At least 10 ad-hoc SQL queries | 15 | `sql/adhoc/` | M9 target |
| Jira evidence | 17 | Local backlog or Jira export | Blocked: no Jira access established |

---

## 5. Milestone gate traceability

| Milestone | Exit gate | Evidence location | Status |
|---|---|---|---|
| M0 Discovery | Vicky approved the complete fixture appendix (F1â€“F19) and the FundLens NAV contract under Option A | `docs/M0_DESIGN_REVIEW.md`, `docs/METHODOLOGY.md`, `docs/FUNDLENS_NAV_CONTRACT.md` | Approved 2026-11-09 â€” M0 exit gate met and formally recorded |
| M1 Foundations | Idempotent import with checksum/provenance; CI green | `docs/PROGRESS.md`, CI run, import test | Approved 2026-11-09 (Vicky). Local execution PASS (11 tests; migrations applied/idempotent; import 1,811,703 rows idempotent); GitHub Actions workflow configured, remote execution not performed; checksum-tamper failure path implemented but not exercised (follow-up release verification item); no Git remote/push/publication. Evidence: `docs/briefings/M1.md`, `docs/PROGRESS.md`, `docs/NAV_EARLIEST_EVIDENCE.md`. |
| M2 Generator | Same seed gives identical hashes | `tests/property/test_generator_determinism.py`, `output/synthetic/run1|run2` file hashes | Approved 2026-11-09 (Vicky). Seed 20261109 `dataset_hash=94839c5cb0119c6501f592da2f7fef56ca3f6cbb04e5e49ba4adfaf3308b6cda`; two clean runs byte-identical; 22 tests passed. Evidence: `docs/briefings/M2.md` |
| M3 Ledger and corrections | Temporal, no-overlap, invalid-correction tests pass | `tests/integration/test_ledger_corrections.py`, `docs/briefings/M3.md`, `docs/M3_VERIFICATION_SUPPLEMENT.md` | Approved 2026-11-09 (Vicky, D-047 accepted). FR-B3/B4 complete; 17 M3 tests passed (full suite 39). Evidence: `docs/briefings/M3.md` |
| M4 Positions and valuation | As-of and valuation tests pass; stale NAV works | `tests/integration/test_positions.py`, `docs/briefings/M4.md` | Approved 2026-11-09 (Vicky, incl. 5-day stale, MISSING_NAV and atomic multi-holding boundary tests; full suite 50). Evidence: `docs/briefings/M4.md` |
| M5 Performance engine | E1 numbers generated; all fixtures pass | `RESULTS.md` E1, `docs/briefings/M5.md` | Approved 2026-11-09 (D-053); fixtures + reference verified; K1/K2 replay verified |
| M6 Snapshots and restatement | Section 2.2 scenario reproduces end-to-end | `tests/integration/test_snapshots.py`, `docs/briefings/M6.md` | Implemented 2026-11-09; Â§9 replay/restatement + comparator verified; awaiting Vicky's M6 sign-off |
| M7 Invariants and pipeline | `make reproduce` twice with identical hashes | `RESULTS.md`, `docs/briefings/M7.md` | Implemented 2026-11-09; `RESULTS.md` sha256 `ac6257e2â€¦` both runs; 12/12 invariants (1 stale expected); awaiting sign-off |
| M8 Sensitivity study | E8/E9 generated and limitations reviewed | `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `docs/briefings/M8.md` | Implemented 2026-11-09; 344 eligible / 30 selected; 11,436 detail rows; E8 complete, E9 partial (documented) |
| M9 Dashboard and SQL | Four pages built; screenshots committed; ten queries | `dashboard/PortfolioReport/`, `sql/adhoc/`, `sql/marts/`, `docs/briefings/M9.md`, `docs/M9_STATUS.md` | **Visually accepted & frozen (Vicky 2026-11-10).** PostgreSQL-only PBIP, 10/10 SQL evidence recorded, screenshots in `docs/screenshots/`, final E9 quintile chart validated. Live Power BI Desktop validation/interaction/screenshot-finality manual. |
| M10 Release | Definition of done met; tag v1.0.0 after approval | `README.md`, `RESULTS.md`, `docs/V1_0_0_RC_FINAL_REPORT.md` | **v1.0.0 RC (2026-11-10).** DB/file verifications + audits completed; prior local evidence recorded; **not re-executed:** tests/Ruff, tamper test, NAV idempotency rerun, two clean reproduce runs with matching hashes, Desktop validation, remote CI. No push/tag/release without Vicky approval. |

---

## 6. Open traceability gaps

- The FundLens live DB export query has not been executed; the contract is verified at schema/source-file level. See `docs/FUNDLENS_NAV_CONTRACT.md` section 6.
- The 86-files-on-disk vs 85-registered difference is reconciled in `docs/FUNDLENS_FILE_RECONCILIATION.md` (86 files, 85 ranges, 3 out-of-scope IDCW differences, zero Growth differences). No unresolved gap remains on that item.
- No Jira project exists; local backlog only. No Jira ticket is claimed.
- No implementation tests exist yet for FR-B1; all test paths above are planned, not passed.
- Migration checksum-tamper: detection/failure path implemented and previously exercised with regression test `tests/integration/test_migration_checksum.py` (recorded). **Not re-executed in 2026-11-10 verification session** (pytest/DB test env not run); migration checksums in live DB verified to match `sql/migrations/*.sql`.
- Earliest imported NAV verification (M2 pre-work, 2026-11-09): `docs/NAV_EARLIEST_EVIDENCE.md` verifies the 7 in-scope observations dated 2006-04-02 against `amfi_nav_20060401_20060629_c6beb9fb99bb.txt.gz`; the weekday was not treated as evidence of invalidity.
