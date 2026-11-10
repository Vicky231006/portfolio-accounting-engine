# Development History — Portfolio Accounting & Performance Engine

This document summarises the project's engineering progression from the approved PRD through M10. It complements the source-level Git history; it does not attempt to reconstruct or fabricate historical commits.

## Why Git shows only two commits

Git versioning was initialised during release-candidate consolidation, after the M0–M10 implementation work had already been performed and documented. The public repository therefore has two commits representing:

1. The initial release-candidate source snapshot.
2. A follow-up hygiene commit that separated test NAV fixtures from canonical AMFI data and hardened local PostgreSQL configuration.

These commits are not a chronological commit-by-commit record of the original development. The contemporaneous PRD, decision log, progress log, milestone briefings, traceability matrix, tests and result artifacts provide the development evidence instead. No artificial commits have been created to imply otherwise.

## Milestone history

| Milestone | Engineering progression | Evidence |
|---|---|---|
| M0 — Discovery | Converted the wealth-management reporting problem into a PRD, BRD, stories, NAV contract, financial fixtures and explicit design decisions. | `PRD.md`, `docs/BRD.md`, `docs/M0_DESIGN_REVIEW.md`, `docs/METHODOLOGY.md` |
| M1 — Foundations | Established PostgreSQL 16, versioned migrations, Python tooling, CI configuration and a provenance-aware AMFI NAV adapter/import. | `sql/migrations/`, `src/bitemporal_ledger/navigation/`, `docs/briefings/M1.md` |
| M2 — Generator | Built deterministic synthetic investors, accounts, transactions and correction intents with a simulated knowledge clock and canonical hashes. | `src/bitemporal_ledger/generator/`, `config/generator.yaml`, `docs/briefings/M2.md` |
| M3 — Ledger and corrections | Implemented immutable transaction revisions, temporal projections, bitemporal queries, atomic corrections, rejection audit and GiST no-overlap enforcement. | `src/bitemporal_ledger/ledger/`, `docs/M3_VERIFICATION_SUPPLEMENT.md`, `docs/briefings/M3.md` |
| M4 — Positions and valuation | Derived cash and holdings as of valid date/knowledge time; added NAV-based valuation, stale-NAV controls and reconciliation invariants. | `src/bitemporal_ledger/valuation/`, `tests/integration/test_positions.py`, `docs/briefings/M4.md` |
| M5 — Performance engine | Implemented Decimal TWR, Modified Dietz and XIRR with hand-computed fixtures and an independent reference solver. | `src/bitemporal_ledger/performance/`, `docs/M5_METHODOLOGY_MAPPING.md`, `docs/briefings/M5.md` |
| M6 — Snapshots and restatement | Added immutable report snapshots, canonical payload hashes, exact replay, later restatement and overwrite-in-place comparison. | `src/bitemporal_ledger/reporting/`, `tests/integration/test_snapshots.py`, `docs/briefings/M6.md` |
| M7 — Invariants and pipeline | Connected migrations, NAV import, generator, ledger, report workflow and invariants into a deterministic reproduction pipeline. | `scripts/reproduce.py`, `src/bitemporal_ledger/invariants/`, `RESULTS.md`, `docs/briefings/M7.md` |
| M8 — Sensitivity | Ran and froze the pre-registered transaction-error sensitivity study on real NAV paths; documented partial E9 coverage and exclusions. | `config/sensitivity.yaml`, `results/sensitivity_detail.csv`, `results/E9_COVERAGE.md`, `docs/briefings/M8.md` |
| M9 — Dashboard and SQL | Built and visually froze the four-page Power BI PBIP report, PostgreSQL marts and 10 business-question SQL queries. | `dashboard/PortfolioReport/`, `sql/marts/`, `sql/adhoc/`, `docs/M9_STATUS.md` |
| M10 — Release candidate | Audited reproducibility evidence, provenance, documentation, traceability, Git contents and limitations; prepared the public RC snapshot. | `docs/V1_0_0_RC_FINAL_REPORT.md`, `docs/RELEASE_CANDIDATE.md`, `docs/briefings/M10.md` |

## Supporting evidence

- `DECISIONS.md` records the reasoning, alternatives and consequences for important architecture and financial-methodology choices.
- `docs/PROGRESS.md` records milestone status and exit-gate evidence.
- `docs/REQUIREMENTS_TRACEABILITY.md` maps PRD requirements to implementation, tests and evidence.
- `docs/briefings/M0.md` through `docs/briefings/M10.md` explain each milestone and provide interview-oriented notes.
- `RESULTS.md` records measured outputs and clearly labels prior evidence that was not freshly rerun during final RC verification.

## Interpretation

The milestone sequence describes the work performed and its evidence trail. It should not be interpreted as proof that every milestone was represented by an individual Git commit. The two public commits document release-candidate packaging and subsequent hygiene corrections; the milestone artifacts provide the detailed development record.
