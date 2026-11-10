-- Q5: What did knowledge time K see for one account (bitemporal slice)?
SELECT r.txn_group_id, r.revision_no, r.txn_type, r.effective_date
FROM core.txn_revision r
WHERE r.recorded_at <= '2026-01-31 09:00:00+00'
ORDER BY r.txn_group_id, r.revision_no DESC;
