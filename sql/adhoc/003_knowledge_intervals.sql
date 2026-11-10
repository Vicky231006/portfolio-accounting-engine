-- Q3: Which knowledge intervals exist per business transaction?
SELECT txn_group_id, txn_revision_id, system_period::text
FROM core.txn_revision_period
ORDER BY txn_group_id;
