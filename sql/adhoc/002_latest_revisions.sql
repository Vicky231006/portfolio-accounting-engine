-- Q2: What is the latest revision of each synthetic transaction?
SELECT txn_group_id, revision_no, txn_type, effective_date, amount_instructed, units_instructed
FROM core.txn_version_current
ORDER BY txn_group_id;
