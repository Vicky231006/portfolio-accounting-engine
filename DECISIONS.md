# DECISIONS.md — Portfolio Accounting & Performance Engine

This file explains **why the project is designed this way**. It is intended to help the developer understand and defend the system, not merely document what the AI agent implemented.

Each entry records the problem, chosen approach, alternatives considered, reason and consequence. Update this file whenever an architectural or financial-methodology decision changes.

---

## D-001 — Make portfolio accounting the product; make bitemporality the mechanism

**Decision:** Name the product “Portfolio Accounting & Performance Engine”. Keep `bitemporal-ledger` as the repository name if that repo already exists, but do not market it as a generic temporal-database demo.

**Why this was considered:** A database feature alone does not tell a wealth-management interviewer what business workflow it supports. The user-facing problem is account positions, performance reporting, late corrections and report restatement.

**Alternatives:**
- Keep the name “Bitemporal Ledger” and lead with range types/GiST constraints.
- Build another mutual-fund analytics dashboard.
- Build an account-level accounting and reporting workflow with an audit/replay layer.

**Why this choice wins:** It creates a distinct second project after FundLens. FundLens analyses funds; this system accounts for synthetic portfolios and explains their reported performance. Bitemporality becomes the mechanism that prevents historical reports from silently changing.

**Consequence:** The dashboard, user stories and resume narrative must lead with account accounting, performance and restatement—not PostgreSQL range types.

## D-002 — Use synthetic accounts and transactions, but real AMFI NAV observations

**Decision:** Generate all investors, accounts, transactions and correction events from documented seeds. Use real AMFI NAV values for market pricing.

**Why:** There is no supplied real client/custodian dataset, and inventing one or implying real accounts would be misleading. Real NAV inputs still make valuations use genuine market observations.

**Alternatives:**
- Fabricate both transaction and market-price data.
- Attempt to obtain real client records (not appropriate for this portfolio project).
- Use synthetic accounts with real public NAV data.

**Why this choice wins:** It gives a useful test environment without pretending to have client data. It also reuses a genuine data asset built for FundLens.

**Consequences:** Label synthetic accounts/transactions in README, dashboard, results, data card and resume. Never claim real clients, accounts, AUM or operational prevalence. Record AMFI retrieval date, coverage and terms review.

## D-003 — Reuse FundLens NAV work through a stable data contract

**Decision:** Do not silently copy or independently reinterpret FundLens scheme mapping. Inspect FundLens first. Consume a versioned canonical NAV export if available; otherwise add the smallest documented export/adapter contract and record its exact schema and checksum.

**Why:** FundLens already solved historical NAV ingestion and scheme identity. Duplicating that logic can cause one project to map schemes differently from the other.

**Alternatives:**
- Rebuild AMFI ingestion from scratch.
- Make this project depend directly on undocumented FundLens database internals.
- Consume a stable, versioned NAV interface.

**Why this choice wins:** A stable contract preserves reuse without coupling this repository to a developer's local database or unversioned table layout.

**Consequence:** The AI agent must inspect the actual FundLens repo before selecting file paths or column names. It must not invent an export command or claim one already exists.

## D-004 — Model both effective date and knowledge time

**Decision:** Each accepted transaction version has a business-effective date and a system-recorded timestamp/period.

**Why:** A backdated correction can change what is now believed to have happened in the past. A report issued before the correction must nevertheless remain reproducible.

**Alternatives:**
- Store only the transaction's effective date.
- Store only `created_at`/`updated_at` audit fields.
- Store a bitemporal history with explicit as-of semantics.

**Why this choice wins:** Effective date answers “when did this apply?” Knowledge time answers “when did the system know it?” An ordinary `updated_at` column cannot reconstruct previous values after overwrite.

**Consequence:** The as-of query must take both an effective date and a knowledge timestamp. Tests must prove a later correction does not affect an earlier knowledge-time query.

## D-005 — Keep an immutable revision history and make current views rebuildable

**Decision:** Accepted business transaction revisions are preserved. Corrections create linked replacement/void revisions. Any current-state table or temporal projection is derived and rebuildable from the revision history.

**Why:** The most important property is that the original accepted information remains available. A mutable current projection is acceptable if it is not the only copy of business history.

**Alternatives:**
- Overwrite the original transaction row.
- Soft-delete without retaining a complete prior payload.
- Append immutable revisions and derive the current view.

**Why this choice wins:** It provides auditability and a clean reconstruction path. It also gives a useful interview demonstration: reconstruct the same report at two different knowledge times.

**Consequence:** If a physical `tstzrange` projection is used, close the prior projection interval in a controlled, deterministic way and retain the append-only source revision. Enforce non-overlap with a GiST exclusion constraint where applicable. Do not claim that every table is immutable if a derived projection is updated.

## D-006 — Use a small double-entry-inspired cash/units model, not a full general ledger

**Decision:** Track account cash and fund units with linked transaction legs and enforce conservation/reconciliation invariants. Do not build a full enterprise general ledger in v1.

**Why:** A portfolio purchase is not an external investor cash flow: it moves value from cash into fund units. If the model only stores fund units, it cannot consistently represent contributions, withdrawals, cash retained from IDCW, fees or switches.

**Alternatives:**
- Store only fund-unit lots and ignore cash.
- Build a complete chart-of-accounts/general-ledger platform.
- Track cash plus units with linked legs and explicit invariants.

**Why this choice wins:** It is sufficiently faithful to support portfolio valuation and performance while keeping the project finishable.

**Consequence:** Each purchase/redeemption/switch/SIP/distribution must have clear linked legs. Tests must prove linked legs balance and units/cash reconcile. Full accounting standards and tax treatment are out of scope.

## D-007 — Separate external flows from internal portfolio movements

**Decision:** Contributions and withdrawals are external portfolio flows. Purchases, redemptions and switches are internal movements. IDCW proceeds are portfolio income held as cash or reinvested, not a new investor contribution.

**Why:** TWR is intended to neutralise the effect of external client cash flows. Treating a fund purchase or switch as a new contribution would distort returns. Ignoring an IDCW payout can also make a NAV-only view understate total portfolio value.

**Alternatives:**
- Treat every cash movement as an external flow.
- Calculate performance from NAV only and ignore account cash.
- Define a transaction taxonomy that separates external and internal events.

**Why this choice wins:** It aligns the accounting representation with the performance question being answered.

**Consequence:** `docs/METHODOLOGY.md` must show signed-flow conventions and hand-calculated examples for contribution, withdrawal, purchase, switch, IDCW and fees. Do not ship calculations until these examples pass.

## D-008 — Use Decimal/NUMERIC for financial quantities

**Decision:** Use Python `Decimal` and PostgreSQL `NUMERIC` for money, NAV, units and return calculation inputs. Define rounding at explicit boundaries.

**Why:** Binary floating-point can represent many decimal amounts approximately. The resulting tiny differences can break ledger reconciliation and report replay.

**Alternatives:**
- Use Python `float`/PostgreSQL `DOUBLE PRECISION` everywhere.
- Use integer paise for every persisted amount.
- Use Decimal/NUMERIC with a documented precision and rounding policy.

**Why this choice wins:** It is easy to inspect and maps clearly to financial decimal arithmetic. Integer minor units may be used for cash where helpful, but it should not create an inconsistent second arithmetic model.

**Consequence:** No silent float conversions in financial paths. Unit tests must cover quantisation, rounding and equality/reconciliation.

## D-009 — Implement three complementary performance measures, not one generic “return”

**Decision:** Implement TWR, Modified Dietz and XIRR, with separate labels and documented assumptions.

**Why:** They answer different questions. TWR is designed to reduce the effect of external cash-flow timing; Modified Dietz approximates a sub-period return when daily valuations around every flow are unavailable; XIRR reflects the investor's dated cash flows and is money-weighted.

**Alternatives:**
- Show only CAGR or a simple beginning-to-ending percentage.
- Show only XIRR.
- Implement all three and explain when each is appropriate.

**Why this choice wins:** It demonstrates a meaningful financial-methodology distinction and prevents the dashboard from conflating portfolio-manager performance with client experience.

**Consequence:** The UI and exports must label TWR and XIRR separately. All calculations need independent tests. Say “GIPS-style conventions” only when justified; never claim GIPS compliance.

## D-010 — Keep XIRR numerically robust and failure-explicit

**Decision:** Use Newton-Raphson with a bounded bisection fallback, plus explicit no-root/non-convergence handling.

**Why:** Newton-Raphson can fail when derivatives are small, initial guesses are poor or cash-flow patterns are irregular. A solver that silently returns a number is less useful than one that reports it cannot establish a valid root.

**Alternatives:**
- Implement Newton-Raphson only.
- Use a library without understanding or validating its conventions.
- Use a primary Newton method plus a bounded fallback and independent reference tests.

**Consequence:** Return a structured result with convergence status, iteration count and reason when unresolved. Test multiple sign changes and no-root cases.

## D-011 — Store report snapshots with input and calculation lineage

**Decision:** A report snapshot records account, period, `known_as_of`, generation timestamp, NAV snapshot/version, calculation version and canonical output hash/contents.

**Why:** “Reproduce the report” is not achievable if the system only stores a PDF or final percentage but not the data and calculation context used to produce it.

**Alternatives:**
- Regenerate old statements using today's latest data.
- Save only exported PDFs.
- Save structured report output plus the data/calculation version metadata needed for deterministic replay.

**Why this choice wins:** It separates exact historical reproduction from a current restated view.

**Consequence:** Canonical structured report payloads are the comparison target. PDF rendering is optional and not the source of truth for the replay test.

## D-012 — Make restatement attribution a core product feature

**Decision:** Restatement output identifies affected account, period, changed input transaction version, correction reason, original value, new value and delta.

**Why:** A changed report total without an explanation is not useful to an operations or performance analyst.

**Alternatives:**
- Show only a “report changed” badge.
- Show old/new totals but no source attribution.
- Trace the output delta back to the corrected transactions.

**Consequence:** The system must retain input lineage and demonstrate a worked correction end to end.

## D-013 — Use synthetic accounts, but make the test cases operationally plausible

**Decision:** Generator parameters are documented and configurable. Use realistic transaction lifecycles and intentionally varied correction delays, but do not claim the resulting distribution represents real clients or a real firm's error rate.

**Why:** Synthetic data makes the repository reproducible and safe to publish. The generator's assumptions remain a limitation.

**Consequence:** Report seed, transaction count, account count, correction rate and date coverage. Any restatement-impact percentage is explicitly “under the configured generator”.

## D-014 — Keep the product batch-oriented and local-first

**Decision:** Use Python CLI, PostgreSQL, SQL marts, Power BI and GitHub Actions. No Kafka/microservices/LLM in v1.

**Why:** The core workflow is a repeatable portfolio valuation/reporting batch, not a sub-second trading system. Distributed infrastructure does not improve the main business demonstration.

**Alternatives:**
- Add message brokers and microservices.
- Build a complex web application before the calculations work.
- Implement a reproducible batch system with a dashboard.

**Consequence:** Spend effort on accounting correctness, temporal queries, calculation methodology, replay, tests and clear reporting.

## D-015 — Reuse Power BI for consistency with FundLens

**Decision:** Use Power BI for the new dashboard.

**Why:** The user already has a Power BI workflow and FundLens dashboard. One BI tool across the portfolio reduces setup overhead and lets interviewers compare the projects.

**Consequence:** Store PBIP/report definitions and screenshots where feasible; keep local data-bearing binaries and sensitive exports out of Git unless deliberately sanitised.

## D-016 — No regulatory-compliance claim

**Decision:** Use regulatory sources only to establish that portfolio reporting, recordkeeping and report reconstruction are genuine industry concerns. Do not state that this student prototype satisfies SEBI requirements or is used by any named firm.

**Why:** A rule's existence does not mean the project implements every control, operational process, certification or legal obligation.

**Evidence boundary:** SEBI's Portfolio Managers Master Circular and Regulations concern the regulated portfolio-management context. The SEC's Rule 17a-4 audit-trail alternative is a US broker-dealer recordkeeping example. Neither dictates this exact bitemporal schema.

**Consequence:** README and dashboard must say “educational prototype”; avoid “compliant”, “production-grade”, “client-ready” and claims about Morgan Stanley's internal systems.

---

## Questions the developer must be able to answer

1. Why are valid time and knowledge time different?
2. Why does `updated_at` alone not reconstruct an old transaction value?
3. Why must a purchase not be counted as a new external client contribution?
4. What is the difference between TWR and XIRR?
5. Why keep account cash as well as fund units?
6. What is stored in a report snapshot that makes replay possible?
7. How does a corrected transaction change the current view without changing the original historical view?
8. What is the limitation of using synthetic accounts and real AMFI NAV data?
9. Why is a bitemporal model not the same as regulatory compliance?

If the developer cannot answer one of these, add a worked example to `docs/METHODOLOGY.md` or this file before calling the feature complete.

---

# Decision log — PRD v2.0 additions and M0 proposals

> **Format note:** D-001 to D-016 were created during project setup and retain their original narrative format. From D-017 onward, each entry records the date, status, problem, chosen approach, reason, alternatives, why alternatives were rejected, consequences/limitations and PRD references.
>
> **Approval note:** “Approved in PRD v2.0” means the decision is explicitly stated in the authoritative PRD. It is not a claim that Vicky approved it separately. “Proposed” means it is awaiting Vicky's M0 approval and must not be implemented as final until approved.

## D-017 — Remove IDCW payouts and reinvestment from v1

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** The AMFI NAV files used by FundLens do not supply declared IDCW amounts. Modelling payouts would require invented amounts or a different data source.
- **Chosen approach:** Support Growth plans only. Do not model IDCW payouts, reinvestment or IDCW NAVs.
- **Reason:** Avoids fabricated financial events and keeps the data contract honest.
- **Alternatives:** (a) Infer IDCW amounts; (b) obtain a separate IDCW data source; (c) exclude IDCW.
- **Why alternatives were rejected:** (a) would fabricate financial information; (b) is outside the approved data source; (c) is the only defensible v1 option.
- **Consequences / limitations:** The product cannot answer IDCW-related questions; this is documented in the data card and out-of-scope list.
- **PRD references:** 4.2, 5.1, 21 (D-017).

## D-018 — Defer fees and charges to a stretch

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** Fees add a new cash-flow and performance surface (expense ratios, transaction charges, exit loads) that is not required to demonstrate the core accounting and replay problem.
- **Chosen approach:** Exclude fees from v1. Keep the model extensible for a later stretch.
- **Reason:** Reduces the methodology surface that must be defended and keeps the focus on portfolio accounting, corrections and replay.
- **Alternatives:** Model all fees now; model a simplified fee; defer.
- **Why alternatives were rejected:** Full fee modelling expands scope; a simplified fee would be an unapproved assumption; deferral is the PRD's choice.
- **Consequences / limitations:** Returns are gross of fees; the dashboard and results must say so.
- **PRD references:** 4.2, 21 (D-018).

## D-019 — Instruct purchases by amount, redemptions by units, and define the allotment rule

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** PRD v1.0 left unit derivation and NAV-date selection undefined.
- **Chosen approach:** Purchases and SIP purchases are instructed by amount: `units = quantize(amount / NAV(allotment_date))`. Redemptions are instructed by units: `proceeds = quantize(units × NAV(allotment_date))`. Allotment date is the effective date if a NAV exists, otherwise the next NAV date within 5 calendar days; otherwise the transaction is not created/rejected.
- **Reason:** Matches how mutual-fund purchases and redemptions are commonly instructed and makes NAV-date selection explicit.
- **Alternatives:** Instruct purchases by units; use the latest NAV regardless of date; use a fixed monthly NAV.
- **Why alternatives were rejected:** Unit-instructed purchases do not match the business convention; stale/arbitrary NAV selection would make valuations and replay ambiguous.
- **Consequences / limitations:** Units and cash can have small rounding residuals; these must be recorded. The 5-day limit is configurable and documented.
- **PRD references:** 5.3, 21 (D-019).

## D-020 — Corrections edit instruction fields only; derived fields are recomputed atomically

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** Allowing direct edits to derived units, proceeds or cash legs can break linked-leg balance and silently corrupt downstream positions.
- **Chosen approach:** A correction edits only instruction fields (effective date, amount or units, scheme via reverse-and-replace). Derived NAV, units, proceeds and cash legs are recomputed in the same atomic correction group. Invalid downstream states are rejected.
- **Reason:** Preserves linked-leg balance and makes the correction auditable.
- **Alternatives:** Edit derived fields directly; delete and reinsert the transaction; allow partial leg edits.
- **Why alternatives were rejected:** Direct edits break conservation; delete/reinsert destroys lineage; partial edits can leave unbalanced legs.
- **Consequences / limitations:** Corrections may be rejected even when the individual instruction is valid, because downstream positions would become invalid. Rejections are part of the audit output.
- **PRD references:** 6.3, 21 (D-020).

## D-021 — The generator owns a simulated clock for knowledge time

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** If knowledge time is wall-clock “now”, K1 and K2 collapse and report replay is meaningless.
- **Chosen approach:** Every generated transaction and correction carries a simulated `recorded_at` in UTC. Report snapshots use simulated generation timestamps. Wall-clock time is used only for pipeline audit metadata.
- **Reason:** Makes knowledge time a controlled, reproducible input.
- **Alternatives:** Use database `now()`; use file modification times; use a fixed constant.
- **Why alternatives were rejected:** `now()` is not reproducible; file times are not transaction knowledge; a fixed constant cannot represent a sequence of corrections.
- **Consequences / limitations:** The generator must be deterministic and must log its clock rules and seed. The simulated clock is not a claim about real system latency.
- **PRD references:** 5.2, 21 (D-021).

## D-022 — Add a pre-registered sensitivity study on real NAV paths; report replay as counts

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0
- **Problem:** A replay demo alone does not show how much reported returns can move under controlled transaction errors, and a “win percentage” against an overwrite comparator would overstate the result.
- **Chosen approach:** Run a pre-registered sensitivity study on real NAV paths from `config/sensitivity.yaml`; report replay as counts of archived snapshots reproduced exactly, not as an improvement percentage.
- **Reason:** Gives a real-data finding without claiming user impact; keeps replay evidence honest.
- **Alternatives:** No sensitivity study; a synthetic-only study; a replay “win rate”.
- **Why alternatives were rejected:** Synthetic-only would not use the real NAV asset; a win rate would invite misleading comparisons.
- **Consequences / limitations:** The study measures sensitivity, not real-world error prevalence or user benefit. All scenarios must be reported with n.
- **PRD references:** 12.1 E2/E8/E9, 12.2, 21 (D-022).

## D-023 — Consume FundLens through a read-only canonical NAV contract

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** Reimplementing AMFI ingestion or scheme mapping risks divergent scheme identity and duplicates FundLens work; coupling directly to an undocumented local database is brittle.
- **Chosen approach (Vicky's Option A):** Use the already verified raw-file fallback now. Do not query the FundLens PostgreSQL database and do not access its running database volumes. Consume the canonical CSV contract using FundLens's parser as a read-only reference. Record contract version, CSV SHA-256, manifest, source-file SHA-256, date range and FundLens schema version. Reconcile the 86 raw files against the 85 registered file ranges with filenames, checksums, date ranges and row-level differences, and verify that the only differences are the three out-of-scope IDCW observations.
- **Reason:** Reuses FundLens identity and provenance without modifying it, while avoiding any database access that Vicky has not authorised. The raw files are the authoritative source and preserve their own SHA-256 provenance.
- **Alternatives:** Rebuild AMFI ingestion; query FundLens tables directly at runtime; copy FundLens tables into this project.
- **Why alternatives were rejected:** Rebuilding forks mapping logic; direct runtime coupling is brittle and was not authorised; copying creates a second source of truth. `core.fact_nav` was not queried.
- **Consequences / limitations:** The live `core.fact_nav` query remains unexecuted by explicit choice. Parity between the raw-file import and FundLens's audited row counts must be established from the raw files and documented as a limitation, not claimed as a database verification. Do not silently omit or alter source records. No AMFI data is redistributed.
- **PRD references:** 5.1, 9; prompt 2.2–2.3.

## D-024 — Date semantics: instruction, effective and allotment dates

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** The PRD distinguishes three dates but does not fully define when cash and units move if the effective date is not a NAV date.
- **Chosen approach:** Instruction date is audit-only. Simple purchases and redemptions post on the allotment date (both cash and units together). SIP contribution posts on the contribution date and its purchase on the allotment date, with interim cash visible. Switch legs post on their respective source/target NAV dates within one atomic group.
- **Reason:** Keeps simple trades value-conserving, respects the PRD's explicit SIP split and avoids inventing a receivable/clearing account.
- **Alternatives:** Post cash on the instruction date and units later; treat all three dates as identical.
- **Why alternatives were rejected:** The first adds an unapproved receivable model; the second hides real date differences and contradicts the PRD.
- **Consequences / limitations:** A simple trade instructed on a non-NAV day posts on the next NAV date. SIP and switch groups can span dates.
- **PRD references:** 5.3, 6.1, 6.2; prompt D-OPEN-01.

## D-025 — SWITCH is one atomic internal group

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** A switch is a linked redemption and purchase. If modelled as two independent external transactions, it distorts TWR/XIRR and can leave one leg posted without the other.
- **Chosen approach:** One atomic group: source redemption on the source NAV date, target purchase on the next target NAV date, with a maximum five-calendar-day interval between the legs, residual cash credited, both legs succeed or fail together. If the target leg cannot be priced within the interval, the entire group is rejected and neither leg posts. Never an external flow.
- **Reason:** Preserves economic substance and auditability.
- **Alternatives:** Common single date; withdrawal + contribution; independent legs.
- **Why alternatives were rejected:** A common date may reject valid switches; withdrawal + contribution creates a false external flow; independent legs can leave an unbalanced state.
- **Consequences / limitations:** Interim cash may exist between the legs; it is valued and reported. Target units use ROUND_DOWN (see D-026).
- **PRD references:** 6.2, 6.3; prompt D-OPEN-02.

## D-026 — Rounding and residual cash policy

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** The PRD sets precision but not the rounding mode or the exact reconciliation of amount-instructed purchases and switch residuals.
- **Chosen approach:** Units 3 dp, amounts 2 dp, NAV as published. General mode `ROUND_HALF_UP`; amount-instructed purchase units use `ROUND_DOWN` so the cash debit never exceeds the instruction. Residual cash is retained, reported and accounted for exactly once; it is never discarded, double-counted or converted into an unexplained fee. Redemption proceeds use `ROUND_HALF_UP`. Switch target units use `ROUND_DOWN`, so residual cash is non-negative.
- **Reason:** Avoids over-debiting, negative residual cash and hidden rounding losses while keeping a single documented convention.
- **Alternatives:** Half-up everywhere; debit the instructed amount and book an expense; use 6 dp units.
- **Why alternatives were rejected:** Half-up can over-debit or create a negative switch residual; an expense entry is out of scope; extra precision does not solve the reconciliation principle.
- **Consequences / limitations:** Purchases may receive slightly fewer units than a half-up calculation, with the residual retained as cash. Residuals are reported by account and type.
- **PRD references:** 5.3, 7, 8; prompt D-OPEN-03.

## D-027 — Opening funding and same-day ordering

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** The PRD does not state whether accounts start funded, whether overdrafts are allowed, or how same-effective-date transactions are ordered for cash/unit sufficiency.
- **Chosen approach (Vicky's refinement):** Accounts start with zero cash and zero units. Funding is an explicit `CONTRIBUTION`. No overdraft. Reject negative cash and negative units. Every transaction group carries an explicit deterministic `posting_sequence` for its effective date. Process same-effective-date groups in ascending `posting_sequence`; ties are broken deterministically by immutable group ID. Do not hardcode a universal transaction-type priority. A group that would create negative cash or units is rejected atomically, recorded with a reason, and does not post; later groups in the sequence are still evaluated against the actual posted balances.
- **Reason:** Creates a traceable funding event and a deterministic, testable sufficiency rule without pretending that one type order is universally correct. The producer must state the intended intraday order.
- **Alternatives:** Allow opening balances; allow an overdraft; process strictly in recorded order; hardcode a universal type priority.
- **Why alternatives were rejected:** Opening balances need an unexplained source; an overdraft contradicts the PRD's negative-cash rule; recorded order is not a financial ordering rule; a universal type priority cannot represent every legitimate same-day dependency.
- **Consequences / limitations:** A withdrawal cannot rely on a later same-day contribution unless its `posting_sequence` places it after that contribution. The generator and ledger must assign and preserve `posting_sequence`; changes to it are auditable corrections. The ordering is a documented, testable business rule.
- **PRD references:** 6.1, 6.2; prompt D-OPEN-04.

## D-028 — Performance conventions

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09 (refined)
- **Problem:** The PRD gives formulas but leaves flow timing, day count, boundaries, stale-NAV treatment and annualisation to be documented.
- **Chosen approach:** External flows at start of day; contributions positive/withdrawals negative for TWR and Modified Dietz; purchases/redemptions/switches internal; SIP contribution counted once; TWR and Modified Dietz are period returns; XIRR is annualised; calendar-day weighting with inclusive `T`; report boundaries inclusive under the adopted full-calendar-day convention; stale NAV carried forward up to 5 calendar days and flagged; no silent fill beyond.
- **Refinement (Vicky, 2026-11-09):** Period start is `start_date 00:00:00`; period end is midnight immediately after `end_date`; opening valuation precedes events on the start date; closing valuation includes events through the end date; flow timestamps, `T` and `t_i` follow this convention. Fixtures F5, F7 and F19 were recalculated under this convention.
- **Reason:** Internally consistent, matches the PRD formula and makes TWR/Modified Dietz/XIRR differences explicit.
- **Alternatives:** End-of-day flows; business-day weighting; annualise TWR in the core output; use a different stale limit.
- **Why alternatives were rejected:** The PRD's TWR formula is start-of-day; business-day weighting would need an unapproved calendar; annualising TWR invites false comparison with XIRR; a different stale limit is arbitrary.
- **Consequences / limitations:** TWR needs valuations at flow dates; Modified Dietz can differ materially from TWR; stale NAVs are visible. The precise formulas, boundaries, sign conventions, annualisation and fixtures are documented in `docs/METHODOLOGY.md` sections 4–7.
- **PRD references:** 8, 10, 12.1 E9; prompt D-OPEN-05.

## D-029 — XIRR root search and failure statuses

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** Newton-Raphson can fail or find only one of several roots; silently returning a number is indefensible.
- **Chosen approach (Vicky's refinement):** Scan the domain `r ∈ (-0.999999, 1000)` on `ln(1+r)`, detect roots, refine with bisection, use Newton from a bracket midpoint with bisection fallback, and return `SUCCESS`, `NO_ROOT_IN_DOMAIN`, `NO_ROOT_PROVEN`, `MULTIPLE_ROOTS`, `NON_CONVERGENCE` or `INVALID_CASH_FLOWS` with iterations, method, residual and, where applicable, the nearest root outside the domain. `NO_ROOT_IN_DOMAIN` means the configured scan found no root; it does not prove that no mathematical root exists. `NO_ROOT_PROVEN` is used only when a documented analytic argument establishes that no root exists in the domain. Never choose an arbitrary root.
- **Reason:** Explicit, testable and honest about the difference between a search failure and a mathematical proof.
- **Alternatives:** Newton only; return the first root; use a library without validating conventions; use a single `NO_ROOT` status for both cases.
- **Why alternatives were rejected:** They can silently pick a root, hide failure, or overstate a numerical scan as a proof.
- **Consequences / limitations:** Sign-change scanning can miss an even-multiplicity tangential root; the limitation is documented. A multiple-root result has no single XIRR value. `NO_ROOT_IN_DOMAIN` must be reported with the search domain and grid resolution, not presented as proof.
- **PRD references:** 8, 14; prompt D-OPEN-06.

## D-030 — Snapshot reproducibility, replay and comparator

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** “Reproduce the report” is impossible if only a PDF or final number is stored; a comparator that retrieves a saved snapshot would not test the cost of overwriting.
- **Chosen approach (Vicky's refinement):** Store all necessary market-data, mapping, calculation, schema and environment provenance: account, period, `known_as_of`, simulated generation time, NAV snapshot ID and checksum, scheme-mapping version, engine version, git commit/dirty flag, schema-migration hash, configuration hash, rounding policy, canonical payload and SHA-256. Distinguish archived retrieval, replay and restatement. The overwrite comparator stores current rows only and must genuinely attempt historical recalculation from retained current-row data; archived report retrieval does not qualify as replay, and the comparator may not retrieve an archived payload.
- **Reason:** Makes replay a genuine reconstruction and makes the comparator's losses demonstrable.
- **Alternatives:** Store only the final number; store only a PDF; store a full database dump per report.
- **Why alternatives were rejected:** The first two cannot reconstruct or attribute; a full dump per report is unnecessary and heavy.
- **Consequences / limitations:** Exact replay is guaranteed only for the same engine version and immutable NAV snapshot. A later code change yields `ENGINE_VERSION_MISMATCH`; archived retrieval still works.
- **PRD references:** 9, 10; prompt D-OPEN-07.

## D-031 — Sensitivity statistics

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** Reporting only a signed median lets positive and negative errors cancel and hide the magnitude of reporting sensitivity.
- **Chosen approach:** Per scenario and measure, report n, median signed change in bp, median absolute change, p95 absolute change, share exceeding configured thresholds and failed/insufficient counts. Pre-register the config before running.
- **Reason:** Shows direction and magnitude without cancellation.
- **Alternatives:** Signed median only; absolute only; mean only.
- **Why alternatives were rejected:** Signed only hides magnitude; absolute only hides direction; the mean is sensitive to outliers and cancels signs.
- **Consequences / limitations:** The study still measures controlled sensitivity, not real-world error prevalence or user benefit.
- **PRD references:** 12.2; prompt D-OPEN-08.

## D-032 — Jira fallback: local backlog until access is established

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** The PRD requires Jira evidence, but no Jira project, credentials or permission was available.
- **Chosen approach (Vicky's direction):** Prepare the eight-epic backlog and stories locally in `docs/USER_STORIES.md`. Do not create a Jira project and do not claim any Jira ticket exists. Do not use FundLens's Jira project. Maintain the local backlog and documentation as the project-management evidence.
- **Reason:** Keeps project-management evidence honest and follows Vicky's instruction not to create or claim a Jira project.
- **Alternatives:** Invent a sprint history; use FundLens's Jira project; omit project management.
- **Why alternatives were rejected:** Inventing history is dishonest; using FundLens's project would violate the separation requirement; omitting it misses a deliverable.
- **Consequences / limitations:** Jira evidence is intentionally absent. The local backlog is the authoritative project-management record for this engagement.
- **PRD references:** 17; prompt section 11.

## D-033 — M1 Foundations approval and preserved qualifications

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M1's local execution phase passed, but the PRD requires formal sign-off before M2, with honest qualifications.
- **Chosen approach:** Record M1 as **Approved**. Preserve explicitly: local validation passed (11 tests); GitHub Actions workflow configured but remote execution not performed; migration checksum-tamper failure path implemented but not exercised; no Git remote, push or publication. Record the tamper test as a follow-up release verification item. Verify the earliest imported NAV (`2006-04-02`) against its raw source file and document the evidence (`docs/NAV_EARLIEST_EVIDENCE.md`); do not treat the weekday as evidence of invalidity.
- **Reason:** Keeps the milestone gate honest: a configured workflow is not a green CI run, and an implemented failure path is not an exercised one.
- **Alternatives:** Mark M1 complete without qualifications; claim CI green from the workflow file; postpone the NAV-date check.
- **Why alternatives were rejected:** They overstate evidence and would hide the exact gaps a reviewer must see.
- **Consequences / limitations:** CI remains unexecuted; determinism and import evidence are local only. The tamper test must be exercised by the M7/M10 release gate.
- **PRD references:** 0 (rule 1), 16 (M1 gate).

## D-034 — M2 generator: pure logical records, no ledger tables

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0 (FR-B1); M2 design choice by Vicky's M2 scope
- **Problem:** The M2 scope needs deterministic investor/account master data and transaction records without implementing the transaction ledger or bitemporal correction engine.
- **Chosen approach:** The generator is a **pure function** `config × seed × NAV index → dataset`. It emits canonical logical records (`investors`, `accounts`, `transactions`, `correction_intents`, `manifest`) as JSON; it writes no ledger tables. Database master persistence (`investor`/`account` tables) is deferred to M3, when the ledger needs foreign keys. The transaction records are **instruction-level intents** (instruction/effective dates, amount/units instructed, `posting_sequence`, simulated `recorded_at`) — not derived legs. No new transaction type is introduced; only the six approved types are emitted.
- **Reason:** Keeps M2's exit gate (identical hashes) testable without inventing a ledger schema, and prevents M2 feasibility estimates from being mistaken for ledger-derived facts.
- **Alternatives:** Create `investor`/`account`/ledger DB tables in M2 and persist generated rows; emit derived cash/unit legs in M2.
- **Why alternatives were rejected:** Persisting rows would force a M3 schema decision early and would duplicate the ledger's responsibility for derived fields.
- **Consequences / limitations:** M3 must define physical tables and prove that generated instructions map onto them. Feasibility estimates inside the generator are labelled `generator_estimated_*` and are not persisted as financial facts beyond the record's instruction fields.
- **PRD references:** 5.2, 6.2, FR-B1.

## D-035 — Determinism: integer-only RNG, canonical JSON and SHA-256

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0 (FR-B1, E7); M2 design choice
- **Problem:** Two clean runs must produce byte-identical logical output. Float randomness, dict/set iteration order and wall-clock timestamps all break that.
- **Chosen approach:** One `random.Random(seed)` instance, integer-only sampling (paise, percents, day counts; no binary float in amounts), sorted iteration everywhere, and no wall-clock `now()` in any record. Canonical serialisation is `json.dumps(..., sort_keys=True, separators=(",", ":"))` with decimals rendered as fixed strings; per-record and overall hashes are SHA-256 over those canonical bytes and the ordered record sequence. The manifest records `seed`, `config_hash`, `generator_version`, `nav_snapshot_id`, counts and all record hashes.
- **Reason:** Makes the reproducibility claim mechanically checkable in tests and across clean container runs.
- **Alternatives:** Float sampling; hashing Python objects/`repr`; pretty-printed JSON as the hash input.
- **Why alternatives were rejected:** Floats and `repr` are platform- and version-sensitive; pretty-printing adds whitespace noise to the hash.
- **Consequences / limitations:** Changing the canonical serialisation or the record field set changes the hashes by design. Any field addition is a breaking change to recorded hashes and must be versioned with `generator_version`.
- **PRD references:** 5.2, FR-B1, 12.1 E7.

## D-036 — Generated transactions are restricted to NAV-available dates

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0 (5.3, D-019, D-024); M2 design choice
- **Problem:** The allotment rule says "the generator does not create the transaction" when no NAV exists within 5 days. Generating arbitrary calendar dates and deferring the check to M3 would produce transactions M3 must reject.
- **Chosen approach:** For `PURCHASE`, `REDEMPTION`, `SIP_INSTALMENT` and `SWITCH`, the generator picks an `effective_date` that **is** a NAV date for the scheme(s) involved, so `allotment_date = effective_date` (and for a switch, the source and target share the date). `CONTRIBUTION`/`WITHDRAWAL` are cash-only and may use any date. The split-date cases in `docs/METHODOLOGY.md` §2.2–§2.3 (SIP contribution on the 5th, purchase on the next NAV date; switch legs on successive NAV dates) remain valid M3 ledger cases but are not exercised by the M2 synthetic dataset.
- **Reason:** One date, one NAV, no interim-cash ambiguity in the feasibility simulation, while staying inside the approved semantics as the `effective_date = allotment_date` special case.
- **Alternatives:** Generate arbitrary effective dates and store a separate `allotment_date`; generate all dates as business days without a NAV index.
- **Why alternatives were rejected:** They require the M3 ledger's deferral logic to make the dataset feasible, and without a NAV index the generator cannot honour "does not create the transaction".
- **Consequences / limitations:** The synthetic dataset does not exercise weekend/holiday effective dates. That limitation is stated in the M2 briefing; the ledger fixtures in `docs/METHODOLOGY.md` cover those cases.
- **PRD references:** 5.3, 6.1, 6.2; D-019, D-024.

## D-037 — Feasibility is enforced by construction, inside the generator only

- **Date:** 2026-11-09
- **Status:** M2 design choice (D-027, D-020)
- **Problem:** A synthetic dataset that books a withdrawal larger than cash, or a redemption larger than units, would be rejected by the M3 ledger and would not be a useful test dataset. But M2 must not become a ledger.
- **Chosen approach:** The generator walks each account in `posting_sequence` order with a **feasibility-only** simulation (cash and an estimated-holdings map derived from real NAV prices). Redemptions and switches are sized as a sampled fraction (10–80%) of current estimated holdings; purchases and withdrawals are capped by available cash; infeasible samples fall back deterministically to `CONTRIBUTION`/`PURCHASE` with a counter in the manifest. The simulation's units are labelled `generator_estimated_units` / `generator_estimated_proceeds` in the record; they are not ledger-derived facts and are recomputed by M3.
- **Reason:** Produces a dataset that is feasible under the approved rules without pretending to be a ledger, and makes the fallback rate visible instead of silent.
- **Alternatives:** Emit unconstrained samples and let M3 reject them; run a full ledger in the generator.
- **Why alternatives were rejected:** The first floods M3 with invalid data; the second duplicates M3/M4 work and blurs milestone boundaries.
- **Consequences / limitations:** Fallback conversions are a generator modelling choice, documented as such; they are not a claim about investor behaviour. The fallback count is always reported.
- **PRD references:** 5.2, 6.2, 6.3; D-020, D-027.

## D-038 — Simulated UTC knowledge clock

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0 (D-021); M2 design choice
- **Problem:** Without a simulated clock, K1 and K2 collapse to wall-clock "now" and bitemporal replay (M3+) is meaningless.
- **Chosen approach:** Every transaction records `recorded_at` as `effective_date` at **18:00 UTC plus a deterministic minute offset** (0–119 minutes from the global transaction index). Every correction intent records `recorded_at` as `effective_date + delay_days` (1–30, configurable) at **11:00 UTC plus a deterministic minute offset** (0–239 minutes). No record uses wall-clock time. The manifest states these rules.
- **Reason:** Monotonic, reproducible, and guarantees `correction.recorded_at > transaction.recorded_at` by construction.
- **Alternatives:** Use `datetime.now()`; use a single fixed timestamp for all records; use random minutes from the RNG stream.
- **Why alternatives were rejected:** `now()` is not reproducible; a fixed timestamp cannot order a sequence; RNG minutes couple the clock to amount sampling and complicate reordering.
- **Consequences / limitations:** The clock is a scenario, not a claim about real system latency. Wall-clock time remains available only for pipeline audit metadata outside logical records.
- **PRD references:** 5.2; D-021.

## D-039 — Correction frequency generates *intents*, not applied revisions

- **Date:** 2026-11-09
- **Status:** Approved in PRD v2.0 (5.2, 6.3; FR-B4 defers the engine to M3); M2 design choice
- **Problem:** The M2 scope requires a configurable "correction frequency", but the bitemporal correction engine is M3. Generating already-applied revisions would implement M3 early.
- **Chosen approach:** For a configurable fraction of eligible transactions, the generator emits `correction_intent` logical records: `correction_type` (`REPLACE`/`VOID`/`REVERSE_AND_REPLACE`), proposed instruction-field change (amount, units, or scheme), `reason_code` and a synthetic note, backdated `recorded_at`, and a synthetic operator ID. Intents are **not applied** in M2: no revision is created, no balance is recomputed, no validity check is run. M3 will consume these intents as its input test data.
- **Reason:** Preserves the milestone boundary while giving M3 a deterministic, seeded correction workload.
- **Alternatives:** Emit applied bitemporal revisions in M2; omit corrections entirely until M3.
- **Why alternatives were rejected:** The first implements M3; the second leaves correction frequency unconfigurable and M3 without seeded input.
- **Consequences / limitations:** An intent may turn out to be invalid when M3 applies the validity rule (for example a `VOID` of a funding contribution). That is expected and M3 must record the rejection; it is not a generator defect.
- **PRD references:** 5.2, 6.3; FR-B1 vs FR-B4.

## D-040 — M2 Generator approval

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M2 needed formal closure before the ledger engine could start.
- **Chosen approach:** Record M2 as **Approved**. The exit criterion is met with evidence: identical seed/config produced byte-identical files and matching `dataset_hash` (`94839c5cb0119c6501f592da2f7fef56ca3f6cbb04e5e49ba4adfaf3308b6cda`); 22 tests passed. Qualifications stand as documented (12 ACTIVE / 0 CLOSED accounts; SIP-dominated counts; split-date cases covered by methodology fixtures; generator-only estimates).
- **Consequences / limitations:** M2 outputs are the frozen input to M3. The M2 generator output contract is not modified to simplify M3 (D-034).
- **PRD references:** 16 (M2 gate).

## D-041 — M3 ledger model: identity table plus append-only revisions plus rebuildable projection

- **Date:** 2026-11-09
- **Status:** M3 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** FR-B3/FR-B4 need stable business IDs, immutable revision history, valid-time vs knowledge-time semantics, three correction operation types, atomic linked-leg correction groups, downstream validity and full reconstructability — without M4 valuation.
- **Chosen approach:** Five tables: `core.investor`, extended `core.account`, `core.txn_business` (identity only), `core.txn_revision` (append-only; full instruction snapshot, `revision_no`, `correction_group_id`, `prev_revision_id`, `recorded_at`, `system_period`), `core.txn_version_current` (rebuildable projection), plus `core.correction_group` and `core.correction_rejection`. The business row never changes after ingest; every correction appends exactly one revision in its group; the projection upserts from the latest revision and is *rebuilt* from revisions (`rebuild_all_projections`) rather than trusted.
- **Reason:** Separates "what the transaction is" from "what version the system knew", making K1/K2 reconstruction a query rather than a rebuild, and keeps the mutable table provably disposable.
- **Alternatives:** Overwrite-in-place versioning; a single table with `updated_at`; store instructions only on the business row and diffs on revisions.
- **Why alternatives were rejected:** Overwrite-in-place cannot reconstruct K1 (the PRD's core problem); `updated_at` collapses knowledge time; diffs lose the full snapshot needed for replay and for recomputing derived legs.
- **Consequences / limitations:** The projection is not immutable (stated explicitly in schema comments and the M3 briefing). Rebuild correctness is asserted by tests. M4's as-of query reuses `get_as_of`.
- **PRD references:** 6, 9; FR-B3; D-005.

## D-042 — System period and GiST no-overlap enforcement

- **Date:** 2026-11-09
- **Status:** M3 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** Without a database-level guarantee, a bug could leave two versions of one transaction simultaneously "current" for overlapping knowledge intervals, silently accepting an impossible history.
- **Chosen approach:** `system_period TSTZRANGE` per revision, closed on correction to `[prior_recorded_at, recorded_at)`, with `EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&)` (via `btree_gist`) so overlapping periods for one `txn_group_id` are rejected by PostgreSQL (error `23P01`) regardless of the application. A raw overlapping insert is a required acceptance test.
- **Reason:** Turns the no-overlap rule from a convention into an enforced invariant, and gives the K1/K2 query a range that is provably a partition.
- **Alternatives:** Rely on application checks only; a trigger; a unique index on `recorded_at`.
- **Why alternatives were rejected:** Application-only checks have race conditions and no defence in depth; a trigger is harder to reason about and to test; a unique index forbids legitimate same-timestamp revisions for *different* transactions while not expressing the actual rule.
- **Consequences / limitations:** `btree_gist` is a new (built-in, local) extension dependency. `recorded_at` must strictly increase per `txn_group_id` (equal timestamps are rejected as `NON_MONOTONIC_RECORDED_AT`).
- **PRD references:** 9; FR-B4.

## D-043 — Corrections apply atomically; rejections are explicit audit rows

- **Date:** 2026-11-09
- **Status:** M3 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** A correction that half-applies (revision written, projection not updated; or a switch leg posted without its partner) corrupts the ledger and breaks K1/K2 reconstruction. A correction that fails silently leaves no evidence of why.
- **Chosen approach:** Validation and application run in one database transaction: validate target/prior revision/recorded-at monotonicity/allotment window, compute the candidate snapshot and derived legs, replay downstream cash/units against the full candidate set in `(posting_date, posting_sequence, txn_group_id)` order, and only then insert the group + revision, close the prior period and upsert the projection. Any validation failure writes a single `core.correction_rejection` row (with `reason_code`, attempted details, actor) and commits nothing else. Failure vocabulary: `INVALID_REFERENCE`, `NON_MONOTONIC_RECORDED_AT`, `INVALID_CORRECTION_TYPE`, `MISSING_NAV_ALLOTMENT`, `NEGATIVE_UNITS_DOWNSTREAM`, `INSUFFICIENT_CASH_DOWNSTREAM`.
- **Reason:** Atomicity makes "succeed or fail together" observable and testable (rollback test asserts zero trace); the rejection row makes the audit trail complete (PRD 6.3: rejections are part of the audit output).
- **Alternatives:** Apply-then-validate; partial commits with compensating deletes; log-only rejection without a row.
- **Why alternatives were rejected:** They can leave the ledger in a state no query can explain; log-only output is not queryable evidence.
- **Consequences / limitations:** Downstream replay is O(all transactions for the account) per correction. That is acceptable for M3's dataset size and is the documented cost of a correct validity rule. Bulk multi-transaction groups are not implemented (schema allows them).
- **PRD references:** 6.3; FR-B4; D-020.

## D-044 — M2 ingestion is instruction-only and idempotent; intents are not corrections

- **Date:** 2026-11-09
- **Status:** M3 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** M3 must load the approved M2 output into the ledger without modifying the M2 contract, without treating unrealised correction intents as accepted corrections, and without ever confusing generator estimates with accounting facts.
- **Chosen approach:** `ingest_m2_output` upserts investors/accounts by `synthetic_ref` and creates `txn_business` + original revision (`revision_no = 1`, `system_period = [recorded_at, +∞)`) per transaction; already-present `txn_group_id`s are skipped, so re-ingestion is a no-op. `generator_estimated_*` is never read. Correction intents stay in their file; converting one into a `CorrectionRequest` and calling `apply_correction` is the only path to a correction. Ingestion validates scheme existence and positive decimal amounts/units.
- **Reason:** Preserves the frozen M2 contract (D-034/D-040), keeps "generated" distinct from "accepted" (D-039), and makes re-ingestion safe during development.
- **Alternatives:** Rewrite M2 records to fit the ledger; ingest intents as accepted revisions; re-derive estimates as facts.
- **Why alternatives were rejected:** They violate the freeze, invent accepted history, or launder estimates into facts.
- **Consequences / limitations:** Batch provenance (dataset hash) lives in the ingestion report/CLI output, not in a ledger table; M7 may add a `pipeline_run` table.
- **PRD references:** 5.2, 6.2, 6.3; FR-B1 vs FR-B4.

## D-045 — M3 computes posting derivations, not valuation

- **Date:** 2026-11-09
- **Status:** M3 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** Correction validity needs derived units/proceeds (D-020), but M4 owns valuation and M5 owns returns. M3 must not drift into either.
- **Chosen approach:** M3 computes only the allotment posting derivations from METHODOLOGY §2.1–§2.3 / §3.3–§3.6 (`ROUND_DOWN` units for amount-instructed purchases, `ROUND_HALF_UP` cash, switch residual ≥ 0, SIP two-leg posting) to replay cash/units for validity. M3 never values a position at an arbitrary date and never calculates a return. `get_as_of` returns **revisions**, not valuations.
- **Reason:** Draws the M3/M4 boundary where the PRD draws it (FR-B3/B4 vs FR-B5/B6), while still allowing the §6.3 validity rule to be enforced.
- **Alternatives:** Defer all derivation to M4 and accept corrections unvalidated; implement valuation queries in M3.
- **Why alternatives were rejected:** Unvalidated corrections violate FR-B4; early valuation duplicates M4.
- **Consequences / limitations:** The cash/units replay is a posting simulation, not a valuation report. Its outputs are used only for accept/reject; they are not stored as positions.
- **PRD references:** 6, 9; FR-B3/B4 vs FR-B5/B6; D-019, D-020, D-024–D-026.

## D-046 — M3 verification supplement (verified findings, no redesign)

- **Date:** 2026-11-09
- **Status:** Verified supplement (review requested before M3 sign-off)
- **Problem:** The M3 delivery needed focused proof of four exact claims: append-only anatomy, GiST identity, split-date SWITCH semantics and replay ordering — with source, SQL and test evidence for each.
- **Findings (all re-executed, 38 tests passing):**
  1. **Append-only:** `apply_correction` closes the prior revision's `system_period` (`[prior_recorded_at, new_recorded_at)`) before inserting the successor; this is the controlled interval-close that D-005 already authorises. Every business column of the prior row is provably unchanged (`test_append_only_system_period_close_preserves_business_facts`). The projection (`txn_version_current`) is separately rebuildable and is not the immutable source.
  2. **GiST identity:** `txn_group_id` is the stable business transaction identity; `correction_group_id` identifies the correction operation; linked legs are sub-revision events (never separate rows), so the exclusion constraint cannot reject valid SIP/SWITCH legs. Live definition confirmed: `EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&)`.
  3. **Split-date SWITCH:** covered by new integration tests — source NAV 2024-01-05 @10 and target NAV 2024-01-06 @30 produce 3.333 target units and 0.01 residual with atomic lineage; target NAV arriving after day 5 is rejected `MISSING_NAV_ALLOTMENT`. M2's single switch date is documented as a generator limitation (D-036), not a ledger limit.
  4. **Replay ordering:** the comparator is `(posting_date, posting_sequence, txn_group_id)`; `recorded_at` is never an economic ordering key. Covered by `test_replay_uses_posting_sequence_not_recorded_at`.
- **Reason:** Records verified evidence rather than assertions, while keeping M3's milestone boundary unchanged.
- **Consequences / limitations:** No implementation change was made; the two NAV fixture schemes added for the switch tests (`100003`, `100004`) are test-only rows in the M1 snapshot. M4 remains unstarted pending Vicky's approval.
- **PRD references:** 6, 9; FR-B3, FR-B4; D-005, D-041, D-042, D-045.

## D-047 — Separate the immutable revision source from the temporal projection

- **Date:** 2026-11-09
- **Status:** Architectural correction required before M3 closure (Vicky, 2026-11-09)
- **Problem:** FR-B3 says transaction revisions are never updated or deleted. The M3 implementation (D-046-era) updated `core.txn_revision.system_period` to close the prior knowledge interval. Business facts did not change, but the row was mutated.
- **Chosen approach:** `core.txn_revision` is now **strictly append-only** — it holds accepted revision facts plus `recorded_at`, and a `BEFORE UPDATE OR DELETE` trigger (`trg_txn_revision_immutable`) raises if any attempt is made. Knowledge-time intervals live in the new `core.txn_revision_period` (rebuildable projection). The GiST no-overlap constraint moved to `txn_revision_period`. On correction the service now: closes the prior interval in the projection, appends the new revision, inserts the new interval and upserts `txn_version_current` — all in one transaction, with full rollback on failure. `rebuild_all_projections()` rebuilds **both** projections from the immutable source (`LEAD(recorded_at)` for period ends; `DISTINCT ON` for current versions) and the rebuilt result must equal the live projection exactly.
- **Reason:** Satisfies the literal FR-B3 requirement: no UPDATE/DELETE on accepted revision rows, ever, with database-level enforcement.
- **Alternatives:** Keep the UPDATE and argue it is metadata-only; event-source with separate current-history table only (no periods at all).
- **Why alternatives were rejected:** The first still mutates the row under review; the second loses the `system_period` ranges the K1/K2 read needs.
- **Consequences / limitations:** The old `system_period` column on `txn_revision` was dropped by migration `005_revision_period_split.sql` after copying the live intervals into the projection. Tests were adapted accordingly (period queries and overlap test moved to the projection table). SWITCH and replay semantics are unchanged.
- **PRD references:** 6, 9; FR-B3; D-005, D-041, D-042.
## D-048 — M3 approval

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M3 needed formal closure.
- **Chosen approach:** Record M3 **Approved**. D-047's split (immutable revision source + rebuildable period/projected tables) satisfies FR-B3/B4. Evidence: 17 M3 tests, full suite 39 passing, M2 ingestion idempotent (2,287).
- **Consequences / limitations:** M1–M3 contracts frozen; M4 valuation starts from this baseline.
- **PRD references:** 16 (M3 gate).

## D-049 — M4 position derivation from bitemporal revisions

- **Date:** 2026-11-09
- **Status:** M4 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** FR-B5 requires `positions(account_id, valid_date, known_as_of)` to reconstruct cash and units as of a valid date **using only versions known at K**, with correct treatment of contributions/withdrawals and each internal movement.
- **Chosen approach:** Derive positions from `LedgerService.get_as_of(K)` — never the current projection — then replay posting legs in `(posting_date, posting_sequence, txn_group_id)` order (the same key as M3 validity). A leg posts only if its posting date is `<= valid_date`. Contributions/withdrawals are cash legs on `effective_date`; purchases, redemptions, SIP purchase legs and switch legs post on their allotment dates. SIP contribution and purchase are two legs; switch source and target are two legs. Zero opening balances; explicit funding via `CONTRIBUTION`.
- **Reason:** The derivation is a pure replay of the approved leg definitions, so K1/K2 views differ only in which revisions are visible — corrections can therefore change historical positions exactly as FR-B4 intends.
- **Alternatives:** Read cash/units from `txn_version_current`; keep a separate positions table.
- **Why alternatives were rejected:** The projection would collapse K1/K2; a stored positions table would be a second source of truth that could drift from revisions.
- **Consequences / limitations:** Positions are computed on demand (O(revisions for the account)). No positions table exists; M4 returns data structures, not persisted rows. Negative intermediates raise an invariant error rather than being clamped.
- **PRD references:** 6, 9; FR-B5; D-024–D-027.

## D-050 — NAV selection and stale policy

- **Date:** 2026-11-09
- **Status:** M4 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** FR-B6 needs the NAV on the valuation date, a stale-carry rule, and explicit failure beyond it — with scheme identity preserved.
- **Chosen approach:** For each holding, the price is the latest `core.nav_observation` (the M4 parameterised `nav_snapshot_id`, one of the immutable M1 snapshots) with `nav_date <= valuation_date`. If that price is dated `valuation_date` it is fresh; if it is 1–5 calendar days older it is **stale** and carried forward, flagged, and reported in a separate stale bucket. If the latest NAV is 6+ days older, or the scheme has no NAV at or before the date, valuation **fails explicitly** with `STALE_BEYOND_LIMIT` / `MISSING_NAV` — never a silent fill. Scheme identity is the AMFI code; there is no name-based merging. The price object carries `(price, price_date, is_stale, stale_days, scheme_code, snapshot_id)`.
- **Reason:** Matches PRD §5.3 and D-028 exactly, and makes stale/small residuals visible in the output schema rather than as prose.
- **Alternatives:** Exact-date-only valuation (rejects every non-NAV day); an exchange holiday calendar (unapproved).
- **Why alternatives were rejected:** Exact-date-only would make most calendar valuations impossible; a holiday calendar is out of scope and unverified for AMFI.
- **Consequences / limitations:** Stale valuation is reported, not hidden: every holding line carries its stale flag. Beyond-limit failures abort the whole valuation (no partial portfolio value) so no caller can mistake a stale price for a real one.
- **PRD references:** 5.3, 8; FR-B6; D-028.

## D-051 — Valuation formula and reconciliation invariants

- **Date:** 2026-11-09
- **Status:** M4 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** FR-B6/B10 require `position_value = units × NAV`, `portfolio_value = sum + cash`, in `Decimal`/`NUMERIC`, with position-to-valuation reconciliation enforced — without implementing TWR/XIRR (M5).
- **Chosen approach:** `holdings_value = Σ (units.quantize(0.001) × price).quantize(0.01)` and `portfolio_value = cash + holdings_value − (fresh_value + stale_value − holdings_value == 0)`. The service also returns the split `fresh_value` / `stale_value` / `cash` and asserts in `Decimal` arithmetic that the sum equals the portfolio value (rounding-tolerance one cent, recorded); any mismatch raises `RECONCILIATION_FAILED`. All inputs are `Decimal` (`NUMERIC` from PostgreSQL); no binary float is used in any path.
- **Reason:** One formula, one invariant, Decimal-only, with stale value separated rather than blended — exactly the reporting the PRD asks for.
- **Alternatives:** Value with float; blend fresh and stale into one unnamed total.
- **Why alternatives were rejected:** Float breaks replay equality; blending hides stale exposure, which is the entire point of the stale report.
- **Consequences / limitations:** The valuation is a point-in-time snapshot (cash + holdings). No performance ratio is computed; TWR/Modified Dietz/XIRR remain M5.
- **PRD references:** 8; FR-B6, FR-B10; D-008, D-026, D-028.

## D-052 — M4 approval

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M4 needed closure.
- **Chosen approach:** Record M4 **Approved**. Boundary tests verified (5-day stale accepted/flagged/valued; missing NAV raises `MISSING_NAV`; multi-holding failure is atomic with no partial total). Full suite 50 passed.
- **Consequences / limitations:** M1–M4 frozen; M5 starts from this baseline.
- **PRD references:** 16 (M4 gate).

## D-053 — M5 performance engine

- **Date:** 2026-11-09
- **Status:** M5 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** TWR, Modified Dietz and XIRR must follow the approved full-calendar-day convention exactly, with independent references.
- **Chosen approach:** Pure `Decimal` TWR (flow-day and gap subperiods), Dietz with `T = inclusive days`, and XIRR per METHODOLOGY §7.7 (2,001-point `ln(1+r)` scan, bisection refine, Newton-from-midpoint fallback, explicit statuses). Account-level computation drives `ValuationService` end-of-day values. `docs/M5_METHODOLOGY_MAPPING.md` maps fixture → function → test; `reference_xirr` is a separately written bisection solver.
- **Reason:** Matches the reviewed methodology to the letter and guarantees E1-style comparability.
- **Alternatives:** Latin/Float solvers; library XIRR; single NO_ROOT vocabulary.
- **Why alternatives were rejected:** Float breaks replay; libraries hide statuses; a single status collapses D-029's distinction.
- **Consequences / limitations:** End-of-day valuations drive subperiods (see mapping boundary notes). TWR/Dietz remain period returns while XIRR is annualised — they are never conflated.
- **PRD references:** 8; FR-B7; D-009, D-010, D-028, D-029.

## D-054 — M5 approval

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M5 needed closure.
- **Chosen approach:** Record M5 **Approved**. All methodology fixtures and the independent reference pass; K1/K2 replay verified (K1 0.4000%/4.8125%, K2 0.4800%/5.8001%). Full suite 68 passed.
- **Consequences / limitations:** M1–M5 frozen; M6 starts from this baseline.
- **PRD references:** 16 (M5 gate).

## D-055 — M6 snapshots versus restatement

- **Date:** 2026-11-09
- **Status:** M6 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** Replay and restatement are routinely conflated; the distinction is the product's core claim.
- **Chosen approach:** Replay (same `known_as_of`, same snapshot) must return `REPLAY_EXACT`; restatement (later `known_as_of`) returns `RESTATEMENT_GENERATED` with per-field deltas and never overwrites the archive. Engine-version and snapshot-version mismatches return explicit statuses. Canonical payload excludes wall-clock fields from equality; persisted `generated_at` is reuseable.
- **Reason:** Makes "original report reproduced" vs "updated-input restated" mechanically distinct, as the PRD requires.
- **Alternatives:** Merge the two operations; overwrite on restatement.
- **Why alternatives were rejected:** They would let a restated report masquerade as an exact replay and destroy the audit pair.
- **Consequences / limitations:** One snapshot per generation call; no figure-level additive decomposition is claimed for nonlinear measures (attribution is linked explanation).
- **PRD references:** 10; FR-B8/B9/B14; D-011, D-012, D-030.

## D-057 — M5/M6 approvals

- **Date:** 2026-11-09
- **Status:** Approved — Vicky, 2026-11-09
- **Problem:** M5/M6 needed closure in sequence.
- **Chosen approach:** Record M5 and M6 **Approved**, with M6's replay/restatement distinction and comparator evidence. Full suites at those points: 68 (M5) and 70 (M6) passing.
- **Consequences / limitations:** M1–M6 frozen; M7 starts from this baseline.
- **PRD references:** 16 (M5/M6 gates).

## D-058 — M7 invariants versus stale limits

- **Date:** 2026-11-09
- **Status:** M7 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** Stale NAVs are expected for schemes whose coverage ended long before the invariant date; treating them as ledger failures would fail every run for a market-data reason.
- **Chosen approach:** The invariant runner reports stale/missing-NAV valuations as expected limitations (`stale_accounts`) while counting true ledger violations (un-derivable positions, negative balances, invariant-catch failures) toward pipeline failure. The run still fails if any true invariant fails.
- **Reason:** Keeps the pipeline gate meaningful: missing coverage is transparent, never silent, but not confused with inconsistency.
- **Alternatives:** Fail the pipeline on any stale account; silently clamp valuation dates to the latest available NAV.
- **Why alternatives were rejected:** The first would block release for an accepted market-data limit; the second hides the limit the PRD explicitly wants surfaced.
- **Consequences / limitations:** Invariant evidence in `RESULTS.md` is per-account with stale counts; dashboards must show the stale bucket, not pretend it priced.
- **PRD references:** 5.3, FR-B10, FR-B12; D-050.

## D-059 — M5–M10 approvals and final scope boundary

- **Date:** 2026-11-09
- **Status:** Authorised — Vicky, 2026-11-09 (sequential approval with mandatory controls)
- **Problem:** Remaining milestones needed unambiguous closure rules: methodology fidelity (M5), replay-vs-restatement (M6), double reproduce (M7), frozen pre-registration (M8), dashboard validation (M9), clean rebuild (M10).
- **Chosen approach:** M5 fixtures + reference within 1 bp; M6 replay-exact vs restatement-generated; M7 `RESULTS.md` sha256 `ac6257e2…` identical across double run; M8 frozen config `93fb380b…` with 11,436 detail rows; M9 ten SQL queries executed + PBIP definitions; M10 clean rebuild 73 tests. E9 partial and E6/png/manual steps remain honest limitations.
- **Consequences / limitations:** v1.0.0 is the PRD scope only; no new features were added; FundLens was never modified.
## D-059 — M5–M10 approvals and final scope boundary

- **Date:** 2026-11-09
- **Status:** Authorised — Vicky, 2026-11-09 (sequential approval with mandatory controls)
- **Problem:** Remaining milestones needed unambiguous closure rules: methodology fidelity (M5), replay-vs-restatement (M6), double reproduce (M7), frozen pre-registration (M8), dashboard validation (M9), clean rebuild (M10).
- **Chosen approach:** M5 fixtures + reference within 1 bp; M6 replay-exact vs restatement-generated; M7 `RESULTS.md` sha256 `ac6257e2…` identical across double run; M8 frozen config `93fb380b…` with 11,436 detail rows and the documented E9 coverage (n = 654); M9 10/10 queries executing + PostgreSQL-only PBIP; M10 clean rebuild 75 tests.
- **Consequences / limitations:** v1.0.0 is the PRD scope only; no new features were added; FundLens was never modified.
- **PRD references:** 16; D-053, D-055, D-058.

## D-060 — Final release verification (no new features)

- **Date:** 2026-11-10
- **Status:** Final verification, no design change
- **Problem:** Four pre-release checks remained: E9 qualification, Power BI manual validation, the M1 checksum-tamper exercise and the consolidated rebuild.
- **Chosen approach:** E9 coverage table (1,040 eligible, 654 solved, 386 excluded, n = 654) recorded in `results/E9_COVERAGE.md`, `RESULTS.md` and `docs/briefings/M8.md`; PBIP prepared with PostgreSQL-only connectors (`dashboard/PortfolioReport/` + `VALIDATION.md`) and left honestly as manual; checksum tamper exercised against a disposable clone with a regression test (`tests/integration/test_migration_checksum.py`); full rebuild, double reproduce and 75-test suite re-run.
- **Reason:** Converts the last open items into executed evidence wherever automation permits and explicit non-claims where it does not.
- **Alternatives:** Fabricate Power BI screenshots; claim remote CI; retune E9 scenarios to raise coverage.
- **Why alternatives were rejected:** They would fabricate evidence or alter a frozen study.
- **Consequences / limitations:** Live Power BI execution + screenshots remain manual; CI remote execution remains unperformed; E9 remains partial as documented. v1.0.0 is a release candidate pending final approval.
- **PRD references:** 12, 16, 19.

## D-056 — Overwrite comparator retains current rows only

- **Date:** 2026-11-09
- **Status:** M6 design (authorised by Vicky 2026-11-09; implementation underway)
- **Problem:** A comparator that peeked at archived payloads would trivially "reproduce" history.
- **Chosen approach:** The comparator ingests only `txn_version_current` rows (latest instruction per transaction) and never reads `report_snapshot` or revision history. Any corrected transaction is unreproducible because the prior amount, lineage and reason were overwritten; uncorrected accounts stay reproducible.
- **Reason:** Produces an honest loss list (E3) instead of a replay triviality.
- **Alternatives:** Give the comparator the full ledger; have it infer history from applying corrections backwards.
- **Why alternatives were rejected:** Both reconstruct information the naive schema does not retain, defeating the purpose of the comparator.
- **Consequences / limitations:** Count-based comparison only (no improvement percentage, D-022).
- **PRD references:** 10.4; FR-B14.

