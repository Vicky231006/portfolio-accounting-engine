-- Q8: Which archived report snapshots exist and what did they store?
SELECT report_snapshot_id, account_id, period_start, period_end, known_as_of, payload_sha256
FROM core.report_snapshot
ORDER BY report_snapshot_id;
