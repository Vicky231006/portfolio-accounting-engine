# Dashboard

## Working preview (open now)

- **`dashboard/index.html`** — self-contained 4-page dashboard rendered from committed, repo-backed results (`scripts/render_dashboard.py`).  
  - Page 1: portfolio overview (synthetic account/ledger counts, transaction mix, honest disclosure of unmaterialised valuation/TWR/XIRR/snapshots).  
  - Page 2: account drilldown scope (accounts, ledger rows, Power BI filter requirements).  
  - Page 3: restatements & audit with **correct distinctions** — original revisions vs applied correction operations vs rejected corrections vs archived snapshots (no `txn_group_id`-as-correction proxy; 0/0/0 reported honestly).  
  - Page 4: M8 sensitivity study (344 eligible / 30 selected, 40 windows, 1,040 eligible, 11,436 detail rows, E9 n=654 solved gaps / 386 excluded) from `results/sensitivity_detail.csv`, `results/sensitivity_summary.json`, `results/E9_COVERAGE.md`.  
- **`docs/screenshots/dashboard_preview.html`** — same rendered preview (for review/screenshots context).

Regenerate: `python scripts/render_dashboard.py`

## Power BI (PBIP, PostgreSQL-only)

- `dashboard/PortfolioReport/Workbook.pbip` — Power BI Project artefact. All model queries use `PostgreSQL.Database("localhost:5434","bitemporal_ledger")` and `marts.*`/`core.*` views only (no MySQL/ODBC).
- Requires a populated database and **Power BI Desktop** refresh; live screenshots are manual (see `PortfolioReport/VALIDATION.md`). PBIP visuals were corrected to avoid mislabeled measures (e.g. revision counts not labelled as corrections; sensitivity NAV context not labelled as M8 paths).

> Synthetic portfolio data; real AMFI NAV inputs. Educational prototype — not investment advice or a regulatory/compliance system.
