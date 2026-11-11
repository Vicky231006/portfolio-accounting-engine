-- 008_e6_perf_index.sql — E6 as-of query performance index (M7/E6).
--
-- The as-of query filters visible revisions by knowledge time:
--   WHERE r.recorded_at <= K
--   ORDER BY r.txn_group_id, r.revision_no DESC
-- Without a recorded_at index PostgreSQL scans the whole revision table for
-- every as-of request, even when K selects only a small early slice of
-- history. The index is deliberately narrow (one column) so write cost stays
-- low; it does not change query semantics or results.

CREATE INDEX IF NOT EXISTS ix_txn_revision_recorded_at
    ON core.txn_revision (recorded_at);
