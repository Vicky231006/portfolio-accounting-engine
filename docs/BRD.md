# Business Requirements Document — Portfolio Accounting & Performance Engine

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Owner | Vicky Dsilva |
| Document status | Draft for M0 review |
| Date | 2026-11-09 |
| Authoritative specification | `PRD.md` (PRD v2.0, 9 November 2026) |
| Build order | Project B — after FundLens, before TradeBreak |
| Classification | Educational prototype. Synthetic accounts; real AMFI NAV inputs. Not investment advice, not a production client system, not a regulatory-compliance claim. |

---

## 1. Business context

A wealth-management operation must answer two different questions about the same historical date:

1. **What was economically effective then?** For example, how many units did account A hold on 31 January, and what was the portfolio worth at that date's NAV?
2. **What did the system know when a report was issued?** For example, what did the 31 January report say at the moment it was generated, before a backdated correction arrived in February?

An ordinary table that overwrites transactions can answer only the first question, and only using today's understanding. After a backdated correction it cannot reconstruct the earlier report. This project builds an account-level portfolio subledger with explicit valid time and knowledge time, so both questions can be answered and the difference can be explained.

The business outcome is not “a temporal database”. The outcome is:

> A performance analyst can explain what a portfolio was worth, what the system knew when a report was issued, what changed later, and why reported performance moved.

---

## 2. Current process and gap

| Current process | Gap |
|---|---|
| Transactions are held in a current-state table; corrections overwrite the prior row. | The prior value is lost. A report generated before the correction cannot be reproduced value-for-value. |
| Reports are regenerated from today's data. | The regenerated report silently mixes periods and knowledge times. A user cannot tell whether a change is a market movement or a correction. |
| Performance is often reduced to one “return” number. | TWR, Modified Dietz and XIRR answer different questions. Showing one number without labelling its convention can mislead. |
| Cash and fund units are not reconciled as linked legs. | A purchase can look like a new client contribution; a switch can be mistaken for a withdrawal plus a contribution. |
| Corrections have no reason, source, actor or lineage. | A changed total cannot be attributed to the transaction revision that caused it. |
| Data provenance is informal. | A NAV value cannot be traced to a source file, checksum, retrieval time and validation outcome. |

The gap is therefore **record reconstruction and attribution**, not merely data storage.

---

## 3. Problem statement

Build a reproducible portfolio-accounting and performance-reporting engine that:

- maintains account cash and INR mutual-fund units;
- values holdings using real AMFI NAV observations obtained through FundLens;
- calculates TWR, Modified Dietz and XIRR under documented conventions;
- accepts backdated corrections without destroying prior revisions;
- reproduces a historical report from the data and code context that produced it;
- produces a restated report and attributes every changed figure to a changed transaction revision and reason;
- demonstrates the limitations of an overwrite-in-place design using the same transactions;
- proves correctness with hand-computed fixtures, independent references, property tests and a reproducible pipeline.

---

## 4. Users and their questions

| User | Main question | System capability |
|---|---|---|
| Portfolio operations analyst | What transactions and positions are currently recognised for an account? | Ledger, current projection, positions, correction history |
| Performance analyst | What was the account's return for a period, using what was known at time K? | TWR, Modified Dietz, XIRR, report replay |
| Operations / team lead | Which reports changed after corrections, and why? | Restatement register, impact attribution, dashboard |
| Developer / data engineer | Can the result be rebuilt from a clean database and the documented inputs? | `make reproduce`, migrations, checksums, tests, CI |

---

## 5. Scope

### 5.1 In scope (v1)

- Synthetic investors, accounts and account status.
- INR-denominated mutual-fund holdings (Growth plans only) and account cash.
- Transaction types: `CONTRIBUTION`, `WITHDRAWAL`, `PURCHASE`, `REDEMPTION`, `SIP_INSTALMENT`, `SWITCH`.
- Correction lifecycle: replace, void, reverse-and-replace.
- Real AMFI NAV observations with provenance.
- As-of positions and cash using valid date and knowledge timestamp.
- Valuation using units × NAV plus cash, with explicit stale/missing NAV behaviour.
- TWR, Modified Dietz and XIRR.
- Immutable report snapshots, replay, restatement attribution and an overwrite-in-place comparator.
- Financial and temporal invariants.
- Real-NAV-path sensitivity study from a pre-registered config.
- PostgreSQL analytical marts.
- Power BI dashboard (four pages).
- At least ten ad-hoc SQL queries, each headed by its business question.
- CLI, reproducible pipeline, automated tests, CI and documentation.
- Jira-compatible backlog. If Jira access is unavailable, a local backlog is provided and the limitation is stated; tickets are not claimed to exist.

### 5.2 Out of scope (binding)

- Real people, client data, PAN, Aadhaar, brokerage or custodian integrations.
- Trade execution, investment recommendations, optimisation, tax lots, tax engines, stamp duty.
- IDCW payouts and reinvestment (AMFI NAV files do not supply declared IDCW amounts).
- Fees and charges (stretch after v1.0.0).
- Multi-currency and FX; equities, bonds, derivatives, alternatives; exit loads; NAV cut-off times.
- GIPS compliance or any regulatory-compliance claim.
- Kafka, microservices, web API, LLM features, mobile app.
- Additional instrument types or a generic temporal-database demonstration.

---

## 6. Business requirements and PRD traceability

The functional requirements are the PRD's `FR-B1` to `FR-B14`. This BRD adds the business rationale; the implementation-to-test mapping is in `docs/REQUIREMENTS_TRACEABILITY.md`.

| ID | Business requirement | Business reason |
|---|---|---|
| FR-B1 | Synthetic master and generator with simulated clock | Produces a safe, reproducible dataset and makes K1/K2 meaningful. |
| FR-B2 | AMFI NAV import adapter | Uses real market observations with traceable provenance; rejects fabricated or invalid values. |
| FR-B3 | Immutable transaction revision ledger | Preserves what was accepted even after a correction. |
| FR-B4 | Bitemporal corrections | Supports replace, void and reverse-and-replace while retaining prior versions and rejecting invalid downstream states. |
| FR-B5 | As-of positions | Answers “what did we hold on date D, using only what was known at K?” |
| FR-B6 | Valuation | Produces a defensible portfolio value with Decimal/NUMERIC arithmetic and explicit stale-NAV treatment. |
| FR-B7 | Performance engine | Distinguishes period TWR, period Modified Dietz and annualised money-weighted XIRR. |
| FR-B8 | Immutable report snapshots | Makes the issued report reproducible and comparable. |
| FR-B9 | Restatement and attribution | Explains which report figures moved and which transaction revision caused each movement. |
| FR-B10 | Invariants | Fails the pipeline on negative units, cash-rule violations, unbalanced legs, valuation mismatches and replay drift. |
| FR-B11 | Dashboard and exports | Gives operations and performance users a usable view without hiding temporal and synthetic-data caveats. |
| FR-B12 | Reproducible pipeline | Every headline number is generated, not typed; a clean run must exit non-zero on critical failure. |
| FR-B13 | Sensitivity study on real NAV paths | Quantifies how controlled transaction errors move reported returns, without claiming real-world error prevalence. |
| FR-B14 | Overwrite-in-place comparator | Demonstrates, rather than asserts, what an ordinary current-state design loses. |

---

## 7. Success criteria

The project is successful when all of the following are true:

1. `make reproduce` rebuilds the database, imports the documented NAV input, generates the seeded data, runs calculations and evaluation, executes critical invariants and writes `RESULTS.md` from an empty project database.
2. Two clean runs with the same inputs and seed produce identical logical results and canonical result hashes.
3. Hand-computed fixtures and independent reference implementations agree with production calculations within the documented tolerance.
4. A correction recorded after K1 cannot alter a `known_as_of = K1` query; the same correction changes the K2 view where effective.
5. An archived report is reproduced by recalculation from its stored metadata, and the canonical payload and hash match.
6. The restated report lists every changed figure, the changed revision and the reason.
7. The overwrite comparator is tested by reconstructing an old report from its retained data; it fails for corrected accounts and the failure is explained.
8. Invariants pass, or the pipeline fails with a clear reason.
9. The sensitivity study runs every pre-registered scenario and reports n, signed median, median absolute, p95 absolute and threshold shares.
10. The dashboard works with synthetic accounts and real AMFI NAV inputs, labels synthetic data everywhere, and keeps TWR and XIRR separate.
11. Documentation, briefings, decision log, traceability matrix, screenshots and at least ten ad-hoc SQL queries are complete.
12. Vicky can independently explain valid time, knowledge time, transaction revisions, valuation, TWR, Modified Dietz, XIRR, internal vs external flows, allotment-date treatment, snapshots/replay, restatement attribution and the sensitivity-study limits.

---

## 8. Assumptions and constraints

- PostgreSQL 15+ is required; FundLens uses PostgreSQL 16, so PostgreSQL 16 is the reference.
- Python 3.12+ is required; the local machine currently has Python 3.14.10. Code must remain compatible with 3.12+.
- All financial calculation paths use Python `Decimal` and PostgreSQL `NUMERIC`; no binary floating point for money, NAV, units or return inputs.
- AMFI NAV data is obtained through a read-only FundLens-derived contract. Nothing from AMFI is redistributed; data files stay local and git-ignored.
- Synthetic accounts and transactions use a fixed seed and simulated knowledge clock. Wall-clock time is audit metadata only.
- No secrets, real personal data or data-bearing `.pbix` files are committed.
- Power BI Desktop is the dashboard tool; PBIP definitions and screenshots are version-controlled where feasible.
- The project is an educational prototype. It does not claim production readiness, regulatory compliance or real client usage.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Valid time confused with knowledge time | Worked K1/K2 example; simulated clock; automated temporal tests; briefing. |
| Internal movements counted as external flows | Explicit flow taxonomy; linked legs; property tests. |
| XIRR picks an arbitrary root or hides non-convergence | Structured result statuses; root scan; bisection fallback; multiple-root and no-root tests. |
| Correction cascades into invalid later state | Recompute downstream positions; reject the entire correction group with a reason; audit rejection. |
| NAV gaps, renames or restatements | Stable AMFI scheme code; FundLens scheme history; stale-NAV policy; conflict recording. |
| Synthetic data looks real | Label in README, dashboard, results, data card, screenshots and resume wording. |
| Sensitivity study cherry-picked | Pre-registered config; all scenarios reported with n; no selective reporting. |
| Scope overwhelms delivery | Milestone gates; binding out-of-scope list; fees and IDCW deferred. |
| Compliance claim | Educational-prototype wording; no GIPS/SEBI compliance claim. |
| FundLens coupling | Read-only contract; no FundLens modification; documented export schema and checksum. |

---

## 10. Glossary

| Term | Meaning |
|---|---|
| Valid time / effective date | The business date on which a transaction or position economically applies. |
| Knowledge time / recorded time | The simulated UTC timestamp at which the system accepted a transaction version. |
| As-of state | Positions and cash effective through a valid date, using only versions known at a requested timestamp. |
| Business transaction ID | Stable identifier for the economic transaction across revisions. |
| Revision | One accepted version of a business transaction. Revisions are append-only. |
| Correction group | An atomic group containing a lifecycle action and all recomputed linked legs. |
| External flow | Contribution or withdrawal between the investor and the portfolio. |
| Internal movement | Purchase, redemption or switch between cash and fund units; never an external flow. |
| TWR | Time-weighted return; removes the effect of external flow timing; period measure under this project's conventions. |
| Modified Dietz | A period-return approximation using weighted external flows. |
| XIRR | Money-weighted annualised return on dated investor cash flows, including terminal value. |
| Stale NAV | A NAV carried forward because the valuation date has no observation, within the documented limit. |
| Snapshot | Immutable stored report payload plus the metadata needed to retrieve or recalculate it. |
| Restatement | A new report using later knowledge, compared with the original report. |

---

## 11. Approval

This BRD is part of the M0 gate. Material financial conventions are proposed in `docs/M0_DESIGN_REVIEW.md` and `DECISIONS.md`. Implementation of financial logic must not begin until Vicky approves those conventions.

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner | Vicky Dsilva | Pending M0 review | |
| Implementation agent | — | Prepared for review | 2026-11-09 |
