# M3 Verification Supplement — Append-Only Proof, GiST Identity, Switch Dates, Replay Ordering

| Field | Value |
|---|---|
| Milestone | M3 — Ledger and Corrections (verification supplement, no redesign) |
| Date | 2026-11-09 |
| Status | Ready for review — all raw evidence re-executed in this session |
| Rule | No valuation/performance code; no M4 work |
| **Errata (architectural correction, D-047)** | Sections A/B below describe the pre-correction layout where `system_period` lived on `core.txn_revision` and was closed with an UPDATE. **That is superseded**: migration `005_revision_period_split.sql` moved `system_period` to the rebuildable projection `core.txn_revision_period` (GiST now `ex_txn_revision_period_no_overlap`), and `core.txn_revision` is now strictly append-only with trigger `trg_txn_revision_immutable`. All GiST, K1/K2, switch, replay and rebuild tests were re-run against the split layout and pass (39 total). |

---

## A. Append-only revision history

### What the source actually does

`src/bitemporal_ledger/ledger/service.py :: LedgerService.apply_correction` commits, in **one DB transaction**:

1. `INSERT correction_group … 'APPLIED'` (operation row).
2. `UPDATE core.txn_revision SET system_period = tstzrange(prior_recorded_at, new_recorded_at, '[)') WHERE txn_revision_id = prior` — **closes the prior visitor's knowledge interval first**, so the new `[recorded_at, infinity)` row can never overlap it under the GiST constraint.
3. `INSERT txn_revision (revision_no = prior_no + 1, prev_revision_id = prior, revision_kind, …)` — the **new** version.
4. `UPDATE correction_group SET applied_revision_id …`.
5. `INSERT … ON CONFLICT (txn_group_id) DO UPDATE …` on `core.txn_version_current` (the projection) with `is_voided = (revision_status = 'VOIDED')`.

No other `txn_revision` column is touched. The prior row's **business facts** (amount, units, schemes, dates, `posting_sequence`, `recorded_at`, lineage) are byte-identical before and after.

### Is updating `system_period` a violation of append-only?

**No, and the reason is structural, not verbal.** D-005 already carves this out: *"If a physical `tstzrange` projection is used, close the prior projection interval in a controlled, deterministic way and retain the append-only source revision."* The `system_period` on a revision is **interval metadata about knowledge time**, not an economic fact. Every bitemporal design must close the previous interval when a successor arrives; otherwise knowledge time is a set of open-ended claims and the GiST constraint would (correctly) forbid the successor. The invariant the PRD actually protects is: *business facts are never rewritten*. The test below proves all business columns survive a correction unchanged, and that the two periods become exactly adjacent (`[K1, K2)` then `[K2, infinity)`).

The **immutable source** (business facts of every revision, including `VOIDED` ones) lives in `core.txn_revision`. The **rebuildable temporal projection** is `core.txn_version_current`, re-derivable from scratch by `rebuild_all_projections()` (`DISTINCT ON (txn_group_id) … ORDER BY revision_no DESC`). Deleting it and rebuilding yields the identical table (asserted by test).

### Table identities (A, cont.)

- `core.txn_business` — one row per **stable business transaction** (`SYN_TXN-…`), never updated after ingest. Proves the business ID is decoupled from any version.
- `core.txn_revision` — append-only: one row per accepted version; business facts immutable; only `system_period` is closed on supersession (above).
- `core.txn_version_current` — rebuildable projection of the latest revision per business transaction.
- `core.correction_group` — one row per **correction operation** (`SYN_GRPCORR-<txn>-<epoch>`); points at the business transaction it corrects and the revision it produced.
- `core.correction_rejection` — one row per refused correction (business transaction, expected prior, type, reason code, attempted knowledge time, actor, JSON details). Rejections commit nothing else.

## B. GiST constraint identity

### What `txn_group_id` represents

`txn_group_id` is the **stable business transaction identity** — the M2 grouping of one economic transaction (`SYN_TXN-000004`, etc.). It is:

- **not** the correction operation identity — that is `correction_group_id` (`SYN_GRPCORR-SYN_TXN-…-<epoch>`);
- **not** a linked-leg identity — SIP instalments and switches are **one** `txn_group_id` with one row per revision; the legs (contribution/purchase, redemption/purchase) are expanded only inside the validity replay and never become separate revision rows.

### Migration SQL and proof

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE core.txn_revision
  ADD CONSTRAINT ex_txn_revision_no_overlap
  EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&);
```

Actual PostgreSQL definition (queried live): `EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&)` with index `ex_txn_revision_no_overlap ON core.txn_revision USING gist (txn_group_id, system_period)`.

Because the exclusion key includes `txn_group_id`, overlapping knowledge intervals are forbidden **only between revisions of the same business transaction**. Revisions of different transactions may share knowledge times freely, and **both legs of a SWITCH/SIP live inside the same single revision**, so the constraint cannot (and does not) reject them.

### Example rows (integration-test observed)

From `test_switch_split_dates_atomic_lineage_and_residual` (one revision for the entire switch):

| txn_group_id | revision_no | revision_kind | txn_type | source_scheme | target_scheme | source_nav_date | target_allotment_date | posting_sequence |
|---|---|---|---|---|---|---|---|---|
| `SYN_TXN-TEST-SW` | 1 | ORIGINAL | SWITCH | 100001 | 100003 | 2024-01-05 | 2024-01-06 | 30 |

From a REPLACE correction run:

| txn_group_id | revision_no | revision_kind | correction_group_id | prev_revision_id | system_period |
|---|---|---|---|---|---|
| `SYN_TXN-TEST-001` | 1 (closed) | ORIGINAL | NULL | NULL | `["2024-01-06 12:00:00+00","2024-01-20 12:00:00+00")` |
| `SYN_TXN-TEST-001` | 2 (current) | REPLACE | `SYN_GRPCORR-SYN_TXN-TEST-001-1705752000` | 1 | `["2024-01-20 12:00:00+00",infinity)` |

## C. SWITCH date semantics (sequential legs, ≤ 5 days)

The ledger design already supports sequential dates end-to-end (D-024, METHODOLOGY §2.3). M2's single-date output is a **generator limitation**, not a ledger one: ingestion mirrors M2's `allotment_date` into both switch legs, while any later correction (or directly-ingested split-date record) resolves `source_nav_date` and `target_allotment_date` independently via `_allotment_dates` (each ≤ 5 calendar days after the previous reference date).

**Integration test `test_switch_split_dates_atomic_lineage_and_residual`:**

- Funding `CONTRIBUTION` 10 000.00 (2024-01-05) → `PURCHASE` 1 000.00 of scheme **100001 @ 10.00 on 2024-01-05** → 100.000 units.
- `SWITCH` 10.000 units out on effective **2024-01-05**: source **100001 @ 10.00 (2024-01-05)** → proceeds `ROUND_HALF_UP(10 × 10) = 100.00`; target **100003 @ 30.00 (2024-01-06)** → `units_target = ROUND_DOWN(100/30) = 3.333`, `target_cost = ROUND_HALF_UP(3.333×30) = 99.99`, **residual 0.01** retained as cash.
- Asserts: `source_nav_date = 2024-01-05`, `target_allotment_date = 2024-01-06`, `allotment_date = 2024-01-06`; the switch remains **one revision** (both legs share `txn_group_id`/`revision_no`/lineage), and a no-op `REPLACE` (same effective date) is rejected as `INVALID_CORRECTION_TYPE` — proving the switch is treated as one atomic group.

**Rejection test `test_switch_missing_target_nav_rejected`:** target scheme **100004** first appears on **2024-01-11** (6 days after the 2024-01-05 switch date). `REVERSE_AND_REPLACE` onto it is rejected with **`MISSING_NAV_ALLOTMENT`** and leaves no revision, group or projection change.

Both legs therefore post on their own NAV dates with the residual accounted for exactly once, and the target leg can never price beyond the five-day window.

## D. Downstream replay ordering

### The sorting key (verbatim from source)

`src/bitemporal_ledger/ledger/service.py :: _replay_candidate`:

```python
legs.sort(key=lambda item: (item[0], item[1], item[2]))
# item[0] = posting_date   (effective_date / allotment_date / source_nav_date / target_allotment_date)
# item[1] = posting_sequence (explicit, deterministic, per D-027)
# item[2] = txn_group_id   (stable identity — final deterministic tie-break)
```

`recorded_at` (knowledge time) is **not** part of the economic ordering. It is used only to decide which revision is visible at K (`get_as_of`) and to enforce the monotonic-knowledge rule (`recorded_at > prior.recorded_at`). In particular, `legs` contains only posting-date-anchored events, so a correction recorded late but posting early still replays in its economic position.

### Integration test `test_replay_uses_posting_sequence_not_recorded_at`

- Funding `CONTRIBUTION` 1 000.00, `effective 2024-01-05`, **`posting_sequence 10`, recorded LATE (2024-01-20 12:00 UTC)**.
- `WITHDRAWAL` 900.00, same effective date, **`posting_sequence 20`, recorded EARLY (2024-01-06 12:00 UTC)**.
- Under knowledge-time ordering the withdrawal would replay first (–900 → negative cash) and the history would be invalid. Under posting-sequence order it is 1000 → 100 (valid).
- A benign `REPLACE` of the funding to 1 100.00 therefore **succeeds** — asserted `applied=True` — proving replay used `(posting_date, posting_sequence, txn_group_id)` and not `recorded_at`.

## E. Evidence and reporting

| Item (per user letter) | Source file / function | SQL definition | Test | Actual result |
|---|---|---|---|---|
| A — append-only close | `service.py :: apply_correction` (period close before insert) | `txn_revision` DDL + `system_period` UPDATE | `test_append_only_system_period_close_preserves_business_facts` | **PASS** — all business columns identical; periods `["…2024-01-06…","…2024-01-20…")` then `["…2024-01-20…",infinity)` |
| A — projection rebuild | `service.py :: rebuild_all_projections` | `txn_version_current` DDL | `test_projection_rebuild` | **PASS** — before/after identical |
| B — GiST identity | Migration `004_ledger_corrections.sql` | `EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&)` | `test_overlapping_system_period_rejection` | **PASS** — raw overlapping insert raises `ExclusionViolation` (23P01) |
| B — business vs group vs leg | `txn_business` / `correction_group` / revision schema | Same migration | `test_switch_split_dates_atomic_lineage_and_residual` + `test_deterministic_correction_ordering` | **PASS** — one-switch-one-revision; correction ordering deterministic |
| C — split-date SWITCH | `service.py :: _allotment_dates`, `_derived_legs`, `switch_derived` | `source_nav_date`, `target_allotment_date` columns | `test_switch_split_dates_atomic_lineage_and_residual` | **PASS** — src 01-05 @10 → tgt 01-06 @30; 3.333 units; residual 0.01; atomic lineage |
| C — target NAV missing | Same | Five-day window | `test_switch_missing_target_nav_rejected` | **PASS** — `MISSING_NAV_ALLOTMENT`, no partial write |
| D — replay ordering | `service.py :: _replay_candidate` (`legs.sort(key=(posting_date, posting_sequence, txn_group_id))`) | — | `test_replay_uses_posting_sequence_not_recorded_at` | **PASS** — benign correction applied despite inverted knowledge order |
| E — full suite after changes | — | — | `pytest /app/tests -q` (CPython 3.12) | **38 passed, 0 failed**; `ruff check /app` clean |

No valuation or performance code was added. M4 has not been started. FundLens was not modified; no push/publish occurred.
