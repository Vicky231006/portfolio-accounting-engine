# M3 Design Review — Ledger and Corrections

| Field | Value |
|---|---|
| Milestone | M3 — Ledger and Corrections (PRD §6.3, §9; FR-B3, FR-B4) |
| Status | Design for review (authorised by Vicky 2026-11-09) |
| Date | 2026-11-09 |

---

## Purpose

M3 implements the immutable transaction revision ledger and the bitemporal correction engine. It consumes the M2 generator's logical records **without modifying them** and produces a ledger that can answer "what was effective then, as known at K?" for every accepted revision. It does not value positions or calculate returns — that is M4.

M2's generator fields read in full before this design: `txn_group_id`, `account_id`, `investor_id`, `txn_type`, `instruction_date`, `effective_date`, `allotment_date`, `posting_sequence`, `scheme_code`, `source_scheme_code`, `target_scheme_code`, `amount_instructed` (decimal-string), `units_instructed` (decimal-string), `recorded_at` (UTC ISO), `generator_estimated_units`/`generator_estimated_proceeds` (ignored), `data_class`/`synthetic_label`. Correction intents carry `correction_type`, `reason_code`, `reason_note`, proposed fields, `recorded_at` and `actor_id`.

---

## 1. Revision-table model

Five tables, all created in `sql/migrations/004_ledger_corrections.sql`:

| Table | Role | Key columns |
|---|---|---|
| `core.investor` | Synthetic master (M2) | `investor_id PK, synthetic_ref UNIQUE, display_name, data_class, synthetic_label` |
| `core.account` (extended) | Synthetic master (M2) | adds `investor_id FK, display_name, account_status, currency, opened_date, closed_date, data_class, synthetic_label` to the M1 table (all nullable-by-default additions preserve the M1 rows) |
| `core.txn_business` | Stable business identity | `txn_group_id TEXT PK, account_id FK, investor_id FK, data_class, synthetic_label` |
| `core.txn_revision` | **Immutable append-only history** | one row per accepted version; full instruction snapshot + lineage (`prev_revision_id`, `correction_group_id`, `revision_kind`, `recorded_at`, `system_period`) |
| `core.txn_version_current` | Rebuildable projection | `txn_group_id PK, latest_revision_id FK, instruction snapshot, is_voided` |
| `core.correction_group` | Atomic correction unit | `correction_group_id PK, correction_type, reason_code, reason_note, source_ref, actor_id, recorded_at, status, applied_revision_id` |
| `core.correction_rejection` | Audit of refused corrections | `correction_group_id (proposed), txn_group_id, expected_prior_revision_id, correction_type, reason_code, attempted_recorded_at, actor_id, details JSONB` |

The business table holds **identity only**; every economic fact lives in revisions, so a correction never updates the business row. The projection (`txn_version_current`) is the only mutable ledger table and is documented as not immutable (D-005).

**Revision line:** `revision_no` (1, 2, …) per `txn_group_id` with `UNIQUE(txn_group_id, revision_no)`; `prev_revision_id` points at the prior revision (NULL for the original). A `VOID` is a new revision whose `revision_kind = 'VOID'` and `revision_status = 'VOIDED'`; its instruction fields copy the prior revision so the history shows exactly what was voided. A historical query at K2 sees the `VOID` revision and excludes the transaction; at K1 it sees the prior `ACCEPTED` revision and includes it.

**Correction group:** one group per correction operation, containing exactly one new revision in M3. A group with more than one revision is not generated in M3; the schema allows it (`correction_group_id` is not unique on revisions). The group, the new revision and the system-period close happen in one database transaction.

## 2. Valid time and system (knowledge) time

- **Valid (effective) time:** `effective_date` (and derived `allotment_date` / `source_nav_date` / `target_allotment_date`) on the revision. It answers "when did this economically apply?" and is the only date that drives posting order.
- **System (knowledge) time:** `recorded_at` (simulated UTC, from M2; corrections carry their own later `recorded_at`) and the derived `system_period TSTZRANGE`. It answers "when did the system know this version?" The pair `(effective_date, recorded_at)` is never conflated (PRD §6).
- **As-of read:** the visible revision for `known_as_of = K` is the revision with the greatest `recorded_at <= K` for that `txn_group_id` (`ORDER BY revision_no DESC LIMIT 1`), excluding `VOIDED` revisions. This is implemented in `LedgerService.get_as_of` with SQL and is the M3 read contract that M4 will reuse.

Wall-clock (`now()`) is used only for audit columns (`created_at`, `applied_at`), never as a logical `recorded_at`.

## 3. Current-version projection rebuild

`txn_version_current` always shows the latest revision per business transaction (the unbounded-K view). It is maintained by `sync_projection_for_txn(txn_group_id)` after every accepted correction and reproducible from scratch by `rebuild_all_projections()`:

```sql
INSERT INTO core.txn_version_current (...)
SELECT ... FROM (
  SELECT DISTINCT ON (txn_group_id) * FROM core.txn_revision
  ORDER BY txn_group_id, revision_no DESC
) latest ON CONFLICT (txn_group_id) DO UPDATE ...
```

The projection is **not** the source of truth; deleting and rebuilding it from `txn_revision` yields the identical table. Tests assert exactly that after applying corrections.

## 4. Atomic correction application

`LedgerService.apply_correction(request)` runs in **one transaction**:

1. Validate the request (target exists, `expected_prior_revision_id` matches the current revision or is NULL, `recorded_at` strictly greater than the prior revision's, correction type consistent with the proposed fields, allotment dates resolvable within 5 days against the M1 snapshot). Failure → insert one `core.correction_rejection` row in a separate statement, return `rejected` with an explicit `reason_code`, and **commit nothing else**.
2. Compute the candidate instruction snapshot (REPLACE changes amount/units/effective date; REVERSE_AND_REPLACE changes scheme(s); VOID copies the prior snapshot) and recompute derived units/proceeds via the allotment rule below.
3. **Downstream validity:** build the candidate full set (all `txn_version_current` revisions with this target replaced by the candidate) and replay cash/units in `(posting_date, posting_sequence, txn_group_id)` order per account. The first step that would make cash or units negative fails the whole group with `NEGATIVE_UNITS_DOWNSTREAM` or `INSUFFICIENT_CASH_DOWNSTREAM`, and the candidate is rejected with no partial write.
4. On success: insert `correction_group (APPLIED)`, insert the new revision with `system_period = [recorded_at, +∞)`, close the prior revision (`system_period = [prior_recorded_at, recorded_at)`), and `INSERT ... ON CONFLICT DO UPDATE` the projection row.

Because the whole sequence is one database transaction, any exception (including a GiST violation, which we do not expect in correct operation) rolls everything back; the linkage is covered by an explicit rollback test.

## 5. No-overlap enforcement (GiST exclusion constraint)

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE core.txn_revision
  ADD CONSTRAINT ex_txn_revision_no_overlap
  EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&);
```

`btree_gist` provides the equality operator on `TEXT` inside the GiST index. The constraint states: *for one `txn_group_id`, two revisions can never have overlapping system periods — no matter what the application does.* Overlapping insertions fail with PostgreSQL error `23P01` even if the service had a bug. A dedicated test attempts a raw overlapping insert and asserts the constraint error. The service's job is simply to close the prior period to `[prior_recorded_at, recorded_at)` before inserting the new `[recorded_at, +∞)` row, which is what makes the periods adjacent rather than overlapping.

## 6. M2 record → ledger mapping (ingestion)

`LedgerService.ingest_m2_output(investors_path, accounts_path, transactions_path, snapshot_id)`:

- **Investors/accounts:** upserted by `synthetic_ref` (`ON CONFLICT DO NOTHING`); investors before accounts because of the FK. Account `account_id`/`investor_id` from M2 are the generated counters; the tables use the same numbers via `BIGSERIAL` only if the row does not exist — ingestion inserts with the M2 IDs explicitly so cross-references are stable and re-ingestion is a no-op (idempotent).
- **Transactions:** each M2 record becomes `txn_business` + original `txn_revision` (`revision_no = 1`, `revision_kind = 'ORIGINAL'`, `system_period = [recorded_at, +∞)`, `correction_group_id = NULL`). `generator_estimated_*` fields are **never read** (M1 keys `data_class`/`synthetic_label` are preserved for labelling). `txn_group_id` already present → the record is skipped (idempotent re-ingest).
- **Correction intents:** **not ingested.** They remain a separate file. Tests and future drivers convert an intent into a `CorrectionRequest` and call `apply_correction`; the engine validates each target freshly (D-039). An intent is never treated as an accepted correction.
- **Scheme validation on ingest:** scheme codes must exist in the snapshot; amounts/units are parsed as `Decimal` (never float) and must be positive.

## 7. Linked-leg semantics (SIP / SWITCH) and the allotment rule

- `SIP_INSTALMENT`: the contribution leg posts on `effective_date`; the linked purchase leg posts on `allotment_date` (first NAV date on or after `effective_date`, ≤ 5 days). Whole group rejected if the purchase cannot be priced within 5 days (D-024, METHODOLOGY §2.2).
- `SWITCH`: one group; the source redemption posts on `source_nav_date`, the target purchase on `target_allotment_date` (each ≤ 5 days after the previous), residual cash credited, both legs succeed or fail together. Never an external flow.
- Derived fields (recomputed atomically per D-020):

| Type | Instruction | Derived (units, proceeds) |
|---|---|---|
| PURCHASE | `amount` | `units = ROUND_DOWN(amount/NAV, 3)`; `actual_cash = ROUND_HALF_UP(units×NAV, 2)` |
| REDEMPTION | `units` | `proceeds = ROUND_HALF_UP(units×NAV, 2)` |
| SIP_INSTALMENT | `amount` | contribution + purchase per PURCHASE row |
| SWITCH | `units` out | `proceeds = ROUND_HALF_UP(units_out×NAV_src, 2)`; `units_tgt = ROUND_DOWN(proceeds/NAV_tgt, 3)`; residual `proceeds − ROUND_HALF_UP(units_tgt×NAV_tgt, 2)` ≥ 0 |

NAV prices come from `core.nav_observation` (snapshot-parameterised). These are **posting** computations, not portfolio valuation: no position is valued at an arbitrary date and no return is calculated (M4). Negative downstream cash/units are rejected (§4.3); `posting_sequence` order is preserved (D-027) and deterministic correction ordering follows `(recorded_at, correction_group_id)` (§9).

## 8. Testing plan (FR-B3/B4 acceptance; all against the real database)

| Requirement | Test |
|---|---|
| Original creation | ingest creates business + revision 1 + projection; M2 records unchanged |
| Replacement / Void / Reverse-and-replace | `apply_correction` per type; current view changes; prior revision still readable at K1 |
| K1/K2 reconstruction | query at K1 returns the original; at K2 returns the correction; repeated queries at the same K are identical |
| Overlapping system periods | raw overlapping insert raises the GiST exclusion error `23P01` |
| Invalid references | unknown target / mismatched prior revision / non-increasing `recorded_at` → `INVALID_REFERENCE` / `NON_MONOTONIC_RECORDED_AT` |
| Negative downstream units | redeeming more units than held (via a correction) → `NEGATIVE_UNITS_DOWNSTREAM`, ledger unchanged |
| Insufficient cash | withdrawing more than cash (via a correction) → `INSUFFICIENT_CASH_DOWNSTREAM` |
| Atomic rollback | a correction engineered to fail mid-apply leaves no group, no revision and no projection change |
| Deterministic ordering | two corrections at the same `recorded_at` apply in `correction_group_id` order with identical outcomes |
| All test fixtures use **hand-computed** expected amounts (METHODOLOGY §2–§3), not values derived by the production code path. |

## 9. Unresolved assumptions (to be decided in M3 or by Vicky)

1. **Correction-group granularity:** M3 groups one correction operation per `correction_group_id` (one new revision). Bulk corrections spanning several `txn_group_id`s are representable but not implemented in M3.
2. **`source_nav_date`/`target_allotment_date` for SWITCH in M2 input:** M2 emits one `allotment_date` (= `effective_date`); ingestion sets both switch dates to it. Split-date switch corrections compute the two dates independently.
3. **Correction ordering ties:** two corrections with identical `recorded_at` on the *same* `txn_group_id` are rejected as `NON_MONOTONIC_RECORDED_AT` (strict increase required). Ordering by `(recorded_at, correction_group_id)` applies across different transactions and to the rejection log.
4. **Ingestion batch provenance:** the M2 dataset hash is recorded in the ingestion result and CLI output, not in a dedicated ledger table in M3. A `pipeline_run`-style table can be added in M7 if needed.
5. **`NO_ROOT`-style failures are out of scope for M3** (M5). The only M3 failure vocabulary is the correction `reason_code` set in §4.

## 10. Non-goals (explicit)

No valuation (`positions`/`valuation`), no TWR/Modified Dietz/XIRR, no report snapshots/restatement, no comparator, no dashboard. The M4 read contract (`get_as_of`) is the only query surface M3 guarantees.
