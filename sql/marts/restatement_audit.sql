-- Mart: restatement audit (Page 3).
SELECT r.txn_group_id, r.revision_no, r.revision_kind, g.reason_code, g.recorded_at
FROM core.txn_revision r
JOIN core.correction_group g ON g.correction_group_id = r.correction_group_id
ORDER BY r.txn_group_id, r.revision_no;
