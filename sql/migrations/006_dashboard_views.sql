-- 006_dashboard_views.sql — Power BI marts (PostgreSQL only, M9).
-- Views keep the business logic in SQL so PBIR visuals stay thin.
-- Every view is a plain SELECT over core.*; no financial engine is duplicated.

CREATE SCHEMA IF NOT EXISTS marts;

CREATE OR REPLACE VIEW marts.portfolio_overview AS
SELECT
    a.account_id,
    a.synthetic_ref,
    a.display_name,
    a.account_status,
    a.currency,
    count(DISTINCT b.txn_group_id) AS transaction_count
FROM core.account a
LEFT JOIN core.txn_business b ON b.account_id = a.account_id
GROUP BY a.account_id, a.synthetic_ref, a.display_name, a.account_status, a.currency;

CREATE OR REPLACE VIEW marts.account_drilldown AS
SELECT
    b.account_id,
    c.txn_group_id,
    c.txn_type,
    c.instruction_date,
    c.effective_date,
    c.allotment_date,
    c.posting_sequence,
    c.scheme_code,
    c.source_scheme_code,
    c.target_scheme_code,
    c.amount_instructed,
    c.units_instructed,
    c.recorded_at,
    c.is_voided
FROM core.txn_version_current c
JOIN core.txn_business b ON b.txn_group_id = c.txn_group_id;

CREATE OR REPLACE VIEW marts.correction_audit AS
SELECT
    r.txn_group_id,
    r.revision_no,
    r.revision_kind,
    r.revision_status,
    r.txn_type AS revision_txn_type,
    r.effective_date,
    coalesce(g.reason_code, 'ORIGINAL') AS reason_code,
    g.recorded_at AS correction_recorded_at,
    g.correction_type
FROM core.txn_revision r
LEFT JOIN core.correction_group g ON g.correction_group_id = r.correction_group_id;

CREATE OR REPLACE VIEW marts.rejected_corrections AS
SELECT
    correction_rejection_id,
    txn_group_id,
    correction_type,
    reason_code,
    attempted_recorded_at,
    actor_id
FROM core.correction_rejection;

CREATE OR REPLACE VIEW marts.report_snapshots AS
SELECT
    report_snapshot_id,
    account_id,
    period_start,
    period_end,
    known_as_of,
    (payload ->> 'total_value')::numeric AS total_value,
    (payload ->> 'cash')::numeric AS cash,
    payload -> 'performance' ->> 'twr' AS twr,
    payload -> 'performance' ->> 'modified_dietz' AS modified_dietz,
    payload -> 'performance' ->> 'xirr_rate' AS xirr_rate,
    payload_sha256
FROM core.report_snapshot;

CREATE OR REPLACE VIEW marts.nav_summary AS
SELECT
    amfi_scheme_code,
    count(*) AS observations,
    min(nav_date) AS first_nav_date,
    max(nav_date) AS last_nav_date,
    avg(nav) AS avg_nav,
    max(nav) AS max_nav
FROM core.nav_observation
WHERE nav_snapshot_id = 3
GROUP BY amfi_scheme_code;
