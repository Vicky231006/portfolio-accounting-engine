# NAV Observation Count Reconciliation and Isolation (1,811,703 canonical / 6 fixtures)

**Date:** 2026-11-10  
**Investigator:** DB/file reconciliation (automated) + hygiene correction (2026-11-10)  
**Rule:** Do **not** silently remove or add observations. Preserve test coverage and document separation. FundLens not modified.

## Summary
| Count | Scope | Notes |
|---|---|---|
| **1,811,703** | Canonical AMFI NAV import (approved 85 raw-file ranges) | `core.nav_snapshot` **id 3** `amfi_nav_m1` (schema `amfi_raw_v1`, canonical source ref `c6beb9fb…173e6`), **row_count 1,811,703**, range **2006-04-02–2026-11-06**. 85 distinct canonical source-file SHAs; duplicate range handled per `docs/FUNDLENS_FILE_RECONCILIATION.md` (canonical selection used; Growth-only identical). |
| **6** | Test/fixture seed observations (isolated) | `core.nav_snapshot` **id 4** `test_fixture_nav_seeds` (`schema_version=test_fixture_v1`), **row_count 6**, range **2024-01-05–2026-01-31**. **Not** from canonical AMFI gzip files. |
| **1,811,709** | Total observations (DB-wide, both snapshots) | 1,811,703 (snapshot 3) + 6 (snapshot 4). No duplicates added/removed. |

**Earlier M1 reported count:** 1,811,703 (canonical). **M10 observed:** 1,811,709 total due to 6 seed/test rows previously co-located in snapshot 3 — now **isolated** into snapshot 4.

## Exact six fixture observations (preserved, clearly labelled)

Moved from `core.nav_snapshot` 3 (`amfi_nav_m1`) to `core.nav_snapshot` 4 (`test_fixture_nav_seeds`):

| nav_observation_id | amfi_scheme_code | nav_date | nav | option_type | source_file_sha256 | ingested_at (original) |
|---|---|---|---|---|---|---|
| 10178554 | 100001 | 2024-01-05 | 10.000000 | GROWTH | `m4-seed` | 2026-11-09 21:12:45.22783+00 |
| 10178555 | 100002 | 2024-01-05 | 20.000000 | GROWTH | `m4-seed` | 2026-11-09 21:12:45.22783+00 |
| 10178558 | 100001 | 2026-01-10 | 50.000000 | GROWTH | `m6-seed` | 2026-11-09 21:12:45.710495+00 |
| 10178559 | 100001 | 2026-01-31 | 52.000000 | GROWTH | `m6-seed` | 2026-11-09 21:12:45.710495+00 |
| 10174702 | 100003 | 2024-01-06 | 30.000000 | GROWTH | `test-seed` | 2026-11-09 15:49:16.367638+00 |
| 10174703 | 100004 | 2024-01-11 | 25.000000 | GROWTH | `test-seed` | 2026-11-09 15:49:16.367638+00 |

- **Source labels:** `m4-seed` (2), `m6-seed` (2), `test-seed` (2). **Schemes:** 100001–100004. **Dates:** 2024-01-05, 2024-01-06, 2024-01-11, 2026-01-10, 2026-01-31.

## Separation performed (DB hygiene, 2026-11-10)
- Created **separate fixture snapshot** `core.nav_snapshot` id **4** `test_fixture_nav_seeds` (clearly labelled, `test_fixture_v1`).
- **Moved** the 6 identified rows from snapshot 3 to snapshot 4 (no deletes, no additions, no value changes).
- **Updated canonical snapshot metadata:** snapshot 3 `row_count` set to **1,811,703** with canonical min/max/date range preserved; source ref remains canonical AMFI file hash.
- **Verification:** snapshot 3 = 1,811,703 rows (canonical 85 SHAs only); snapshot 4 = 6 rows (seed labels only); DB total 1,811,709; 0 duplicate `(snapshot,scheme,date)` keys. Existing `core.report_snapshot` records (ids 1–2, `nav_snapshot_id=3`) unchanged.

## Test coverage & provenance
- Integration tests seed fixture NAV rows with labels `test-seed`/`m4-seed`/`m6-seed` (`tests/integration/test_ledger_corrections.py`, `test_positions.py`, `test_snapshots.py`) as **test fixtures** (not canonical AMFI). Isolation preserves these fixtures in a dedicated snapshot/label space in the populated DB and documents provenance; tests remain responsible for seeding/using appropriate fixture data per their setup.
- **Canonical AMFI snapshot (id 3)** contains **exactly 1,811,703 observations from the approved 85 source-file ranges** (reconciled against `docs/FUNDLENS_FILE_RECONCILIATION.md`).

**No financial methodology, M8 results, or frozen dashboard visuals modified. FundLens not modified.**
