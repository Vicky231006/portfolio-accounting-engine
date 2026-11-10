# User Stories and Acceptance Criteria

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Status | Draft for M0 review |
| Date | 2026-11-09 |
| Source | PRD v2.0 (`PRD.md`), FR-B1 to FR-B14 |

Stories are grouped by the PRD's eight Jira epics. Each story has acceptance criteria that must be demonstrated by an automated test or a recorded manual check. A story is **Done** only when its acceptance criteria pass, evidence exists and the implementation is verified.

---

## Epic 1 — Foundation and market data

### US-1.1 — Reproducible local environment
**As a** developer, **I want** a documented PostgreSQL + Python environment, **so that** the project can be rebuilt on a clean machine.

**Acceptance criteria**
- `docker-compose.yml` starts PostgreSQL 15+ (reference: 16).
- Versioned migrations apply in order and record checksums.
- `make reproduce` and a Windows-friendly equivalent are documented.
- `.env.example` contains placeholders only; no secrets are committed.
- CI runs lint, unit, property, integration and clean-migration checks.

**Maps to:** FR-B12; NFR reproducibility, security.

### US-1.2 — Import real AMFI NAVs idempotently
**As a** data engineer, **I want** to import a documented FundLens NAV extract, **so that** valuations use real market observations with provenance.

**Acceptance criteria**
- The adapter accepts the canonical CSV schema in `docs/FUNDLENS_NAV_CONTRACT.md`.
- Re-importing the same file is a no-op; a changed file is detected by SHA-256.
- Every NAV row records scheme code, name, plan, option, category, NAV date, NAV, source file checksum, source URL, retrieval time and import time.
- Non-positive, non-finite, malformed or out-of-scope rows are rejected and counted.
- A conflicting NAV for an existing `(scheme_code, nav_date)` is recorded, not silently overwritten.
- Import creates an immutable NAV snapshot with a content checksum and row count.
- No fabricated NAV is ever labelled as real.

**Maps to:** FR-B2, FR-B12; PRD 5.1, 5.3.

### US-1.3 — Verify the FundLens data contract
**As a** developer, **I want** a documented, read-only FundLens NAV contract, **so that** this project does not fork scheme-mapping logic or couple to undocumented internals.

**Acceptance criteria**
- The contract names the verified FundLens tables and columns: `core.dim_scheme`, `core.fact_nav`, `core.scheme_name_history`, `core.scheme_mapping`, `raw.source_file`.
- Scheme identity uses the stable AMFI scheme code, never name similarity.
- The read-only extraction query and canonical CSV schema are documented.
- File-level checksums and observed coverage are recorded.
- No FundLens file or database is modified.

**Maps to:** FR-B2; PRD 5.1, 9; DECISIONS D-003.

---

## Epic 2 — Ledger and bitemporal corrections

### US-2.1 — Generate synthetic accounts and transactions
**As a** performance analyst, **I want** a deterministic synthetic dataset with realistic transaction lifecycles, **so that** I can test accounting and replay without real client data.

**Acceptance criteria**
- Same seed and config produce identical logical records and canonical hashes.
- Generated data includes contributions, withdrawals, purchases, redemptions, SIP instalments, switches and corrections.
- Every generated transaction carries a simulated `recorded_at` in UTC.
- Counts, seed, date range, generator version and config hash are logged.
- Synthetic data is labelled in every output and in the dashboard.
- Rejected transactions do not change balances.

**Maps to:** FR-B1; PRD 5.2.

### US-2.2 — Keep an immutable transaction revision history
**As a** portfolio operations analyst, **I want** every accepted transaction version preserved, **so that** I can inspect what the system knew at any time.

**Acceptance criteria**
- A stable business transaction ID survives revisions.
- Revisions are append-only; UPDATE and DELETE of business revisions are rejected.
- Each revision stores effective date, recorded time, instruction fields, derived fields, correction group, prior revision and reason metadata.
- A rebuildable current-version projection exists and can be reconstructed from revisions.
- The projection is not claimed to be immutable.

**Maps to:** FR-B3; PRD 6.3, 9.

### US-2.3 — Replace a transaction with a backdated correction
**As a** portfolio operations analyst, **I want** to replace a prior transaction revision, **so that** a corrected instruction is reflected without losing the original.

**Acceptance criteria**
- The correction creates a new revision linked to the prior revision and a correction group.
- Only instruction fields may change; derived NAV, units and cash legs are recomputed atomically.
- The prior revision remains queryable at K1.
- The current projection and K2 views reflect the correction.
- The correction stores reason code, note, source reference, synthetic operator and recorded time.

**Maps to:** FR-B4; PRD 6.3.

### US-2.4 — Void a transaction
**As a** portfolio operations analyst, **I want** to void a prior transaction, **so that** an invalid transaction is removed from current accounting without deleting history.

**Acceptance criteria**
- A void creates a new revision with a void status and a correction group.
- All linked legs are voided together.
- The prior revision remains visible for K1 queries.
- Voids that would create negative units or cash downstream are rejected.

**Maps to:** FR-B4; PRD 6.3.

### US-2.5 — Reverse-and-replace a scheme
**As a** portfolio operations analyst, **I want** to reverse a transaction and replace it with a different scheme, **so that** a wrong-scheme purchase can be corrected with full lineage.

**Acceptance criteria**
- The correction group contains a reversing leg and a replacement leg.
- Units and cash are recomputed for both legs.
- The reason, operator, source and prior/new revision IDs are stored.
- Invalid downstream states cause the whole group to be rejected.

**Maps to:** FR-B4; PRD 6.3.

### US-2.6 — Reject invalid corrections
**As a** risk owner, **I want** invalid corrections rejected and logged, **so that** history cannot be silently corrupted.

**Acceptance criteria**
- A correction that would create negative units at any later effective date is rejected.
- A correction that would create negative cash beyond the configured rule is rejected.
- A correction that would break a linked-leg balance is rejected.
- The rejection is recorded with reason and evidence.
- Rejected corrections do not change balances or report outputs.

**Maps to:** FR-B4; PRD 6.3; tests in PRD 14.

---

## Epic 3 — Valuation and performance

### US-3.1 — Query positions as of a valid date and knowledge time
**As a** performance analyst, **I want** `positions(account_id, valid_date, known_as_of)`, **so that** I can see holdings using only what was known at K.

**Acceptance criteria**
- The query returns units and cash per scheme and account.
- It uses only revisions with `recorded_at <= known_as_of` and `effective_date <= valid_date`.
- A correction recorded after K1 does not alter the K1 result.
- The K2 result reflects the correction where effective.
- Results are deterministic and use Decimal/NUMERIC.

**Maps to:** FR-B5; PRD 6.

### US-3.2 — Value a portfolio with stale-NAV reporting
**As a** performance analyst, **I want** a valuation that uses the correct NAV and flags stale values, **so that** I know whether a value is based on a current or carried-forward observation.

**Acceptance criteria**
- `position_value = units × NAV`; `portfolio_value = sum(position_value) + cash`.
- The valuation date's NAV is used when present.
- If missing, the last NAV is carried forward up to 5 calendar days and flagged stale.
- Beyond 5 days, valuation fails explicitly; no silent forward-fill.
- Stale and missing NAV counts are reported separately.
- All arithmetic uses Decimal/NUMERIC.

**Maps to:** FR-B6; PRD 5.3.

### US-3.3 — Calculate TWR
**As a** performance analyst, **I want** a period TWR under a documented flow convention, **so that** I can compare portfolio performance without external-flow timing distortion.

**Acceptance criteria**
- Formula: `r_t = (V_t - V_(t-1) - CF_t) / (V_(t-1) + CF_t)`; `TWR = product(1 + r_t) - 1`.
- External contributions are positive; withdrawals negative; purchases, redemptions and switches are internal.
- Flows are treated at start of day; subperiods are bounded by external flows.
- A zero-flow period gives `V_end / V_start - 1`.
- A same-day flow case is tested.
- The result is labelled a period return, not annualised.
- Hand-computed and independent-reference tests pass.

**Maps to:** FR-B7; PRD 8, 14.

### US-3.4 — Calculate Modified Dietz
**As a** performance analyst, **I want** a period Modified Dietz return with explicit day-count and flow timing, **so that** I can use a standard approximation when daily valuations around every flow are unavailable.

**Acceptance criteria**
- Formula: `R = (V_end - V_start - sum(CF_i)) / (V_start + sum(w_i × CF_i))`.
- `T` is the inclusive calendar-day count; `w_i = (T - t_i) / T`; flows are at start of day.
- Zero-flow and same-day-flow cases are tested.
- The result is labelled a period return and is not compared with XIRR without stating the different basis.
- Hand-computed and independent-reference tests pass.

**Maps to:** FR-B7; PRD 8.

### US-3.5 — Calculate XIRR with explicit failure states
**As a** performance analyst, **I want** a money-weighted annualised return with convergence status, **so that** I never receive a silently chosen or invalid number.

**Acceptance criteria**
- Solves `sum(CF_i / (1 + r)^((d_i - d_0)/365)) = 0`.
- Contributions are negative; withdrawals and terminal value are positive.
- Returns a structured result: status, rate (if any), iterations, method and reason.
- Statuses include `SUCCESS`, `NO_ROOT`, `MULTIPLE_ROOTS`, `NON_CONVERGENCE`, `INVALID_CASH_FLOWS`.
- Newton-Raphson with bounded bisection fallback; no arbitrary root when multiple roots exist.
- Multiple-sign-change and no-root cases are tested.
- Independent reference tests pass.

**Maps to:** FR-B7; PRD 8.

### US-3.6 — Demonstrate TWR vs XIRR
**As a** performance analyst, **I want** both TWR and XIRR reported separately, **so that** I can explain manager performance versus investor experience.

**Acceptance criteria**
- The results output labels TWR as a period return and XIRR as an annualised money-weighted return.
- A deterministic SIP example shows a material difference and explains why.
- The dashboard does not combine the two measures into one “return”.
- The methodology document contains the example.

**Maps to:** FR-B7, FR-B11; PRD 8, 12.1 E9.

---

## Epic 4 — Snapshots, replay and restatement

### US-4.1 — Archive an immutable report snapshot
**As a** performance analyst, **I want** a report snapshot with full lineage, **so that** I can retrieve the exact report that was issued.

**Acceptance criteria**
- The snapshot stores account, period, `known_as_of`, simulated generation time, NAV snapshot ID/checksum, scheme-mapping version, calculation engine version, git commit SHA, schema/migration version, config hash, rounding policy, canonical payload and SHA-256.
- Retrieval returns the stored payload without recalculation.
- The payload is deterministic: sorted keys, decimal strings, ISO dates, no floats, explicit nulls.
- The snapshot is immutable.

**Maps to:** FR-B8; PRD 9, 10.

### US-4.2 — Replay a historical report from stored metadata
**As a** performance analyst, **I want** to recalculate an archived report from its stored inputs, **so that** replay is a genuine reconstruction, not merely retrieval.

**Acceptance criteria**
- Replay uses the stored period, `known_as_of`, NAV snapshot, engine/schema/config versions and rounding policy.
- The recalculated canonical payload is compared with the archived payload.
- The canonical hashes match for an unchanged engine and data snapshot.
- A mismatch fails the replay and records the difference.
- If the engine version differs, the result is `ENGINE_VERSION_MISMATCH`; the archived payload is still retrievable.

**Maps to:** FR-B8; PRD 10; D-OPEN-07.

### US-4.3 — Produce a restated report
**As a** team lead, **I want** a report using later knowledge, **so that** I can see the corrected position and performance.

**Acceptance criteria**
- The restated report uses the same account, period and current/later knowledge time.
- It reflects accepted corrections effective in the period.
- It is stored or reproducible with its own lineage.
- It is not confused with the archived K1 report.

**Maps to:** FR-B9; PRD 10.

### US-4.4 — Attribute every changed figure
**As a** team lead, **I want** each restatement delta linked to a changed transaction revision and reason, **so that** I can explain the movement.

**Acceptance criteria**
- The restatement register lists account, period, figure, original value, restated value, delta and basis points where applicable.
- Each delta is linked to one or more changed revisions, correction type, reason code and note.
- Cash, units, valuation, TWR, Modified Dietz and XIRR changes are covered.
- Unchanged figures are shown as unchanged or explicitly omitted with a rule.
- The K1 report remains unchanged.

**Maps to:** FR-B9; PRD 10; D-OPEN-07.

### US-4.5 — Prove the overwrite comparator's limitations
**As a** reviewer, **I want** a naive overwrite-in-place schema fed the same transactions, **so that** I can see exactly which historical reports it can and cannot reproduce.

**Acceptance criteria**
- The comparator has no archived report payload and no revision history; it stores current rows only.
- It is fed the same transaction stream and corrections.
- It attempts to reconstruct the original K1 report from its retained data.
- For corrected accounts, it fails or produces a different canonical payload; the failure is recorded.
- The result reports the count of reports still reproducible and exactly what is lost: prior instruction values, derived units/cash, revision lineage, reason and prior report payload.
- It is not allowed to retrieve a snapshot it previously saved.

**Maps to:** FR-B14; PRD 10; D-OPEN-07.

---

## Epic 5 — Data quality, invariants and tests

### US-5.1 — Run financial and temporal invariants
**As a** risk owner, **I want** invariants checked automatically, **so that** the pipeline fails on corrupt accounting or unreproducible reports.

**Acceptance criteria**
- Negative units are rejected.
- Cash-rule violations are rejected.
- Linked legs balance within the documented rounding residual.
- Positions tie to valuation.
- Replay mismatches beyond documented rounding fail.
- Invariant types, counts, passes and failures are recorded in `RESULTS.md`.
- The pipeline exits non-zero on a critical failure.

**Maps to:** FR-B10; PRD 14.

### US-5.2 — Test financial calculations against independent references
**As a** reviewer, **I want** hand-computed fixtures and independent reference implementations, **so that** production functions are not tested only against themselves.

**Acceptance criteria**
- `docs/METHODOLOGY.md` contains hand-computed fixtures before implementation.
- Reference functions do not call production functions.
- Max absolute error for TWR, Modified Dietz and XIRR is reported with case count.
- Tests cover contribution, withdrawal, purchase, redemption, SIP, switch, same-day flow, zero flow, partial withdrawal, terminal valuation, XIRR no-root, multiple-root and non-convergence.

**Maps to:** FR-B7; PRD 7, 14; E1.

### US-5.3 — Run property-based tests
**As a** reviewer, **I want** property tests, **so that** invariants hold across generated inputs.

**Acceptance criteria**
- Scaling all values and cash flows by a positive constant leaves returns unchanged.
- Internal transfers do not change portfolio value before market movement or rounding effects.
- No external flows means TWR equals the period portfolio return.
- A correction recorded after K1 cannot alter a K1 query.
- Same seed and inputs produce the same logical generated records.
- Rejected transactions do not change balances.

**Maps to:** FR-B1, FR-B4, FR-B7, FR-B10; PRD 7.

---

## Epic 6 — Sensitivity study

### US-6.1 — Pre-register the sensitivity study
**As a** reviewer, **I want** the study config committed before results, **so that** scenarios cannot be cherry-picked.

**Acceptance criteria**
- `config/sensitivity.yaml` defines path eligibility, seed, windows, SIP rule, scenarios, thresholds and statistics.
- The config is frozen and hashed before the study runs.
- No scenario is added, removed or changed after results are inspected.

**Maps to:** FR-B13; PRD 12.2.

### US-6.2 — Run every pre-registered scenario
**As a** performance analyst, **I want** all scenarios reported with sample size, **so that** I can see the true sensitivity distribution.

**Acceptance criteria**
- Backdating, mis-sizing and missed-correction scenarios are executed on real NAV paths.
- Each scenario reports n and the change in TWR, Modified Dietz and XIRR in basis points.
- Signed median, median absolute, p95 absolute and share exceeding configured thresholds are reported.
- Null, negative and inconclusive results are not hidden.
- The report states that correction magnitudes are controlled, not observed real-world error rates.

**Maps to:** FR-B13; E8.

### US-6.3 — Compare XIRR and TWR under SIP schedules
**As a** performance analyst, **I want** the XIRR–TWR gap across real market windows, **so that** I can explain the difference between money-weighted and time-weighted returns.

**Acceptance criteria**
- Deterministic monthly SIP schedules are run across pre-registered windows.
- The distribution of XIRR minus TWR is reported by window start.
- The relation to the window's drawdown is reported.
- The two measures remain separately labelled.

**Maps to:** FR-B13; E9.

---

## Epic 7 — Power BI reporting

### US-7.1 — Portfolio overview page
**As a** team lead, **I want** an overview of synthetic accounts and totals, **so that** I can see the portfolio at a glance.

**Acceptance criteria**
- Synthetic account count and totals are labelled.
- Value over time, TWR and XIRR are shown as separate measures.
- Allocation, cash and contribution/withdrawal history are shown.
- The footer states: “Synthetic portfolio data; real AMFI NAV inputs. Educational prototype, not investment advice or a regulatory system.”
- Filters behave correctly.

**Maps to:** FR-B11; PRD 11.

### US-7.2 — Account drilldown page
**As a** portfolio operations analyst, **I want** an account selector and date range, **so that** I can inspect holdings and the ledger.

**Acceptance criteria**
- Holdings show units, NAV, value and cash.
- The ledger shows effective date, recorded date, type and status.
- Performance series show flow markers.
- TWR and XIRR are not combined.

**Maps to:** FR-B11; PRD 11.

### US-7.3 — Restatements and audit page
**As a** team lead, **I want** original vs restated values and changed versions, **so that** I can audit corrections.

**Acceptance criteria**
- Original and restated values, K1/K2, affected accounts and periods are shown.
- Changed revisions, reasons and deltas are shown.
- Replay pass/fail and rejected corrections are shown.
- The page footer carries the synthetic-data disclosure.

**Maps to:** FR-B11; PRD 11.

### US-7.4 — Sensitivity page
**As a** performance analyst, **I want** the pre-registered sensitivity distributions, **so that** I can explain reporting fragility.

**Acceptance criteria**
- Scenario controls and the pre-registration note are displayed.
- TWR, Modified Dietz and XIRR distributions are shown with n.
- The page does not claim real-world error prevalence or user benefit.

**Maps to:** FR-B11, FR-B13; PRD 11.

### US-7.5 — At least ten ad-hoc SQL queries
**As a** reviewer, **I want** business-question SQL queries, **so that** I can inspect the ledger without the dashboard.

**Acceptance criteria**
- At least ten files in `sql/adhoc/`.
- Each file starts with the business question it answers.
- Each query runs against the project database.
- Results are reproducible and use the documented temporal semantics.

**Maps to:** FR-B11; PRD 15.

---

## Epic 8 — Reproducibility, documentation and release

### US-8.1 — Regenerate every headline number
**As a** reviewer, **I want** `make reproduce` to rebuild `RESULTS.md` from an empty database, **so that** no number is hand-typed.

**Acceptance criteria**
- The command builds/resets the project database safely, applies migrations, imports the NAV input, generates seeded data, runs calculations and evaluation, executes critical invariants and writes `RESULTS.md`.
- It records provenance, seed, dates, counts and runtime environment.
- It exits non-zero on a critical failure.
- Two clean runs produce identical logical results and canonical hashes.

**Maps to:** FR-B12; PRD 3, 12, 16; E7.

### US-8.2 — Publish the evaluation results
**As a** reviewer, **I want** E1–E9 with baselines, n, dates and limitations, **so that** I can judge the evidence.

**Acceptance criteria**
- `RESULTS.md` includes calculation correctness, replay counts, comparator capabilities/losses, restatement counts, invariant totals, as-of p50/p95 with hardware/row counts/plans, reproducibility hashes, sensitivity results and TWR-vs-XIRR differences.
- Every number states dataset size, baseline/reference, date range, seed where relevant, provenance and runtime environment.
- Null, negative and inconclusive results are not hidden.

**Maps to:** FR-B10, FR-B12, FR-B13, FR-B14; PRD 12.

### US-8.3 — Complete documentation and briefings
**As a** candidate, **I want** documentation that teaches the system, **so that** I can defend it in an interview.

**Acceptance criteria**
- README, BRD, user stories, data card, methodology, decisions, traceability, progress, M0 design review, briefings and screenshots exist and are substantive.
- Every milestone has a one-page briefing with three interview questions and defensible answers.
- README includes results, baselines, n, date ranges and limitations.
- Synthetic data is labelled everywhere.

**Maps to:** PRD 10, 15; definition of done.

### US-8.4 — Prepare Jira evidence without fabricating it
**As a** project owner, **I want** a real Jira backlog if access exists, or a local backlog with the limitation stated, **so that** project-management evidence is honest.

**Acceptance criteria**
- Eight epics match the PRD.
- Stories have acceptance criteria and one-week sprints.
- A ticket is Done only when criteria and evidence are verified.
- If Jira access is unavailable, no claim is made that tickets were created; the local backlog is provided.

**Maps to:** PRD 17; prompt section 11.

---

## Definition of Ready and Done

**Ready:** story has a clear user, business value, acceptance criteria, FR mapping and test approach.

**Done:** acceptance criteria pass; relevant tests exist and pass; evidence is recorded; documentation and briefings are updated; no secrets or fabricated numbers; the milestone gate is recorded in `docs/PROGRESS.md`.
