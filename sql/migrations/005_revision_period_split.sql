-- 005_revision_period_split.sql — separate immutable revision source from temporal projection (M3 correction, D-047)
-- core.txn_revision becomes strictly append-only: no UPDATE or DELETE is ever
-- issued against accepted rows (enforced by trigger below). The knowledge-time
-- intervals live in core.txn_revision_period, which is fully rebuildable from
-- txn_revision (D-047). The current-version projection remains in
-- core.txn_version_current.

CREATE SCHEMA IF NOT EXISTS core;

-- Rebuildable temporal projection: one interval per revision.
CREATE TABLE IF NOT EXISTS core.txn_revision_period (
    txn_revision_id BIGINT PRIMARY KEY REFERENCES core.txn_revision(txn_revision_id),
    txn_group_id TEXT NOT NULL REFERENCES core.txn_business(txn_group_id),
    system_period TSTZRANGE NOT NULL
);

-- Copy the live intervals out of the old column (no-op when empty).
INSERT INTO core.txn_revision_period (txn_revision_id, txn_group_id, system_period)
SELECT txn_revision_id, txn_group_id, system_period
FROM core.txn_revision
ON CONFLICT (txn_revision_id) DO NOTHING;

-- Move the GiST no-overlap constraint to the projection table.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ex_txn_revision_period_no_overlap'
    ) THEN
        ALTER TABLE core.txn_revision_period
            ADD CONSTRAINT ex_txn_revision_period_no_overlap
            EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&);
    END IF;
END $$;

-- Remove the old constraint and the system_period column from the immutable source.
ALTER TABLE core.txn_revision DROP CONSTRAINT IF EXISTS ex_txn_revision_no_overlap;
ALTER TABLE core.txn_revision DROP COLUMN IF EXISTS system_period;

-- Enforce append-only at the storage layer: any UPDATE or DELETE on accepted
-- revision rows fails loudly. Only INSERT into txn_revision is ever issued
-- by the application.
CREATE OR REPLACE FUNCTION core.forbid_txn_revision_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'core.txn_revision is immutable: UPDATE/DELETE on accepted rows is forbidden (D-047)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_txn_revision_immutable ON core.txn_revision;
CREATE TRIGGER trg_txn_revision_immutable
    BEFORE UPDATE OR DELETE ON core.txn_revision
    FOR EACH ROW EXECUTE FUNCTION core.forbid_txn_revision_mutation();
