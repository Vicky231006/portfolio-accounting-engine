# M10 — Release and Project Closure Report

**Project:** Portfolio Accounting & Performance Engine (`portfolio-accounting-engine` / `bitemporal-ledger`)  
**Specification:** PRD v2.0  
**Milestones:** M0–M10  
**Report date:** 11 November 2026  
**Repository:** [Vicky231006/portfolio-accounting-engine](https://github.com/Vicky231006/portfolio-accounting-engine)  
**Release status:** **v1.0.0 final release** — tagged `v1.0.0` and published from `main` as the Portfolio Accounting & Performance Engine v1.0.0.

## 1. Executive summary

The project implements an educational portfolio subledger and performance-reporting workflow for a simulated wealth-management operation. It uses synthetic investors, accounts, transactions and corrections, with real AMFI mutual-fund NAV observations as market inputs.

The central business problem is historical reporting after a backdated correction. A performance analyst needs to answer both what was economically effective on a past date and what the system knew when a report was issued. The system therefore preserves transaction revisions, reconstructs positions as of a valid date and knowledge timestamp, values holdings, calculates performance, archives report snapshots, replays original reports and attributes later restatements.

The implementation scope M0–M10 is delivered and documented. The final verification pass re-executed the automated gates and the deterministic reproduction pipeline; the evidence supports describing the delivered state as **v1.0.0** of the Portfolio Accounting & Performance Engine.

## 2. Business problem and intended use

A current portfolio balance alone is insufficient when a transaction is corrected after a historical report has been produced. Overwriting the original transaction may provide the corrected present state but lose the information needed to reproduce the earlier report.

This project demonstrates an auditable alternative:

1. Keep accepted transaction revision facts immutable.
2. Represent economic effective time separately from system knowledge time.
3. Reconstruct cash and holdings for a selected account, valid date and `known_as_of` timestamp.
4. Value positions using versioned AMFI NAV snapshots and explicit stale/missing-NAV rules.
5. Calculate TWR, Modified Dietz and XIRR under documented cash-flow and date conventions.
6. Store report snapshots with the inputs and versions needed for replay.
7. Produce later restatements and attribute changed values to transaction revisions and correction reasons.

Bitemporal modelling is the auditability mechanism; the product is the portfolio accounting and reporting workflow.

## 3. Delivered scope by milestone

| Milestone | Delivered capability | Evidence location |
|---|---|---|
| M0 — Discovery | PRD review, BRD, user stories, data contract, hand-computed fixtures, decisions and traceability | `docs/M0_DESIGN_REVIEW.md`, `docs/METHODOLOGY.md`, `DECISIONS.md` |
| M1 — Foundations | PostgreSQL 16, migrations, NAV adapter/import, provenance and CI configuration | `sql/migrations/`, `src/bitemporal_ledger/navigation/`, `docs/briefings/M1.md` |
| M2 — Generator | Deterministic synthetic investors, accounts, transactions, SIPs, switches and correction intents and simulated knowledge clock | `src/bitemporal_ledger/generator/`, `config/generator.yaml`, `docs/briefings/M2.md` |
| M3 — Ledger and corrections | Immutable revision facts, temporal/current projections, atomic correction operations, rejection audit and no-overlap constraint | `src/bitemporal_ledger/ledger/`, migrations 004–005, `docs/M3_VERIFICATION_SUPPLEMENT.md` |
| M4 — Positions and valuation | As-of positions, cash, holdings valuation, stale-NAV policy and reconciliation | `src/bitemporal_ledger/valuation/`, `tests/integration/test_positions.py` |
| M5 — Performance | Decimal TWR, Modified Dietz, XIRR, independent reference and methodology-to-test mapping | `src/bitemporal_ledger/performance/`, `docs/M5_METHODOLOGY_MAPPING.md` |
| M6 — Snapshots and restatement | Canonical report payloads, archived retrieval, exact replay, later restatement and overwrite comparator | `src/bitemporal_ledger/reporting/`, `tests/integration/test_snapshots.py` |
| M7 — Invariants and pipeline | Invariant checks and deterministic reproduction pipeline | `src/bitemporal_ledger/invariants/`, `scripts/reproduce.py`, `RESULTS.md` |
| M8 — Sensitivity | Frozen, pre-registered sensitivity study on real NAV paths | `config/sensitivity.yaml`, `results/sensitivity_detail.csv`, `results/E9_COVERAGE.md` |
| M9 — Dashboard and SQL | Four-page PostgreSQL-only Power BI PBIP report, marts and 10 ad-hoc SQL queries | `dashboard/PortfolioReport/`, `sql/marts/`, `sql/adhoc/`, `docs/M9_STATUS.md` |
| M10 — Release | Documentation audit, traceability, repository hygiene, evidence/limitations report and release packaging | `docs/M10_RELEASE_AND_CLOSURE.md`, `docs/V1_0_0_RC_FINAL_REPORT.md`, `docs/RELEASE_CANDIDATE.md` |

## 4. Data and reproducibility evidence

### 4.1 Real market data

- Canonical AMFI NAV snapshot: **1,811,703 observations**.
- Scope: **85 approved raw-file ranges**, 779 schemes.
- Date range: 2 April 2006 to 6 November 2026.
- Six M4/M6/test NAV fixtures are isolated in a separate `test_fixture_nav_seeds` snapshot and are not counted as canonical AMFI observations.
- Canonical NAV observations have zero duplicate `(snapshot, scheme, date)` keys in the recorded database audit.

Raw AMFI files are not included in the repository. The project consumes the locally available, read-only FundLens raw-file contract. FundLens itself was not modified.

### 4.2 Synthetic portfolio data

The documented baseline generator configuration uses seed `20261109`, the canonical profile (`config/generator.yaml`) and the scaled synthetic dataset: **600 investors / 1,000 accounts**, **209,937** transactions and **14,926** correction intents, with dataset SHA-256 `833f7f5703c1bbbd8142f0db5c11945b97bf2f844307c9a59887b886b62a2f8a` and config SHA-256 `ed9891222f7817344b596408ffa1947da0724140067592c89ca7d5d94fa6afbb`. The dashboard/reproduction demonstration includes a deterministic applied correction, rejected correction, original report snapshot, replay and restatement.

All accounts, investors, transactions and correction behaviour are synthetic. These counts do not represent real clients, AUM, users or transaction-error prevalence.

### 4.3 Sensitivity evidence

- Frozen M8 configuration SHA-256: `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`.
- Detail observations: 11,436.
- E9 eligible windows: 1,040.
- E9 solved observations: **1,040** (after the terminal-valuation/backdating defect correction, zero excluded).
- E9 excluded observations: **0** in the final corrected state; the earlier 386 exclusions are preserved as archived evidence in `results/archive/e9_v1_frozen/`.
- E9 dashboard presentation: five deterministic drawdown quintiles with counts 131 / 131 / 131 / 131 / 130 for the final solved set.

E9 reports annualised XIRR minus period TWR over the same 12-month SIP window. These are different return measures; their difference is not presented as an error. The sensitivity scenarios are controlled experiments, not measured real-world error rates.

## 5. Verification status

The final v1.0.0 verification pass freshly re-executed the automated gates and the deterministic reproduction pipeline, and distinguishes those checks from historical recorded evidence.

| Check | Recorded status | Qualification |
|---|---|---|
| Canonical NAV provenance/count | Verified in DB/files | 1,811,703 canonical observations; six fixtures isolated separately |
| Applied migrations/checksums | Verified | Seven migrations recorded with checksums matching committed SQL files |
| E9 quintile mart | Verified | Final solved set: 1,040 observations assigned once across five bands; per-band statistics checked |
| Git/secret scan | Completed | `.env` excluded; placeholders only in `.env.example`; raw files and data-bearing binaries excluded |
| Full test suite | **77 passed** (fresh final pass, incl. 35 PostgreSQL integration tests) | Freshly re-executed 2026-11-11 |
| Ruff | **Clean** (fresh final pass) | Freshly re-executed 2026-11-11 |
| Migration checksum-tamper test | **Passed** (fresh final pass) | Freshly re-executed via integration suite |
| NAV source re-import/idempotency | **Verified** | Fresh re-import and idempotency demonstrated in clean runs (inserted=1,811,703; skipped on re-run) |
| Two clean `make reproduce` runs | **Passed** (fresh, final artefact set) | Byte-identical `RESULTS.md` sha256 `e742e2f07231adcaedf9aceef3b196583e7758a863512f372544e0f03ef7a241` |
| Power BI Desktop | PBIP and screenshots preserved; owner reviewed/froze visuals | Live refresh/interaction validation manual; not re-executed in final pass |
| GitHub Actions | Workflow configured | Remote CI execution status not recorded in final pass |
| E6 query latency | **Benchmarked** | p50/p95 measured with/without `core.ix_txn_revision_recorded_at`; result digests identical; environment-specific |

**Interpretation:** the final v1.0.0 verification pass freshly re-executed the automated gates and the deterministic reproduction pipeline; all recorded checks are freshly passing except the manually-executed Power BI Desktop refresh/interaction and the remote GitHub Actions execution, which remain documented limitations.

## 6. Dashboard status

The four-page Power BI PBIP report is frozen by the project owner. Page 4 uses the accepted drawdown-quintile bar-chart presentation for E9 rather than a scatter plot. The PBIP definitions and screenshots are committed; the data-bearing `.pbix` file is excluded.

The four pages cover:

1. Portfolio overview.
2. Account drilldown.
3. Restatements and audit.
4. Sensitivity analysis.

The report connects to the local PostgreSQL database (`127.0.0.1:5434`, database `bitemporal_ledger`). Full Desktop refresh/interaction verification is a documented manual limitation in the final evidence.

## 7. Git and publication record

The public repository is [`Vicky231006/portfolio-accounting-engine`](https://github.com/Vicky231006/portfolio-accounting-engine), with work pushed to `main`.

The final public state for v1.0.0 was published as tag `v1.0.0` with a GitHub Release accompanying the verified state.

| Commit | Purpose |
|---|---|
| `46023b22344adf1ecc7fd981350aafc8084cf039` | Initial v1.0.0 release-candidate snapshot |
| `536aa76d6c408f6711a6b9d0f73215f283e4eb6e` | Isolate six test NAV fixtures and harden local PostgreSQL configuration |

No release-candidate label is retained for the delivered v1.0.0 state.

## 8. Security, privacy and scope boundaries

- No real client, investor or account personal data is included.
- Synthetic portfolio data is labelled in documentation and dashboard footers.
- Raw AMFI NAV archives are not committed.
- `.env`, database dumps, database volumes, local caches and data-bearing `.pbix` files are excluded.
- PostgreSQL is bound to loopback (`127.0.0.1:5434`) and obtains its local password from an untracked `.env` file.
- FundLens is a read-only source dependency; it was not modified.
- The project does not execute trades, provide recommendations, calculate taxes/fees, or claim SEBI/GIPS/SEC compliance.

## 9. Final assessment and next steps

The project delivers a substantial, technically defensible educational prototype covering portfolio accounting, temporal corrections, valuation, investment performance, historical replay, sensitivity analysis and reporting.

The strongest demonstration is the end-to-end K1/K2 workflow: a report is generated using the original transaction knowledge, a later correction is accepted, the original report remains reproducible, and a restatement shows the changed values and their cause.

Final v1.0.0 release closure items are complete:

1. Full test suite and Ruff re-executed and passing.
2. Checksum-tamper regression test passed on a disposable database.
3. Canonical AMFI source re-import and idempotency demonstrated.
4. Two clean `make reproduce` executions from empty project databases produced byte-identical `RESULTS.md`.
5. Power BI Desktop refresh/interaction checks remain a documented manual step.
6. GitHub Actions remote execution status remains a documented limitation.

The delivered v1.0.0 artefact is closed; no production, client-use, regulatory-compliance or real-world prevalence claims are supported.
