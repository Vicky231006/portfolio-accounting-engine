-- Mart: portfolio overview (Page 1). Synthetic accounts and real AMFI NAVs.
SELECT a.account_id, a.synthetic_ref, a.account_status, a.currency,
       count(DISTINCT c.txn_group_id) AS transaction_groups
FROM core.account a
LEFT JOIN core.txn_version_current c ON c.txn_group_id IS NOT NULL
GROUP BY a.account_id, a.synthetic_ref, a.account_status, a.currency;
