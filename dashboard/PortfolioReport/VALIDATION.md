# Power BI Manual Validation Checklist



**Connector: PostgreSQL only.** Every query in this project uses the Power BI

PostgreSQL connector against `127.0.0.1:5434` / `bitemporal_ledger`. No

MySQL or ODBC connector is used anywhere.



## Validation steps



1. Start PostgreSQL 16: `docker compose up -d postgres`.

2. Reproduce: migrations → NAV import (idempotent) → generator → `python scripts/reproduce.py`.

3. Open `dashboard/PortfolioReport/Workbook.pbip` in Power BI Desktop. The

   file is the standard PBIP shortcut (`version` + `artifacts[].report.path`);

   the model automatically resolves via `PortfolioReport.Report/definition.pbir`

   (`datasetReference.byPath = ../PortfolioReport.SemanticModel`) and

   `PortfolioReport.SemanticModel/definition.pbism`.

4. Datasource: Get data → **PostgreSQL database** (`localhost:5434`). Every

   M expression in `PortfolioReport.SemanticModel/definition/tables/*.tmdl`

   uses `PostgreSQL.Database(...)`. Verify no MySQL/ODBC source exists.

5. Refresh: `core.account`, `core.txn_version_current`, `core.txn_revision_period`,

   `core.nav_observation`, `core.report_snapshot`, `core.txn_revision`,

   `core.correction_group`, `core.correction_rejection`.

6. Pages (one per `Definition/pages/<id>/page.json`):

   - **1 Portfolio Overview** — synthetic account count, total value,

     TWR, XIRR, allocation, cash — synthetic-data footer on every page.

   - **2 Account Drilldown** — selector + date range show holdings,

     ledger, performance series with flow markers.

   - **3 Restatements and Audit** — original vs restated, K1/K2,

     changed versions/reasons/deltas, replay pass/fail, rejected corrections.

   - **4 Sensitivity** — scenario distributions with pre-registration note.

7. Relationships: `PortfolioOverview[account_id]` and `AccountDrilldown[txn_group_id]`

   link through `core.txn_business`; `RestatementAudit` links by

   `correction_group_id`; `Sensitivity` is by AMFI scheme.

8. Slicers: synthetic account, date range, report version — all affect visuals.

9. Verify TWR vs XIRR measures are separately labelled (never blended).

10. Save **four screenshots** to `docs/screenshots/` (one per page).



**Status:** Prepared. Live Power BI Desktop validation must be performed by

the operator (this environment cannot drive the GUI). The

`docs/screenshots/` directory is empty until the manual run.

