# M0 Design Review — Decisions Required Before Financial Implementation

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Status | Approved by Vicky on 2026-11-09, with refinements; M0 exit gate met and formally recorded as approved after the fixture-appendix and NAV-contract reviews. |
| Date | 2026-11-09 |
| Authoritative specification | `PRD.md` (PRD v2.0), then approved `DECISIONS.md` entries |
| Reference fixtures | `docs/METHODOLOGY.md` |
| Data contract | `docs/FUNDLENS_NAV_CONTRACT.md` |

> This review does not re-open matters the PRD already decides. It resolves the financial conventions that the PRD leaves open or only sketches. No financial implementation began before this review.

### Approval record

Vicky approved the 22-item checklist on 2026-11-09 with these refinements:

- same-effective-date transactions use an explicit deterministic `posting_sequence`, not a hardcoded universal transaction-type priority;
- the switch group has a maximum five-calendar-day interval and is rejected in full if the target leg cannot be completed;
- residual cash is accounted for exactly once;
- XIRR distinguishes `NO_ROOT_IN_DOMAIN` from `NO_ROOT_PROVEN` and documents search limitations;
- snapshots preserve all necessary market-data, mapping, calculation, schema, configuration and environment provenance;
- the overwrite comparator must genuinely attempt historical recalculation from current rows only, and archived retrieval is not replay;
- sensitivity reporting includes signed and absolute movements, thresholds, sample sizes and failure counts;
- FundLens remains strictly read-only: use the verified raw-file fallback (Option A), do not query the FundLens database or its volumes, and reconcile the 86-vs-85 file count;
- no Jira project will be created or claimed.

The decisions are recorded as approved in `DECISIONS.md` D-023–D-032. Vicky subsequently reviewed the complete numerical fixture appendix in `docs/METHODOLOGY.md` (fixtures F1–F19, Appendix A) and the FundLens NAV contract, and approved the contract under **Option A** (verified raw-file fallback; no FundLens database or volume access). Vicky also approved four final documentation amendments on 2026-11-09: (1) the inclusive full-calendar-day period-boundary convention; (2) the completed F5 contribution/withdrawal and F7 exact-date working papers; (3) the separated F19 exact-replay, input-mismatch, engine-mismatch and restatement outcomes; (4) the full working shown for the F13/F19 XIRR terminal-valuation timestamps. No approved financial convention was changed beyond these clarifications. The M0 exit gate was formally recorded as met and approved on 2026-11-09; M1 Foundations may begin under the PRD milestone gate. No financial implementation began before that record.

---

## 1. What is already decided by the PRD (not being re-asked)

- Portfolio accounting is the product; bitemporality is the audit mechanism.
- Synthetic accounts and transactions; real AMFI NAVs.
- INR only; Growth plans only; no IDCW; no fees; no multi-currency; no tax.
- PostgreSQL 15+, Python 3.12+, Docker Compose, versioned migrations, Decimal/NUMERIC.
- TWR, Modified Dietz and XIRR, separately labelled.
- Immutable transaction revisions; replace, void and reverse-and-replace.
- Immutable report snapshots; replay; restatement attribution; overwrite comparator.
- Pre-registered sensitivity study; no selective reporting.
- No GIPS/SEBI compliance claim; educational prototype.

The decisions below are the material conventions that need one consolidated approval.

---

## 2. Decision summary

| ID | Decision | Recommendation | Fixture impact | PRD reference |
|---|---|---|---|---|
| D-OPEN-01 | Instruction / effective / allotment dates | Post simple purchases and redemptions on the allotment date; SIP contribution and purchase legs may post on different dates; switch legs may post on different NAV dates within one atomic group. | A purchase instructed on a non-NAV day posts on the next NAV date. SIP cash sits visibly for one day. | 5.3, 6.1, 6.2 |
| D-OPEN-02 | SWITCH semantics | One atomic group; source redemption first, target purchase next, residual cash credited; both legs succeed or fail together; never an external flow. | 100 units × 20.0000 = 2,000.00; target NAV 30.0000; 66.666 target units; 0.02 residual. | 6.2, 6.3 |
| D-OPEN-03 | Rounding and residual | Units 3 dp; amounts 2 dp; NAV as published; general `ROUND_HALF_UP`; amount-instructed purchase units use `ROUND_DOWN` so the cash debit never exceeds the instruction; residual cash is recorded, never discarded. | A 10,000 purchase at NAV 30 buys 333.333 units and debits 9,999.99, leaving 0.01 cash. | 5.3, 7, 8 |
| D-OPEN-04 | Opening funding and same-day order | Accounts start at zero; fund via CONTRIBUTION; no overdraft; reject negative cash/units; same-effective-date groups carry an explicit deterministic `posting_sequence`; a rejected group posts nothing; no universal transaction-type priority. | A withdrawal can only use cash available at its `posting_sequence`; a SIP contribution funds its purchase only if sequenced before it. | 6.1, 6.2 |
| D-OPEN-05 | Performance conventions | Flows at start of day; contributions positive, withdrawals negative; purchases/redemptions/switches internal; TWR and Modified Dietz are period returns; XIRR is annualised; calendar-day weighting; stale NAV policy; report boundaries inclusive. | TWR 3.3421% vs Modified Dietz 3.7895% on the mid-period-flow fixture. | 8, 10, 12 |
| D-OPEN-06 | XIRR roots and failures | Newton-Raphson + bounded bisection fallback; root scan; explicit `SUCCESS`, `NO_ROOT`, `MULTIPLE_ROOTS`, `NON_CONVERGENCE`, `INVALID_CASH_FLOWS`; never pick an arbitrary root. | -100, +230, -132 has roots at 10% and 20%; -100, +1, -100 has no root. | 8, 14 |
| D-OPEN-07 | Snapshot reproducibility | Store parameters, K time, NAV snapshot/checksum, mapping version, engine/git/schema/config versions, rounding policy, canonical payload/hash; distinguish retrieval, replay and restatement; comparator must genuinely fail to reconstruct. | K1 report stays at 0.4000% TWR; K2 restates to 0.4800%. | 9, 10 |
| D-OPEN-08 | Sensitivity statistics | Report signed median, median absolute, p95 absolute, threshold shares and n per scenario; never let signs cancel; pre-register config. | A +10 bp and -10 bp error cannot net to zero: median signed 0, median absolute 10 bp. | 12.2 |

---

## 3. D-OPEN-01 — Instruction date, effective date and allotment date

### 3.1 Ambiguity

The PRD distinguishes the three dates but does not fully specify whether cash and units move together when the effective date is not a NAV date. If cash leaves on the instruction date and units appear on a later allotment date, the account has interim cash. If both move on the allotment date, the effective date is shifted. The choice affects positions, valuation, TWR and the audit trail.

### 3.2 Numerical example

A purchase is instructed on Saturday 2026-01-10 for `10,000.00`. The scheme's next NAV is Monday 2026-01-12 at `50.0000`.

- Option A (cash and units on allotment date): on 1/10 the account still has `10,000.00` cash; on 1/12 it has `200.000` units and `10,000.00` less cash.
- Option B (cash on instruction date, units on allotment date): on 1/10 cash falls by `10,000.00` and the account holds a receivable; on 1/12 units appear. Interim value is a receivable, not cash or units.

### 3.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Post the whole simple purchase/redemption on the allotment date; retain instruction date for audit. | Simple, conserves value, no receivable model. Effective date equals posting date. |
| B | Post cash on the instruction/effective date and units on the allotment date; model interim cash/receivable. | More realistic but adds a receivable/clearing account and more states. |
| C | Treat all three dates as identical. | Rejected: hides date differences and contradicts the PRD. |

### 3.4 Recommendation

**Option A for simple purchases and redemptions.** For SIP, keep the PRD's explicit split: contribution on the contribution date, purchase on the allotment date, interim cash visible. For switches, use sequential source/target NAV dates within one atomic group (D-OPEN-02). Never conflate the three dates.

### 3.5 What changes in the results

- Cash and units appear together for simple trades, simplifying valuation.
- A SIP may have one or more days of interim cash, which is valued and included in TWR.
- A switch may have interim cash between the source and target NAV dates.
- Instruction date is audit-only and does not affect returns.

**PRD reference:** 5.3 (allotment rule), 6.1 (external vs internal), 6.2 (transaction semantics).

---

## 4. D-OPEN-02 — SWITCH semantics

### 4.1 Ambiguity

The PRD requires an atomic linked redemption and purchase, but does not define whether both legs use the same date, how the target NAV is selected, or how rounding residual cash is handled. A switch must never be an external flow.

### 4.2 Numerical example

- Source scheme A: redeem `100.000` units at NAV `20.0000` → proceeds `2,000.00`.
- Target scheme B: NAV `30.0000`.
- `2,000 / 30 = 66.666666...`.
- With half-up units: `66.667`; target cost `2,000.01`; residual `-0.01`.
- With down units: `66.666`; target cost `1,999.98`; residual `+0.02`.

### 4.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | One common effective date; both schemes must have a NAV on that date. | Simple, but may delay the switch or reject valid switches. |
| B | Source redemption on its NAV date; target purchase on the next target NAV date; both in one atomic group; residual cash credited. | Realistic; interim cash is visible; needs careful TWR treatment (still internal). |
| C | Treat the switch as a withdrawal plus a contribution. | Rejected: creates a false external flow and distorts TWR/XIRR. |

### 4.4 Recommendation

**Option B.** One atomic group, sequential NAV dates within 5 calendar days, target units ROUND_DOWN, residual cash credited. Both legs succeed or fail together. The switch is internal and never enters the external-flow set.

### 4.5 What changes in the results

- No external flow; TWR is not neutralised for the switch.
- Interim cash is part of portfolio value.
- Target units are slightly lower than a half-up calculation, but the residual cash preserves total value.
- If either scheme lacks a NAV within the limit, the whole switch is rejected.

**PRD reference:** 6.2, 6.3; prompt D-OPEN-02.

---

## 5. D-OPEN-03 — Rounding and residual cash

### 5.1 Ambiguity

The PRD says units 3 dp, amounts 2 dp and NAV as published, but does not fix the rounding mode, the exact rounding boundary, or how a purchase that is instructed by amount reconciles to units × NAV.

### 5.2 Numerical example

Purchase `10,000.00` at NAV `30.0000`:

- `10,000 / 30 = 333.333333...`.
- Half-up units: `333.333`; `333.333 × 30 = 9,999.99`; residual `0.01`.
- If units were `333.334`, cost `10,000.02`, exceeding the instruction by `0.02`.

### 5.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Half-up units everywhere; debit instructed amount; book the difference as a rounding expense/income. | Requires a fee/expense concept that the PRD excludes; can over-debit. |
| B | Half-up units; debit actual `units × NAV`; record residual cash. | Transparent, but can over-debit if units round up. |
| C | ROUND_DOWN for amount-instructed purchase units; debit actual `units × NAV`; residual stays in cash. | Never over-debits; residual is explicit; slight unit under-allocation. |
| D | Use 6 dp units to make residuals negligible. | Still possible; does not solve the reconciliation principle. |

### 5.4 Recommendation

**Option C.** General mode `ROUND_HALF_UP` for amounts, redemptions and other unit calculations; `ROUND_DOWN` for amount-instructed purchase units (purchase, SIP purchase, switch target). Store `instructed_amount`, `units`, `allotment_nav`, `actual_cash` and `rounding_residual`. Report residuals by account and transaction type. Never silently discard a difference. Never change the published NAV precision.

### 5.5 What changes in the results

- Cash debit is always `<=` the instructed amount for purchases.
- The small residual remains in cash and is included in valuation.
- Switch target units may be 0.001 lower than a half-up calculation; residual cash compensates.
- Redemption proceeds use half-up and can be a cent above the exact product.

**PRD reference:** 5.3, 7, 8; prompt D-OPEN-03.

---

## 6. D-OPEN-04 — Opening account funding and same-day ordering

### 6.1 Ambiguity

The PRD does not state whether accounts can start with balances, whether overdrafts are allowed, or how same-day transactions are ordered for cash/unit sufficiency.

### 6.2 Numerical example

An account has `1,000.00` cash. On the same effective date it has a `1,200.00` withdrawal at `posting_sequence` 10, a `+500.00` contribution at 20, and a `1,200.00` purchase at 30. At sequence 10 the withdrawal fails because cash is only 1,000.00. The contribution then raises cash to 1,500.00, and the purchase succeeds, leaving 300.00 cash and 120.000 units at NAV 10.0000. A hardcoded contributions-first rule would have posted the withdrawal and then failed the purchase, producing a different end state.

### 6.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Zero opening balances; explicit contributions; no overdraft; reject negative cash/units; explicit `posting_sequence` per group. | Clean audit trail; matches PRD; makes intraday dependencies explicit. |
| B | Allow a configured opening balance or overdraft. | Adds an unexplained funding source and negative-cash states; rejected for v1. |
| C | Process same-day transactions strictly in recorded order. | Recorded order is not a financial ordering rule and can reject a valid end-of-day state. |
| D | Hardcode a universal transaction-type priority. | Cannot represent every legitimate same-day dependency; rejected by Vicky's refinement. |

### 6.4 Recommendation

**Option A plus an explicit deterministic `posting_sequence`.** Process same-effective-date groups in ascending `posting_sequence`; break ties deterministically by immutable group ID. Do not hardcode a universal transaction-type priority. Require sufficient cash/units after each group. Reject a group atomically if it would create negative cash or units; record the rejection and continue with later groups against the actual posted balances. No overdraft in v1. Opening balances are explicit `CONTRIBUTION` transactions.

### 6.5 What changes in the results

- Every account has a traceable funding event.
- A same-day SIP contribution can fund its purchase only when its `posting_sequence` is earlier.
- A withdrawal cannot rely on a later same-day transaction; the order is explicit and auditable.
- Negative cash/units cannot occur, simplifying TWR denominators and invariants.
- A rejected group is visible, with a reason, rather than silently reordered.

**PRD reference:** 6.1, 6.2; prompt D-OPEN-04.

---

## 7. D-OPEN-05 — Performance conventions

### 7.1 Ambiguity

The PRD specifies TWR and Modified Dietz formulas but leaves the flow-timing, day-count, boundary, stale-NAV and annualisation conventions to be documented. XIRR signs and terminal value also need explicit treatment.

### 7.2 Numerical example

Period 2026-02-02 to 2026-02-28; `V_S = 100,000.00`; contribution `+50,000.00` on 2026-02-26; pre-flow value `102,000.00`; post-flow `152,000.00`; `V_E = 154,000.00`.

- TWR: `(102,000/100,000) × (154,000/152,000) - 1 = 3.3421%`.
- Modified Dietz: `T = 27`, `t = 24`, `w = 3/27`; `R = 4,000 / (100,000 + 5,555.56) = 3.7895%`.

The 44.74 bp difference is the approximation in Modified Dietz, not a bug.

### 7.3 Options

| Convention | Options | Recommendation |
|---|---|---|
| Flow timing | Start of day vs end of day | Start of day, consistent with the PRD's TWR formula. |
| Sign | Contribution positive vs negative | Portfolio perspective: contribution positive, withdrawal negative. XIRR uses investor perspective: contribution negative, withdrawal positive. |
| Day count | Actual/365 vs actual/actual vs business days | Calendar days; actual/365 for XIRR; inclusive `T` for Modified Dietz. |
| Boundaries | Inclusive vs exclusive end | Inclusive `[S, E]`; `V_S` before flows on `S`; `V_E` after flows on `E`. |
| Stale NAV | Forward-fill vs fail | Carry forward up to 5 calendar days, flag stale, fail beyond. |
| Annualisation | Period vs annualised | TWR and Modified Dietz are period returns; XIRR is annualised. Do not compare without labelling. |
| Internal flows | Include vs exclude | Contributions/withdrawals only; purchases/redemptions/switches internal. SIP contribution once. |
| Terminal value | Include vs omit in XIRR | Include exactly once as a positive final flow; do not double-count a withdrawal. |

### 7.4 Recommendation

Adopt the table above. Use the formulas and fixtures in `docs/METHODOLOGY.md`. Label TWR and Modified Dietz as period returns and XIRR as an annualised money-weighted return. Do not annualise TWR in the core v1 output; if an annualised TWR is shown later, label it separately.

### 7.5 What changes in the results

- TWR is flow-neutral but requires valuations at flow dates.
- Modified Dietz is an approximation and can differ materially when a flow is large and late in the period.
- XIRR reflects investor timing and can differ from TWR; the SIP fixture shows 15.2381% vs 6.5248%.
- Stale NAV flags prevent silent mark-to-market errors.

**PRD reference:** 8, 10, 12.1 E9; prompt D-OPEN-05.

---

## 8. D-OPEN-06 — XIRR multiple roots and failure states

### 8.1 Ambiguity

The PRD requires Newton-Raphson with a bounded bisection fallback and explicit failure handling, but does not define the root domain, the multiple-root policy, or the exact statuses.

### 8.2 Numerical example

- Multiple roots: `-100` at t0, `+230` at t1, `-132` at t2. Roots at `10%` and `20%`.
- No root: `-100` at t0, `+1` at t1, `-100` at t2. NPV is always negative; no root.
- Invalid: all flows negative; no sign change.

### 8.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Newton only; return the first converged root. | Can silently pick a root; rejected. |
| B | Newton + bisection; return a single root even if multiple exist. | Still arbitrary; rejected. |
| C | Scan, detect multiple roots, return `MULTIPLE_ROOTS` with all roots; Newton + bisection for a single root. | Explicit, defensible, testable. |
| D | Use a library without validating conventions. | Rejected: hides failure states. |

### 8.4 Recommendation

**Option C, refined by Vicky.** Domain `r ∈ (-0.999999, 1000)`, scan on `ln(1+r)`, refine brackets, return `SUCCESS`, `NO_ROOT_IN_DOMAIN`, `NO_ROOT_PROVEN`, `MULTIPLE_ROOTS`, `NON_CONVERGENCE` or `INVALID_CASH_FLOWS`, with iterations, method, residual and, where applicable, the nearest root outside the domain. `NO_ROOT_IN_DOMAIN` means the configured scan found no root; it is not a mathematical proof. `NO_ROOT_PROVEN` requires a documented analytic argument. Never choose an arbitrary root. Document the tangential-root and finite-grid limitations.

### 8.5 What changes in the results

- A multiple-root cash-flow pattern is reported as ambiguous, not as a single XIRR.
- A no-root case is reported as `NO_ROOT_IN_DOMAIN` or `NO_ROOT_PROVEN`, not as 0% or NaN; the two are never conflated.
- The dashboard and RESULTS must show the status; a numeric XIRR is shown only for `SUCCESS`.

**PRD reference:** 8, 14; prompt D-OPEN-06.

---

## 9. D-OPEN-07 — Historical snapshot reproducibility

### 9.1 Ambiguity

The PRD requires immutable snapshots and replay but does not define the exact metadata, the canonical payload, or the difference between retrieving an archived report and recalculating it. The overwrite comparator must be genuinely tested, not merely allowed to retrieve a stored snapshot.

### 9.2 Numerical example

K1 report at 2026-01-31 09:00 UTC: 200 units, cash 90,000.00, value 100,400.00, TWR 0.4000%, XIRR 4.8125%.

Correction at K2 = 2026-02-05 11:00 UTC: 240 units, cash 88,000.00, value 100,480.00, TWR 0.4800%, XIRR 5.8001%.

- Archived retrieval of K1 must return the K1 payload exactly.
- Replay at K1 must recalculate from the stored K1 metadata and match the K1 payload/hash.
- Restatement at K2 must produce the K2 payload and attribute the delta to the purchase revision.
- The overwrite comparator, which has no revision history or archived payload, must fail to reconstruct K1 for this account.

### 9.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Store only the final return number. | Cannot reconstruct positions, flows or attribution; rejected. |
| B | Store a PDF or a rendered report. | Not comparable value-for-value; rejected as the source of truth. |
| C | Store structured canonical payload plus input/code/data metadata. | Reproducible and comparable; recommended. |
| D | Store a full database dump per report. | Heavy; unnecessary if revision history and NAV snapshot are immutable. |

### 9.4 Recommendation

**Option C.** Store the metadata listed in `docs/METHODOLOGY.md` section 10, the canonical payload and its SHA-256. Distinguish:

- **archived retrieval** (always exact, no recalculation);
- **replay** (recalculate and compare; guaranteed for the same engine version and NAV snapshot; `ENGINE_VERSION_MISMATCH` otherwise);
- **restatement** (recalculate with later K and attribute deltas).

The overwrite comparator stores current rows only and must attempt reconstruction from its retained data. It is not allowed to retrieve an archived payload.

### 9.5 What changes in the results

- Replay is a real reconstruction, not a snapshot lookup.
- A later code change can prevent exact replay; the archived payload remains retrievable and the limitation is reported.
- The comparator demonstrates the cost of overwriting: lost prior instruction values, derived units/cash, lineage, reasons and report payload.

**PRD reference:** 9, 10; prompt D-OPEN-07.

---

## 10. D-OPEN-08 — Sensitivity statistics

### 10.1 Ambiguity

The PRD requires median, p95 and threshold shares, but does not state whether these are signed or absolute. If only the signed median is reported, positive and negative errors can cancel and hide the magnitude of reporting sensitivity.

### 10.2 Numerical example

Five backdating errors produce TWR changes of `+10, +5, 0, -5, -10 bp`. The signed median is `0 bp`; the median absolute change is `5 bp`; the p95 absolute change is `10 bp`. Reporting only the signed median would wrongly suggest no sensitivity.

### 10.3 Options

| Option | Description | Consequence |
|---|---|---|
| A | Signed median only. | Cancellation hides magnitude; rejected. |
| B | Absolute median and p95 only. | Hides direction; incomplete. |
| C | Signed median + median absolute + p95 absolute + threshold shares + n. | Complete and honest; recommended. |
| D | Report only the mean. | Outliers and cancellation; rejected. |

### 10.4 Recommendation

**Option C.** For every scenario and measure, report n, median signed change in bp, median absolute change, p95 absolute change, share exceeding each configured threshold, and failed/insufficient counts. State that the correction magnitudes are controlled parameters, not observed real-world error rates.

### 10.5 What changes in the results

- The sensitivity section cannot hide a large absolute effect behind sign cancellation.
- Positive and negative directions are visible alongside magnitude.
- Null and inconclusive results are reported, not dropped.

**PRD reference:** 12.2; prompt D-OPEN-08.

---

## 11. Consolidated approval checklist

Please approve or change the following. A single approval covers all items unless you explicitly reject one.

| # | Item | Recommended answer |
|---|---|---|
| 1 | Simple purchase/redemption posting date | Post on the allotment date; instruction date is audit-only. |
| 2 | SIP dates | Contribution on contribution date; purchase on allotment date; interim cash visible. |
| 3 | Switch dates and atomicity | Sequential source/target NAV dates within 5 calendar days; one atomic group; residual cash credited. |
| 4 | Switch external-flow treatment | Never external; internal only. |
| 5 | Unit precision and mode | 3 dp; ROUND_DOWN for amount-instructed purchase units; ROUND_HALF_UP otherwise. |
| 6 | Amount precision and mode | 2 dp; ROUND_HALF_UP. |
| 7 | NAV precision | As published; store `NUMERIC(20,6)`; never round published NAV. |
| 8 | Residual cash | Record and retain; never discard; report by account/type. |
| 9 | Opening funding | Zero cash/units; explicit CONTRIBUTION; no overdraft. |
| 10 | Same-day order | Explicit deterministic `posting_sequence` per group; no hardcoded universal transaction-type priority; rejected groups post nothing. |
| 11 | Flow signs | Portfolio perspective for TWR/MD; investor perspective for XIRR. |
| 12 | Flow timing | Start of day for TWR and Modified Dietz. |
| 13 | Day count | Calendar days; inclusive `T`; actual/365 for XIRR. |
| 14 | Report boundaries | Inclusive; `V_S` before flows on `S`; `V_E` after flows on `E`. |
| 15 | Stale NAV | Carry forward up to 5 calendar days; flag; fail beyond. |
| 16 | Annualisation | TWR/MD period returns; XIRR annualised; label separately. |
| 17 | XIRR solver | Scan + Newton + bisection; explicit statuses; `NO_ROOT_IN_DOMAIN` distinguished from `NO_ROOT_PROVEN`; no arbitrary root. |
| 18 | Snapshot metadata | Store the metadata and canonical payload/hash in `docs/METHODOLOGY.md` section 10. |
| 19 | Replay limits | Exact for same engine/snapshot; `ENGINE_VERSION_MISMATCH` otherwise; archived retrieval always works. |
| 20 | Comparator | Current-row-only schema; may not retrieve a stored payload; must demonstrate failure. |
| 21 | Sensitivity statistics | Signed median + median absolute + p95 absolute + threshold shares + n. |
| 22 | Pre-registration | Freeze `config/sensitivity.yaml` before the study; no changes after results. |

---

## 12. M0 deliverables and exit-gate checklist

| Deliverable | Status | Location |
|---|---|---|
| BRD with current-process gap | Complete for review | `docs/BRD.md` |
| User stories | Complete for review | `docs/USER_STORIES.md` |
| Data card | Complete for review | `docs/DATA_CARD.md` |
| Methodology with hand-computed fixtures | Complete for review | `docs/METHODOLOGY.md` |
| Decision log | D-017–D-022 recorded; D-023–D-032 approved by Vicky 2026-11-09 with refinements | `DECISIONS.md` |
| Requirements traceability | Complete for review | `docs/REQUIREMENTS_TRACEABILITY.md` |
| Progress log | Complete for review | `docs/PROGRESS.md` |
| M0 design review | Approved with refinements; fixture appendix and NAV contract approved 2026-11-09; M0 exit gate met and formally recorded | `docs/M0_DESIGN_REVIEW.md` |
| Fixture appendix | Expanded to include delayed allotment, same-day sequencing, SIP dates, no-root distinction and replay | `docs/METHODOLOGY.md` |
| FundLens file reconciliation | 86 files reconciled to 85 ranges; 3 out-of-scope IDCW differences; 0 Growth differences | `docs/FUNDLENS_FILE_RECONCILIATION.md` |
| FundLens NAV contract | Option A selected: verified raw-file fallback; no FundLens DB query or volume access | `docs/FUNDLENS_NAV_CONTRACT.md` |
| Jira project and epics | Not created by Vicky's direction; local backlog only | `docs/USER_STORIES.md` |
| Sensitivity pre-registration | Draft, not frozen | `config/sensitivity.yaml` |
| M0 briefing | Complete for review | `docs/briefings/M0.md` |

### 12.1 Exit gate

The M0 gate is met when:

- Vicky has reviewed the complete fixture appendix in `docs/METHODOLOGY.md` and this design review, and approved the fixture suite subject to four final documentation amendments; the amendments are complete and the suite is accepted. **Done 2026-11-09.**
- Vicky has approved the material conventions in section 11. **Done 2026-11-09 with refinements; the four documentation amendments were adopted the same day.** The financial conventions themselves were not changed beyond those clarifications.
- The FundLens NAV contract is accepted under Option A (verified raw-file fallback; no database query). **Approved by Vicky 2026-11-09.**
- The 86-vs-85 raw-file reconciliation is documented with filenames, checksums, date ranges and row-level differences. **Done: `docs/FUNDLENS_FILE_RECONCILIATION.md`.**
- No unresolved conflict between the PRD and this review remains.
- The M0 gate is formally recorded as approved in `docs/PROGRESS.md` and this review; **M0 exit gate met and formally approved on 2026-11-09**. M1 Foundations may begin under the PRD milestone gate; no financial implementation starts before the M1 foundations gate passes.

### 12.2 Blockers and limitations

1. **FundLens live database query intentionally not executed.** Vicky selected Option A: use the verified raw-file fallback and do not query the FundLens PostgreSQL database or access its running database volumes. The contract remains verified from migrations, parser code, raw files and FundLens's audited results. This is a documented limitation, not a pending authorisation.
2. **86 raw files vs 85 registered files — reconciled.** `docs/FUNDLENS_FILE_RECONCILIATION.md` lists all 86 files with range, compressed/uncompressed size, SHA-256, data-line count, scheme count and date span. The duplicate 2006 range differs on exactly three out-of-scope IDCW NAV rows and zero Growth rows; both files are preserved and neither is silently omitted. The earlier 435,745 Direct-Growth count is withdrawn because the scan did not reproduce it.
3. **Jira access not established and not to be used.** Vicky directed that no Jira project be created or claimed. The local backlog is the authoritative record.
4. **No Git repository in the target workspace.** `bitemporal-ledger` is not currently a Git repository. M1 will initialise it and make small logical commits; no remote, push or release will be created without approval.
5. **Python 3.14.10 is installed**, not 3.12. M1 must pin and verify a reproducible Python 3.12 environment; the local 3.14 interpreter is not accepted as evidence that the 3.12 environment works.
6. **Docker daemon is stopped.** PostgreSQL 16 configuration will be prepared in M1, but no PostgreSQL integration test or migration execution may be claimed as passed until the Docker service is running.

---

## 13. Proposed M1 plan after approval

1. Initialise a local Git repository only in this project directory; no remote, push or publication.
2. Add `.gitignore`, `.env.example`, `pyproject.toml`, `Makefile` and Windows `make.ps1`.
3. Pin and verify a reproducible Python 3.12 environment; record the exact interpreter and dependency lock evidence.
4. Add Docker Compose for PostgreSQL 16 on a non-conflicting host port (proposed 5434, because FundLens uses 5433). Do not claim integration tests or migrations passed until Docker is running.
5. Add a versioned migration runner and the first schema migration (schemas, migration table, NAV snapshot tables).
6. Implement the canonical NAV adapter from the verified raw-file fallback and add import validation.
7. Reconcile 86 raw files against 85 registered ranges with filenames, checksums, date ranges and row-level differences; verify the three out-of-scope IDCW differences and no Growth differences.
8. Add CI: lint, unit tests, property tests, integration tests and a clean-database migration check; mark integration tests as not run until Docker is available.
9. Verify idempotent import, checksum, provenance and conflict recording.
10. Record the M1 exit evidence in `docs/PROGRESS.md` and `docs/briefings/M1.md`.

No financial calculation is implemented in M1; the performance engine starts in M5 after the ledger and valuation gates pass. No Jira project will be created.

---

## 14. Decision requested

**The 22 items in section 11 were approved by Vicky on 2026-11-09 with the refinements recorded above.** Vicky subsequently reviewed the complete numerical fixture appendix in `docs/METHODOLOGY.md` and the FundLens NAV contract, approving the contract under **Option A**, and approved the four final documentation amendments on 2026-11-09. After those amendments were completed, **the M0 exit gate was formally recorded as approved on 2026-11-09**; M1 Foundations may begin under the PRD milestone gate.

**M1 Foundations may begin. No portfolio accounting or performance calculation implementation may start before the M1 foundations gate passes.**
