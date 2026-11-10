# Progress Log — bitemporal-ledger

**Project:** `bitemporal-ledger` — Bitemporal Portfolio Accounting & Performance Engine  
**Status:** M0–M9 complete/frozen, M10 v1.0.0 RC (final verification documented)  
**Date:** 2026-11-10

## M0 — Discovery
Approved 2026-11-09 (Vicky). Fixtures F1–F19 and FundLens NAV contract under Option A approved. See `docs/M0_DESIGN_REVIEW.md`.

## M1 — Foundations
Approved 2026-11-09. Migrations/idempotent NAV import established (schema evolved through 007).

## M2 — Generator
Approved 2026-11-09. Seed 20261109, dataset hash `94839c5cb0119c6501f592da2f7fef56ca3f6cbb04e5e49ba4adfaf3308b6cda`.

## M3 — Ledger and corrections
Approved 2026-11-09. Immutable bitemporal ledger, corrections/rejections, no-overlap guarantees.

## M4 — Positions and valuation
Approved 2026-11-09. As-of positions/valuation, stale NAV handling.

## M5 — Performance engine
Approved 2026-11-09. TWR/Modified Dietz/XIRR with fixtures and independent reference.

## M6 — Snapshots and restatement
Implemented 2026-11-09. Replay vs restatement, comparator evidence (PRD §2.2 scenario).

## M7 — Invariants and pipeline
Implemented 2026-11-09. Deterministic `make reproduce` pipeline; prior double-run hash `ac6257e2…` recorded.

## M8 — Sensitivity study (FROZEN)
Implemented 2026-11-09. Frozen config `config/sensitivity.yaml` SHA-256 `93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01` (preserved). 11,436 detail rows; E8 complete; E9 654/1,040 solved (386 excluded). **No retuning/changes.**

## M9 — Dashboard and SQL (FROZEN, visually accepted)
**Visually accepted and frozen 2026-11-10 (Vicky).** PBIP PostgreSQL-only (`dashboard/PortfolioReport/Workbook.pbip`, 4 pages). Final Page 4 E9: drawdown-quintile bar chart + summary table (654 solved, deterministic quintiles, SQL-validated). Screenshots in `docs/screenshots/`. Desktop render/interaction validation manual. No further visual iterations. See `docs/M9_STATUS.md`, `docs/DASHBOARD_VALIDATION_SQL.md`.

## M10 — Release

### Status
**v1.0.0 Release Candidate (2026-11-10).** No push/publish/tag/release. No further feature development.

### Verification executed during M10 (2026-11-09/10, recorded)
| Check | Result (recorded) |
|---|---|
| Clean rebuild | migrations + import + generate `94839c5c…` + ledger + double reproduce `ac6257e2…` |
| Full suite | 75 passed (Docker PG16 + CPython 3.12) |
| Ruff | Clean |
| Checksum tamper | Exercised; regression test `tests/integration/test_migration_checksum.py` |
| Power BI / CI | PBIP frozen, screenshots present; Desktop manual; CI remote not performed |
| Sensitivity | 11,436 rows; E8 complete, E9 n=654 |

### Final verification pass (2026-11-10)
| Check | Evidence | Status |
|---|---|---|
| NAV import & idempotency | Snapshot 3 `amfi_nav_m1` 1,811,709 obs, 0 duplicates (DB) | State verified; source rerun not executed |
| Migrations & integrity | 7 applied, checksums match `sql/migrations/*.sql` | Verified |
| Checksum-tamper test | Test present; prior evidence recorded | Not re-executed |
| Full tests & Ruff | — | Not executed (deps/env unavailable) |
| Two clean `make reproduce` runs (matching hashes) | Prior `ac6257e2…` recorded | Not executed |
| RESULTS/README/traceability/docs audit | Updated | Completed |
| Git working tree & secret scan | No commits/remotes; untracked; no secrets found (local dev DSNs noted) | Completed |
| M9/M8 freeze | Dashboard frozen, screenshots preserved, M8 `93fb380b…` preserved | Recorded |

### Blockers / outstanding
- Fresh RC rerun in prepared env: tests, Ruff, tamper test, NAV idempotency rerun, **two clean reproduce runs with matching hashes**. Manual Desktop validation. CI remote not performed. **No push/tag/release without Vicky’s explicit approval.**

Canonical RC report: `docs/V1_0_0_RC_FINAL_REPORT.md`.
