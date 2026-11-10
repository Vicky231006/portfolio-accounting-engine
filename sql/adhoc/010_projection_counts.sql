-- Q10: Do rebuilt projections match the revision history?
SELECT count(*) AS period_rows, count(*) FILTER (WHERE lower(system_period) <> lower(system_period)) AS _unused
FROM core.txn_revision_period;
