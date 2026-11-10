# bitemporal-ledger — Portfolio Accounting & Performance Engine

Synthetic-account portfolio accounting and performance reporting on real AMFI NAVs. **Educational prototype; not investment advice; not a regulatory-compliance claim.**

## Quick start

```powershell
docker compose up -d postgres
# set DATABASE_URL (e.g. postgresql://postgres:postgres@localhost:5434/bitemporal_ledger)
python scripts/migrations/runner.py
python scripts/import_nav.py --source-dir <fundlens-raw-amfi> --snapshot-name amfi_nav_m1 --apply
python scripts/generate_synthetic.py --config config/generator.yaml --output-dir output/synthetic/run1
python scripts/reproduce.py   # writes RESULTS.md (deterministic pipeline)
```

## Results

See `RESULTS.md` (E1–E9, dataset/config hashes, invariant counts, M10 verification notes).

## Milestones (PRD v2.0, M0–M10)

M1 Foundations (approved), M2 Generator (approved), M3 Ledger & Corrections (approved), M4 Positions & Valuation (approved), M5 Performance Engine (approved), M6 Snapshots & Restatement (implemented), M7 Invariants & Pipeline (implemented), M8 Sensitivity (executed, **frozen**: config `93fb380b…`; E8 complete, E9 partial 654/1,040 solved), **M9 Dashboard & SQL — visually accepted and frozen (2026-11-10)**, **M10 Release — v1.0.0 RC (final verification documented)**.

## Dashboard (frozen)

- Power BI PBIP (PostgreSQL-only, `localhost:5434` / `bitemporal_ledger`): `dashboard/PortfolioReport/Workbook.pbip`, 4 pages. **No further visual iterations** (Vicky, 2026-11-10). Page 4 E9: **drawdown-quintile bar chart** (final alternative to scatter), 654 solved observations, deterministic quintiles, validated against source; XIRR annualised vs period TWR (same 12-mo window).
- Screenshots: `docs/screenshots/page1_overview.png`, `docs/screenshots/page2_drilldown.png`, `docs/screenshots/page3_restatements.png`, `docs/screenshots/page4_sensitivity.png`. Desktop render/interaction validation remains **manual** (see `docs/M9_STATUS.md`, `dashboard/PortfolioReport/VALIDATION.md`).

## Verification status (2026-11-10)

- **Verified now (DB/files):** Docker PG16 container healthy; NAV snapshot `amfi_nav_m1` (id 3) 1,811,709 observations, 0 duplicate keys; 7 migrations applied with checksums matching `sql/migrations/*.sql`; E9 quintile marts 654/654 distinct, per-band stats independently validated; M8 config hash preserved; git/secret scan and doc/traceability audits completed (see `docs/V1_0_0_RC_FINAL_REPORT.md`).
- **Prior local evidence (recorded, not re-executed this session):** migrations, double `make reproduce` (hash `ac6257e2…`), **75 tests passed**, `ruff` clean, 10 ad-hoc queries, checksum-tamper exercised, ingestion idempotent (Docker PG16 + CPython 3.12).
- **Not executed in this environment:** full pytest/Ruff, checksum-tamper test rerun, NAV idempotency rerun from source, **two clean `make reproduce` runs with matching logical hashes** (requires prepared env), Power BI Desktop validation, remote CI.

## Honest limitations

- E9: 654/1,040 solved (386 no-root excluded, documented); TWR/XIRR gap = annualised XIRR minus period TWR (same 12-mo window). E6 p50/p95 not claimed.
- Dashboard: PBIP/marts shipped and SQL-validated; live Desktop execution, interactions, and screenshot finality are manual.
- GitHub Actions configured; remote execution never performed. Jira/local backlog only.
- Repo currently uncommitted/untracked, no remote/tags. **No push, publish, or tag/release without Vicky’s explicit approval.**

## Deliverables

`docs/PROGRESS.md` (milestones), `docs/REQUIREMENTS_TRACEABILITY.md` (PRD→evidence), `DECISIONS.md`, `RESULTS.md`, `docs/V1_0_0_RC_FINAL_REPORT.md` (M10 RC), `docs/RELEASE_CANDIDATE.md`, `docs/M9_STATUS.md`. FundLens is read-only and untouched. M8 sensitivity config/results and dashboard visuals are **frozen**. No further feature development.
