-- 002_nav_revision_conflict.sql — NAV revision conflict tracking (M1, FundLens NAV contract 4.4)
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.nav_revision_conflict (
    nav_revision_conflict_id BIGSERIAL PRIMARY KEY,
    nav_snapshot_id BIGINT NOT NULL REFERENCES core.nav_snapshot(nav_snapshot_id),
    amfi_scheme_code VARCHAR(32) NOT NULL,
    nav_date DATE NOT NULL,
    original_nav NUMERIC(20, 6) NOT NULL,
    conflicting_nav NUMERIC(20, 6) NOT NULL,
    source_file_sha256 VARCHAR(64) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_note TEXT,
    CONSTRAINT uq_nav_conflict_snapshot_scheme_date UNIQUE (nav_snapshot_id, amfi_scheme_code, nav_date)
);
