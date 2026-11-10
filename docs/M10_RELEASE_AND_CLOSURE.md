# M10 — Release and Project Closure Report

**Project:** Portfolio Accounting & Performance Engine (`portfolio-accounting-engine` / `bitemporal-ledger`)  
**Specification:** PRD v2.0  
**Milestones:** M0–M10  
**Report date:** 10 November 2026  
**Repository:** [Vicky231006/portfolio-accounting-engine](https://github.com/Vicky231006/portfolio-accounting-engine)  
**Release status:** Public release-candidate snapshot on `main`; final v1.0.0 tag/release not claimed.

## 1. Executive summary

The project implements an educational portfolio subledger and performance-reporting workflow for a simulated wealth-management operation. It uses synthetic investors, accounts, transactions and corrections, with real AMFI mutual-fund NAV observations as market inputs.

The central business problem is historical reporting after a backdated correction. A performance analyst needs to answer both what was economically effective on a past date and what the system knew when a report was issued. The system therefore preserves transaction revisions, reconstructs positions as of a valid date and knowledge timestamp, values holdings, calculates performance, archives report snapshots, replays original reports and attributes later restatements.

The implementation scope M0–M10 is delivered and documented. The repository is public on GitHub `main`. The current evidence supports describing it as a **release candidate**, not as a fully re-verified final v1.0.0 release. The final verification report explicitly records checks that were not re-executed in the release-candidate environment.

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
| M2 — Generator | Deterministic synthetic investors, accounts, transactions, correction intents and simulated knowledge clock | `src/bitemporal_ledger/generator/`, `config/generator.yaml`, `docs/briefings/M2.md` |
| M3 — Ledger and corrections | Immutable revision facts, temporal/current projections, atomic correction operations, rejection audit and no-overlap constraint | `src/bitemporal_ledger/ledger/`, migrations 004–005, `docs/M3_VERIFICATION_SUPPLEMENT.md` |
| M4 — Positions and valuation | As-of positions, cash, holdings valuation, stale-NAV policy and reconciliation | `src/bitemporal_ledger/valuation/`, `tests/integration/test_positions.py` |
| M5 — Performance | Decimal TWR, Modified Dietz, XIRR, independent reference and methodology-to-test mapping | `src/bitemporal_ledger/performance/`, `docs/M5_METHODOLOGY_MAPPING.md` |
| M6 — Snapshots and restatement | Canonical report payloads, archived retrieval, exact replay, later restatement and overwrite comparator | `src/bitemporal_ledger/reporting/`, `tests/integration/test_snapshots.py` |
| M7 — Invariants and pipeline | Invariant checks and deterministic reproduction pipeline | `src/bitemporal_ledger/invariants/`, `scripts/reproduce.py`, `RESULTS.md` |
| M8 — Sensitivity | Frozen, pre-registered sensitivity study on real NAV paths | `config/sensitivity.yaml`, `results/sensitivity_detail.csv`, `results/E9_COVERAGE.md` |
| M9 — Dashboard and SQL | Four-page PostgreSQL-only Power BI PBIP report, marts and 10 ad-hoc SQL queries | `dashboard/PortfolioReport/`, `sql/marts/`, `sql/adhoc/`, `docs/M9_STATUS.md` |
| M10 — Release | Documentation audit, traceability, repository hygiene, evidence/limitations report and RC packaging | `docs/V1_0_0_RC_FINAL_REPORT.md`, `docs/RELEASE_CANDIDATE.md` |

## 4. Data and reproducibility evidence

### 4.1 Real market data

- Canonical AMFI NAV snapshot: **1,811,703 observations**.
- Scope: **85 approved raw-file ranges**, 779 schemes.
- Date range: 2 April 2006 to 6 November 2026.
- Six M4/M6/test NAV fixtures are isolated in a separate `test_fixture_nav_seeds` snapshot and are not counted as canonical AMFI observations.
- Canonical NAV observations have zero duplicate `(snapshot, scheme, date)` keys in the recorded database audit.

Raw AMFI files are not included in the repository. The project consumes the locally available, read-only FundLens raw-file contract. FundLens itself was not modified.

### 4.2 Synthetic portfolio data

The documented baseline generator configuration uses seed `20261109`, 12 synthetic accounts and 2,287 generated transactions. The baseline dataset hash begins `94839c5c`. The dashboard/reproduction demonstration includes a deterministic applied correction, rejected correction, original report snapshot, replay and restatement.

All accounts, investors, transactions and correction behaviour are synthetic. These counts do not represent real clients, AUM, users or transaction-error prevalence.

### 4.3 Sensitivity evidence

- Frozen M8 configuration SHA-256: `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`.
- Detail observations: 11,436.
- E9 eligible windows: 1,040.
- E9 solved observations: 654.
- E9 excluded observations: 386, documented as no-root/solver-domain exclusions.
- E9 dashboard presentation: five deterministic drawdown quintiles with counts 131 / 131 / 131 / 131 / 130.

E9 reports annualised XIRR minus period TWR over the same 12-month SIP window. These are different return measures; their difference is not presented as an error. The 386 excluded windows remain visible in the limitations. The sensitivity scenarios are controlled experiments, not measured real-world error rates.

## 5. Verification status

The release-candidate evidence distinguishes checks verified in the final audit from prior recorded test runs and checks not freshly re-executed.

| Check | Recorded status | Qualification |
|---|---|---|
| Canonical NAV provenance/count | Verified in DB/files | 1,811,703 canonical observations; six fixtures isolated separately |
| Applied migrations/checksums | Verified | Seven migrations recorded with checksums matching committed SQL files |
| E9 quintile mart | Verified | 654 distinct solved observations assigned once across five bands; per-band statistics checked |
| Git/secret scan | Completed | `.env` excluded; placeholders only in `.env.example`; raw files and data-bearing binaries excluded |
| Full test suite | Prior successful run: 75 passed | Not freshly rerun in the final RC verification environment |
| Ruff | Prior clean result recorded | Not freshly rerun in the final RC verification environment |
| Migration checksum-tamper test | Test exists; prior exercise recorded | Not rerun in the final RC verification environment |
| NAV source re-import/idempotency | Import path and DB state inspected | Fresh source re-import was not run in the final RC pass |
| Two clean `make reproduce` runs | Prior matching hash recorded (`ac6257e2…`) | Fresh double run from an empty database was not re-established in the final RC pass |
| Power BI Desktop | PBIP and screenshots preserved; owner reviewed/froze visuals | Full refresh/interaction validation was not independently re-executed in the final RC environment |
| GitHub Actions | Workflow configured | Remote CI execution not recorded as successful |
| E6 query latency | Not claimed | p50/p95 benchmark values are not published |

**Interpretation:** the repository contains the implementation and evidence from prior milestone verification, but the final RC audit did not freshly rerun every automated and manual check. Do not describe all checks as freshly passing.

## 6. Dashboard status

The four-page Power BI PBIP report is frozen by the project owner. Page 4 uses the accepted drawdown-quintile bar-chart presentation for E9 rather than a scatter plot. The PBIP definitions and screenshots are committed; the data-bearing `.pbix` file is excluded.

The four pages cover:

1. Portfolio overview.
2. Account drilldown.
3. Restatements and audit.
4. Sensitivity analysis.

The report connects to the local PostgreSQL database (`127.0.0.1:5434`, database `bitemporal_ledger`). Full Desktop refresh/interaction verification is a documented manual limitation in the RC evidence.

## 7. Git and publication record

The public repository is [`Vicky231006/portfolio-accounting-engine`](https://github.com/Vicky231006/portfolio-accounting-engine), with work pushed to `main`.

The initial Git history was created during release-candidate consolidation, after the milestone implementation had already been completed and documented. The two commits therefore represent the RC snapshot and subsequent hygiene corrections; they are not a chronological record of every M0–M10 implementation step.

| Commit | Purpose |
|---|---|
| `46023b22344adf1ecc7fd981350aafc8084cf039` | Initial v1.0.0 release-candidate snapshot |
| `536aa76d6c408f6711a6b9d0f73215f283e4eb6e` | Isolate six test NAV fixtures and harden local PostgreSQL configuration |

No final v1.0.0 tag or GitHub Release is claimed in this report. The current public state should be described as a release-candidate snapshot, with the outstanding verification limitations above.

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

The remaining work is verification, not feature development:

1. Re-run the full test suite and Ruff in the pinned Python 3.12/PostgreSQL 16 environment.
2. Re-run the checksum-tamper regression test on a disposable database.
3. Re-import the canonical AMFI source and demonstrate idempotency.
4. Run two clean `make reproduce` executions from empty project databases and compare logical hashes.
5. Complete/record the final Power BI Desktop refresh and interaction checks.
6. Record an actual GitHub Actions run if remote CI evidence is desired.

Until those checks are freshly completed, retain the **release-candidate** label and the documented limitations. No production, client-use, regulatory-compliance or real-world prevalence claims are supported.
