# Visual Audit — PRD §11 → Visual / Measure / Source

| PRD requirement | Visual (file) | Measure / column | Source table / mart | Verification |
|---|---|---|---|---|
| Synthetic account count | Page 1 card `a1c1` | `SyntheticAccountCount = COUNTROWS(PortfolioOverview)` | `marts.portfolio_overview` | SQL count = 12 |
| Account status | Page 1 bar `a1b1` | `Count(PortfolioOverview.account_id)` by `account_status` | `marts.portfolio_overview` | Groups: 12 ACTIVE |
| Transaction count | Page 2 card `a2c1` | `TransactionCount = COUNTROWS(AccountDrilldown)` | `marts.account_drilldown` | SQL count = 2,287 |
| Transactions by type | Page 2 bar `a2b1` | `Count(AccountDrilldown.txn_group_id)` by `txn_type` | `marts.account_drilldown` | 6 types present |
| Correction count | Page 3 card `a3c1` | `CorrectionCount = COUNTROWS(RestatementAudit)` | `marts.correction_audit` (revisions, not group ids) | 2,287 rows, 0 corrections applied yet (honest) |
| Corrections by kind | Page 3 bar `a3b1` | `Count(RestatementAudit.txn_group_id)` by `revision_kind` | `marts.correction_audit` | ORIGINAL only until corrections applied |
| Path count | Page 4 card `a4c1` | `PathCount = COUNTROWS(Sensitivity)` | `marts.nav_summary` | 783 schemes |
| NAV depth by scheme | Page 4 bar `a4b1` | `Avg(Sensitivity.nav)` by `amfi_scheme_code` | `marts.nav_summary` | Avg price; no SUM across history |

**Rules enforced:** no generic titles (*Sum of nav*, *Count of txn_group_id* simplified internally but `nativeQueryRef` relabelled); no SUM→MAX hacks; grain fixed at the mart level (one row per account / transaction / revision / scheme).
