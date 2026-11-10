-- 001_initial_schema.sql — schemas, migration table, NAV snapshot tables (M1 initial migration)
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS core.migration (
    migration_id BIGSERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL DEFAULT '',
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.account (
    account_id BIGSERIAL PRIMARY KEY,
    synthetic_ref VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.nav_snapshot (
    nav_snapshot_id BIGSERIAL PRIMARY KEY,
    snapshot_name VARCHAR(255) NOT NULL,
    source_file_sha256 VARCHAR(64) NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.nav_observation (
    nav_observation_id BIGSERIAL PRIMARY KEY,
    nav_snapshot_id BIGINT NOT NULL REFERENCES core.nav_snapshot(nav_snapshot_id),
    amfi_scheme_code VARCHAR(32) NOT NULL,
    nav_date DATE NOT NULL,
    nav NUMERIC(20, 6) NOT NULL,
    option_type VARCHAR(16) NOT NULL,
    source_file_sha256 VARCHAR(64) NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_nav_observation_snapshot_scheme_date UNIQUE (nav_snapshot_id, amfi_scheme_code, nav_date)
);

CREATE TABLE IF NOT EXISTS core.report_snapshot (
    report_snapshot_id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES core.account(account_id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    known_as_of TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    calculation_engine_version VARCHAR(32) NOT NULL,
    nav_snapshot_id BIGINT NOT NULL REFERENCES core.nav_snapshot(nav_snapshot_id),
    payload JSONB NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
