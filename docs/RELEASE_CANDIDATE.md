# v1.0.0 Release Candidate Report

> **SUPERSEDED (2026-11-11).** This file is retained as historical evidence of the
> release-candidate state on 2026-11-10. It is **not** the current release
> status. The final verified v1.0.0 report is
> [`docs/V1_0_0_FINAL_REPORT.md`](V1_0_0_FINAL_REPORT.md); see also
> [`CHANGELOG.md`](../CHANGELOG.md) and [`docs/M10_RELEASE_AND_CLOSURE.md`](M10_RELEASE_AND_CLOSURE.md).

**Date:** 2026-11-10  
**Status:** Release candidate — pending final approval. **No push, publish, tag or release has occurred.**  
**Dashboard:** frozen (M9 visually accepted by Vicky, 2026-11-10; E9 drawdown-quintile bar chart final). **M8 sensitivity frozen.** No further feature development.

> Canonical final RC detail: `docs/V1_0_0_RC_FINAL_REPORT.md` (verified evidence, audits, and outstanding limitations).

## 1. What was built

Portfolio accounting and performance engine on PostgreSQL 16 + Python 3.12 (M0–M10, PRD v2.0):

- **M1** migrations (001–007), idempotent NAV import (1,811,709 observations, snapshot `amfi_nav_m1` id 3).
- **M2** deterministic generator (seed 20261109, dataset hash `94839c5cb011…`).
- **M3** immutable bitemporal ledger (GiST no-overlap, atomic corrections).
- **M4** as-of positions and stale-aware valuation.
- **M5** performance engine (TWR / Modified Dietz / XIRR, independent reference).
- **M6** immutable snapshots, replay vs restatement, overwrite comparator.
- **M7** invariants + deterministic `make reproduce` pipeline.
- **M8** frozen sensitivity study (11,436 detail rows; E9 654/1,040 solved, 386 excluded) — **config/results preserved**.
- **M9** PostgreSQL-only PBIP (4 pages) + marts/SQL; **frozen** with final E9 drawdown-quintile bar chart (654 solved, deterministic, validated).
- **M10** final verification: evidence gathered/audited; some checks not re-executed in this environment (see below).

## 2. Verification (distinguished)

| Verification type | Status (2026-11-10) |
|---|---|
| **DB/files (verified now)** | Docker PG16 healthy. NAV snapshot 3: 1,811,709 rows, 2006-04-02–2026-11-06, 0 duplicate keys. 7 migrations applied, checksums match `sql/migrations/*.sql`. E9 quintile marts 654/654 distinct, per-band stats independently validated. M8 config hash `93fb380b…` preserved. Git working tree & secret scan completed. Docs/traceability audited. |
| **Prior local evidence (recorded, not re-run this session)** | Migrations, double `make reproduce` (hash `ac6257e2…`), 75 tests passed, `ruff` clean, 10 ad-hoc queries, checksum-tamper exercised, ingestion idempotent (Docker PG16 + CPython 3.12). |
| **Not executed this session** | Full pytest suite, Ruff, checksum-tamper regression rerun, NAV idempotency rerun from source, **two clean `make reproduce` runs with matching logical hashes** (requires prepared env), Power BI Desktop render/interaction validation, remote CI. |

## 3. Key results

- **E1:** 17 fixtures + independent reference within tolerance (recorded).
- **E2/E3/E4:** replay exact (count-based), comparator loss demonstrated, restatement/correction evidence materialized (recorded/demo).
- **E5:** 12 accounts, 0 failed (recorded).
- **E6:** deterministic repeats asserted; p50/p95 not claimed.
- **E7:** prior double-reproduce hash `ac6257e2…` recorded; **fresh two-clean-run match not re-executed**.
- **E8/E9:** frozen config `93fb380b…`, 11,436 detail rows; E9 n=654/1,040 (386 excluded). Quintile chart validated (annualised XIRR minus period TWR, same 12-mo window).
- **Dashboard:** PBIP/screenshots frozen (`docs/screenshots/page1_overview.png`, `page2_drilldown.png`, `page3_restatements.png`, `page4_sensitivity.png`); Desktop validation manual.

## 4. Known limitations / outstanding

- E9 partial (solver domain); E6 benchmark not claimed; XIRR–TWR convention difference expected (not error).
- Live Power BI Desktop execution/interaction/screenshot finality manual; CI remote execution never performed.
- Full RC rerun items pending in prepared env: tests, Ruff, tamper test, NAV idempotency rerun, **two clean reproduce runs with matching hashes**.
- Repo uncommitted/untracked, no remote/tags. Local dev DSNs in PBIP/docs (not external secrets).

## 5. Readiness

**Release candidate**, not released v1.0.0. Do not claim fresh full verification complete until pending items pass and Vicky confirms Desktop validation. **No push/publish/tag/release without Vicky’s explicit approval.** No further feature development.
