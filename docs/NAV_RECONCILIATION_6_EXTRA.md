# NAV Observation Count Reconciliation (1,811,703 → 1,811,709)

**Date:** 2026-11-10  
**Investigator:** Automated reconciliation against DB and `docs/FUNDLENS_FILE_RECONCILIATION.md`  
**Rule:** Do **not** silently remove or add observations. Document authoritative counts.

## Summary
| Count | Source | Notes |
|---|---|---|
| **1,811,703** | Canonical AMFI NAV import (raw files) | Earlier M1-reported count; corresponds to observations sourced from the 85 canonical raw-file ranges (excluding the duplicate variant `f09f872ef68e` when canonical selection applies). |
| **+6** | Seed/test observations inserted into `core.nav_observation` | `source_file_sha256` values `m4-seed`, `m6-seed`, `test-seed`. **Not from canonical AMFI gzip files.** |
| **1,811,709** | Current `core.nav_observation` total | Verified via DB query. |

**Authoritative canonical AMFI import count:** **1,811,703** (85 distinct source files by SHA-256 from raw AMFI ranges; duplicate range handled per `docs/FUNDLENS_FILE_RECONCILIATION.md`).  
**Authoritative total in DB (as-is):** **1,811,709** (includes 6 seed/test observations).

## Exact six additional observations

Queried from `core.nav_observation` (snapshot_id=3):

| nav_observation_id | nav_snapshot_id | amfi_scheme_code | nav_date | nav | option_type | source_file_sha256 | ingested_at |
|---|---|---|---|---|---|---|---|
| 10178554 | 3 | 100001 | 2024-01-05 | 10.000000 | GROWTH | m4-seed | 2026-11-09 21:12:45.22783+00 |
| 10178555 | 3 | 100002 | 2024-01-05 | 20.000000 | GROWTH | m4-seed | 2026-11-09 21:12:45.22783+00 |
| 10178558 | 3 | 100001 | 2026-01-10 | 50.000000 | GROWTH | m6-seed | 2026-11-09 21:12:45.710495+00 |
| 10178559 | 3 | 100001 | 2026-01-31 | 52.000000 | GROWTH | m6-seed | 2026-11-09 21:12:45.710495+00 |
| 10174702 | 3 | 100003 | 2024-01-06 | 30.000000 | GROWTH | test-seed | 2026-11-09 15:49:16.367638+00 |
| 10174703 | 3 | 100004 | 2024-01-11 | 25.000000 | GROWTH | test-seed | 2026-11-09 15:49:16.367638+00 |

- **Source files (by SHA-256):** `m4-seed` (2 rows), `m6-seed` (2 rows), `test-seed` (2 rows).  
- **Scheme codes:** 100001, 100002, 100003, 100004.  
- **Dates:** 2024-01-05, 2024-01-06, 2024-01-11, 2026-01-10, 2026-01-31.

## Reconciliation against approved 85 canonical raw-file ranges
- `docs/FUNDLENS_FILE_RECONCILIATION.md` documents 86 `.gz` files, 85 distinct date ranges, 1 duplicate range (`20060630–20060927`: `7101b03da5bb` vs `f09f872ef68e`). Duplicate IDCW differences excluded; **Direct-Growth differences 0** between duplicates. Canonical selection per documented rule (lexicographically smaller filename SHA-256 prefix) uses `7101b03da5bb`; `f09f872ef68e` not treated as canonical for Growth scope.
- DB contains **85** distinct `source_file_sha256` values that correspond to canonical/raw AMFI files (all match ranges/hashes documented) with total **1,811,703** rows. It also contains **3** non-canonical seed SHAs with **6** rows total.  
- **Conclusion:** The +6 are seed/test observations not from canonical raw-file ranges. They are explicitly identified above; no observations were silently removed or added. Authoritative canonical count remains **1,811,703** (85 ranges). Total DB count **1,811,709** includes seed/test rows as present.

**No financial methodology, M8 results, or frozen dashboard visuals modified.**
