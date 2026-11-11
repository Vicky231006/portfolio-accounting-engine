# v1.0.0 Release-Candidate — Final Report

> **SUPERSEDED (2026-11-11).** This document records the release-candidate
> verification of 2026-11-10 and is retained as historical evidence. It is
> **not** the current release status. The final verified v1.0.0 report is
> [`docs/V1_0_0_FINAL_REPORT.md`](V1_0_0_FINAL_REPORT.md).

**Date:** 2026-11-10  
**Status:** **Release candidate (v1.0.0 RC)** — evidence-based, with explicit limitations. **No push, no publish, no remote tag, no GitHub release created** (and none must be created without Vicky’s explicit approval).  
**Scope:** M0–M10 per PRD v2.0. **Dashboard frozen (M9 visually accepted by Vicky, 2026-11-10); M8 sensitivity frozen. No further feature development and no financial/methodology/M8/dashboard-visual changes.**

## 1. Executive summary
- bitemporal portfolio accounting/performance engine (synthetic accounts/transactions/corrections; real AMFI NAV inputs) delivered across M0–M10 with PostgreSQL-only PBIP dashboard (4 pages). E9 presented as **drawdown-quintile bar chart** (final, accepted alternative to scatter).
- **Verified in this session (DB/file-level):** NAV snapshot/state and idempotency indicators, migration inventory/checksum integrity vs files, deterministic E9 quintile marts (654 solved, per-band independently validated), dashboard artifacts/screenshots present, M8 config hash preserved, git working tree and secret scan, documentation/traceability audit.
- **Not executed in this environment (cannot be claimed as re-verified now):** full pytest suite and Ruff (deps not installed, Python 3.14 present vs project 3.12), migration checksum-tamper regression test run, NAV import idempotency rerun from source, **two clean `make reproduce` runs from empty DB with matching logical hashes**, Power BI Desktop render/interaction validation, remote CI execution. Prior local evidence recorded in repo (see §3/§6) remains the documented baseline but is not a substitute for a fresh, reproducible RC rerun in the validation environment.

## 2. M9/M8 freeze (preserved)
- **M9 (frozen):** PBIP `dashboard/PortfolioReport/Workbook.pbip` preserved; screenshots in `docs/screenshots/` (`page1_overview.png`, `page2_drilldown.png`, `page3_restatements.png`, `page4_sensitivity.png`, plus naming copies). Page 4 = quintile bar `a4s1` + table `a4t1`. See `docs/M9_STATUS.md`, `docs/DASHBOARD_VALIDATION_SQL.md`.
- **M8 (frozen):** `config/sensitivity.yaml` SHA-256 **`93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`** (unchanged). `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `results/E9_COVERAGE.md` preserved.

## 3. M10 verification evidence (2026-11-10 session)

| Item | Evidence (verified now) | Status |
|---|---|---|
| NAV import & idempotency / provenance | **Canonical** `core.nav_snapshot` 3 `amfi_nav_m1`: **1,811,703** obs (2006-04-02–2026-11-06, 85 approved source-file ranges), 0 duplicate `(snapshot,scheme,date)` keys. **6** M4/M6/test seed observations isolated to **separate fixture snapshot** `core.nav_snapshot` 4 `test_fixture_nav_seeds` (labelled `m4-seed`/`m6-seed`/`test-seed`), preserving test fixtures; DB total 1,811,709. Import path idempotent by design (`scripts/import_nav.py`). Approved source available read-only at `C:\Users\Vicky\Desktop\fundlens\data\raw\amfi` (86 `.gz`). **Fresh clean re-import + idempotency proof not executed.** | **Reconciled & isolated (verified); fresh re-import/idempotency rerun not executed** |
| Migrations & checksum integrity | 7 applied (`core.migration`): `001_initial_schema.sql`…`007_dashboard_perf_views.sql` with checksums matching `sql/migrations/*.sql` byte-for-byte (SHA-256 recomputed 2026-11-10). Runner enforces checksum match and fails on mismatch (`scripts/migrations/runner.py`). | **Verified (integrity/match).** |
| Migration checksum-tamper | Tamper-detection logic implemented and regression test exists: `tests/integration/test_migration_checksum.py::test_checksum_tamper_fails_loudly_without_touching_db` (disposable copy, expects `Migration checksum mismatch`, asserts DB counts unchanged). Prior exercised evidence documented in repo (`docs/RELEASE_CANDIDATE.md`, `DECISIONS.md` D-060). | **Not re-executed this session** (pytest/`DATABASE_URL` test env not run; `psycopg`/pytest unavailable in host Python). |
| Full test suite | 9 unit + 14 integration/property test modules present (`tests/`). Prior local claim: **75 passed** (Docker PG16 + CPython 3.12). | **Not executed this session** (`python -m pytest`: module missing; host Python 3.14.10; no `.venv`). |
| Ruff | Config in `pyproject.toml` (`E4,E7,E9,F,I`). Prior local claim: clean. | **Not executed this session** (`python -m ruff`: module missing). |
| Two clean `make reproduce` runs, matching logical hashes | `scripts/reproduce.py` deterministic pipeline; prior documented double-run `RESULTS.md` hash `ac6257e2…` (baseline). Current DB holds demo/marts and changes since baseline mean hashes must be **re-established** by two clean empty-DB runs; `make`/deps/source data not exercised. | **Not executed (blocking to claim fresh RC determinism).** |
| Dashboard marts/views post-reproduce | `marts.sensitivity_e9_quintiles/detail` built and SQL-validated now (654, deterministic, per-band match). `build_portfolio_history.py`/`load_sensitivity_mart.py` presentation-compatible. | **Current state verified; post-reproduce rebuild not applicable (reproduce not run).** |

## 4. Documentation & audit

| Audit | Result |
|---|---|
| `RESULTS.md` | Updated with M10 (2026-11-10) verification notes: distinguishes DB/file evidence verified now vs items not re-executed; retains historical baseline values and limitations. No fabricated numbers. |
| `README.md` | Updated: M9 frozen/visually accepted, E9 quintile chart, current verification status (verified vs not re-executed), dashboard screenshot names, no push/publish claim. |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Updated: FR-B11/E2–E9/M9 statuses reflect frozen dashboard, quintile E9 presentation, and M10 verification posture with explicit manual/unexecuted items. |
| `docs/PROGRESS.md`, `docs/RELEASE_CANDIDATE.md`, `docs/M9_STATUS.md` | Updated to reflect freeze and M10 final verification state/limitations. |
| `docs/DASHBOARD_VALIDATION_SQL.md`, `docs/DASHBOARD_AUDIT.md` | Contain E9 quintile construction, tie-handling, 654/uniqueness, per-band validation, and XIRR−TWR comparability investigation (validated, no methodology change). |
| Requirements/traceability coverage | PRD FR-B1–B14, NFRs, E1–E9, milestones and deliverables traced to components/tests/evidence with honest status (designed/approved/implemented/partial/manual/not re-executed). |

## 5. Git working tree & secret scan
- **Git:** repository initialized, branch `master`, **no commits**, **no remotes**. Working tree **entirely untracked** (`??` — source, docs, dashboard, config, results, tests, `.github/`, etc.); nothing staged/committed. No tags. **No push/publish performed.**
- **Secrets/config scan (repo files):** no `.env` committed (only `.env.example` placeholders). No matches for common private-key/token patterns (`BEGIN PRIVATE KEY`, `AKIA*`, `ghp_*`, `xoxb-`, `sk_live`) in tracked-scan scope. No real credentials found.
- **Local dev DSNs/endpoints:** `localhost:5434` and `password=postgres` appear as **local development defaults** in dashboard model TMDL/PBIP docs and some scripts/tests/config context (expected for a local Postgres prototype, not external secrets). `.gitignore` present. **Recommendation:** confirm no unintended secrets before any future commit/publish (out of scope here; no push).

## 6. Key verified results (documented baseline + current DB checks)
- **NAV:** canonical `core.nav_snapshot` 3 `amfi_nav_m1` **1,811,703** observations (2006-04-02–2026-11-06, approved 85 source-file ranges), 0 duplicate keys; **6** seed/test fixture observations isolated in `core.nav_snapshot` 4 `test_fixture_nav_seeds` (total DB 1,811,709) — reconciled/documented in `docs/NAV_RECONCILIATION_6_EXTRA.md` (verified 2026-11-10).
- **Migrations:** 7 applied, checksums match files (verified now).
- **Ledger/demo (DB):** 12 accounts, 2,288 txn revisions, demo correction/snapshots/replay materialized per pipeline design (DB present); P1 latest 124,325,759.90 / 110,372,447.52 / 13,953,312.38 INR (diff 0.00); restatement Δ +14,041.39 / +0.02 / +0.428972888 bp / +0.0042897288 pp (previously validated; consistent with marts).
- **Sensitivity (frozen):** config `93fb380b…`; 11,436 detail rows; E9 1,040 eligible, **654 solved** (386 no-root excluded), quintiles 131/131/131/131/130 (validated).
- **Prior local evidence (not re-run):** 75 tests passed, Ruff clean, 10 ad-hoc queries executed, double reproduce hash `ac6257e2…`, checksum-tamper exercised (Docker PG16 + CPython 3.12).

## 7. Outstanding limitations / manual or unexecuted items
1. **Not re-executed this session:** full pytest suite, Ruff, migration checksum-tamper regression test, NAV idempotency rerun from source, **two clean `make reproduce` runs with matching logical hashes** (requires prepared env: deps/CPython 3.12, `DATABASE_URL`, Docker, FundLens source as applicable, clean DB; destructive/heavy).
2. **Power BI Desktop (manual):** refreshed render/interaction validation of frozen PBIP (all pages, Page 4 bars/table/KPIs/zero line, filters, no broken fields/clipping) and confirmation screenshots reflect frozen state — **cannot be executed here**.
3. **CI:** GitHub Actions configured but **remote execution never performed**.
4. **E9:** partial by design/solver domain (654/1,040 solved; 386 excluded, documented). XIRR–TWR shown as annualised XIRR minus period TWR (same 12-mo window).
5. **E6:** p50/p95 benchmark not claimed.
6. **Git/release:** no commits/remotes/tags; **no push/publish/tag/release** without Vicky’s explicit approval.
7. Local dev `localhost:5434`/default credentials in PBIP/docs/scripts are environment-specific, not external secrets.

## 8. Release recommendation
- **v1.0.0 RC is evidence-backed at artifact/DB/doc level with an honest gap list.** Do **not** claim full RC verification complete until, in a prepared validation environment: (a) tests+Ruff pass, (b) checksum-tamper test passes, (c) NAV import idempotency rerun confirmed, (d) **two clean `make reproduce` runs from empty DB produce matching logical hashes** with marts/views rebuilt/consistent, and (e) Vicky confirms Desktop validation/screenshots for the frozen dashboard.
- After those pass and Vicky explicitly approves: create tag/release/push per direction (none done now).

**No further feature development. Dashboard and M8 remain frozen.**
