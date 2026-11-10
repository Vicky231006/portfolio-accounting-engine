-- 004_ledger_corrections.sql — immutable revision ledger + bitemporal corrections (M3, FR-B3/B4)
-- Design: docs/M3_DESIGN.md; DECISIONS D-041..D-045.
-- The projection table (txn_version_current) is rebuildable from txn_revision
-- and is explicitly NOT immutable (D-005).

CREATE SCHEMA IF NOT EXISTS core;

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Synthetic master data (M2). Idempotent: safe to re-run.
CREATE TABLE IF NOT EXISTS core.investor (
    investor_id BIGINT PRIMARY KEY,
    synthetic_ref VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL DEFAULT '',
    data_class VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    synthetic_label VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extend the M1 account table with the M2 master fields (additive only; existing rows preserved).
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS investor_id BIGINT REFERENCES core.investor(investor_id);
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS display_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS account_status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE'
    CHECK (account_status IN ('ACTIVE', 'CLOSED'));
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'INR';
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS opened_date DATE;
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS closed_date DATE;
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS data_class VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav';
ALTER TABLE core.account ADD COLUMN IF NOT EXISTS synthetic_label VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav';

-- Stable business identity (one row per M2 transaction group; never updated after ingest).
CREATE TABLE IF NOT EXISTS core.txn_business (
    txn_group_id TEXT PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES core.account(account_id),
    investor_id BIGINT NOT NULL REFERENCES core.investor(investor_id),
    data_class VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    synthetic_label VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Atomic correction unit (one group per correction operation in M3).
CREATE TABLE IF NOT EXISTS core.correction_group (
    correction_group_id TEXT PRIMARY KEY,
    txn_group_id TEXT NOT NULL REFERENCES core.txn_business(txn_group_id),
    correction_type VARCHAR(32) NOT NULL
        CHECK (correction_type IN ('REPLACE', 'VOID', 'REVERSE_AND_REPLACE')),
    reason_code VARCHAR(64) NOT NULL,
    reason_note TEXT NOT NULL DEFAULT '',
    source_ref TEXT NOT NULL DEFAULT 'synthetic_intent',
    actor_id VARCHAR(64) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'APPLIED' CHECK (status IN ('APPLIED', 'REJECTED')),
    applied_revision_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutable append-only revision history. Never UPDATE business facts on this table;
-- the only UPDATE permitted is closing the prior system_period on correction.
CREATE TABLE IF NOT EXISTS core.txn_revision (
    txn_revision_id BIGSERIAL PRIMARY KEY,
    txn_group_id TEXT NOT NULL REFERENCES core.txn_business(txn_group_id),
    revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
    correction_group_id TEXT REFERENCES core.correction_group(correction_group_id),
    prev_revision_id BIGINT REFERENCES core.txn_revision(txn_revision_id),
    revision_kind VARCHAR(32) NOT NULL
        CHECK (revision_kind IN ('ORIGINAL', 'REPLACE', 'VOID', 'REVERSE_AND_REPLACE')),
    revision_status VARCHAR(16) NOT NULL DEFAULT 'ACCEPTED'
        CHECK (revision_status IN ('ACCEPTED', 'VOIDED')),
    txn_type VARCHAR(32) NOT NULL
        CHECK (txn_type IN ('CONTRIBUTION', 'WITHDRAWAL', 'PURCHASE', 'REDEMPTION', 'SIP_INSTALMENT', 'SWITCH')),
    instruction_date DATE NOT NULL,
    effective_date DATE NOT NULL,
    allotment_date DATE,
    source_nav_date DATE,
    target_allotment_date DATE,
    posting_sequence INTEGER NOT NULL CHECK (posting_sequence > 0),
    scheme_code VARCHAR(32),
    source_scheme_code VARCHAR(32),
    target_scheme_code VARCHAR(32),
    amount_instructed NUMERIC(20, 2),
    units_instructed NUMERIC(20, 3),
    recorded_at TIMESTAMPTZ NOT NULL,
    system_period TSTZRANGE NOT NULL,
    data_class VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    synthetic_label VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_txn_revision_group_no UNIQUE (txn_group_id, revision_no)
);

-- No-overlap enforcement: one business transaction can never have two revisions
-- with overlapping system (knowledge-time) periods (D-042).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ex_txn_revision_no_overlap'
    ) THEN
        ALTER TABLE core.txn_revision
            ADD CONSTRAINT ex_txn_revision_no_overlap
            EXCLUDE USING gist (txn_group_id WITH =, system_period WITH &&);
    END IF;
END $$;

-- Rebuildable current-version projection (NOT immutable; see D-041).
CREATE TABLE IF NOT EXISTS core.txn_version_current (
    txn_group_id TEXT PRIMARY KEY REFERENCES core.txn_business(txn_group_id),
    latest_revision_id BIGINT NOT NULL REFERENCES core.txn_revision(txn_revision_id),
    revision_no INTEGER NOT NULL,
    txn_type VARCHAR(32) NOT NULL,
    instruction_date DATE NOT NULL,
    effective_date DATE NOT NULL,
    allotment_date DATE,
    source_nav_date DATE,
    target_allotment_date DATE,
    posting_sequence INTEGER NOT NULL,
    scheme_code VARCHAR(32),
    source_scheme_code VARCHAR(32),
    target_scheme_code VARCHAR(32),
    amount_instructed NUMERIC(20, 2),
    units_instructed NUMERIC(20, 3),
    recorded_at TIMESTAMPTZ NOT NULL,
    is_voided BOOLEAN NOT NULL DEFAULT FALSE,
    data_class VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    synthetic_label VARCHAR(64) NOT NULL DEFAULT 'synthetic_accounts_real_nav',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log of refused corrections (one row per rejected attempt).
CREATE TABLE IF NOT EXISTS core.correction_rejection (
    correction_rejection_id BIGSERIAL PRIMARY KEY,
    correction_group_id TEXT,
    txn_group_id TEXT NOT NULL,
    expected_prior_revision_id BIGINT,
    correction_type VARCHAR(32) NOT NULL
        CHECK (correction_type IN ('REPLACE', 'VOID', 'REVERSE_AND_REPLACE')),
    reason_code VARCHAR(64) NOT NULL,
    attempted_recorded_at TIMESTAMPTZ NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
