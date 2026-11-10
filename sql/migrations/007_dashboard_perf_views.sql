-- 007_dashboard_perf_views.sql — Page 1 / Page 3 supply (M9).
-- Portfolio value history comes from archived snapshots (immutable MD payload);
-- cash/allocations come from ledger projections. No financial logic is duplicated.

CREATE SCHEMA IF NOT EXISTS marts;

CREATE OR REPLACE VIEW marts.performance_summary AS
SELECT
    account_id,
    period_start,
    period_end,
    known_as_of,
    (payload -> 'performance' ->> 'twr')::numeric AS twr,
    (payload -> 'performance' ->> 'modified_dietz')::numeric AS modified_dietz,
    (payload -> 'performance' ->> 'xirr_rate')::numeric AS xirr_rate,
    (payload ->> 'total_value')::numeric AS total_value,
    (payload ->> 'cash')::numeric AS cash
FROM core.report_snapshot;

CREATE OR REPLACE VIEW marts.cash_flows AS
SELECT
    b.account_id,
    c.effective_date,
    c.txn_type,
    CASE WHEN c.txn_type IN ('CONTRIBUTION','SIP_INSTALMENT') THEN c.amount_instructed
         WHEN c.txn_type = 'WITHDRAWAL' THEN -c.amount_instructed
         ELSE NULL END AS external_amount
FROM core.txn_version_current c
JOIN core.txn_business b ON b.txn_group_id = c.txn_group_id
WHERE c.txn_type IN ('CONTRIBUTION','WITHDRAWAL','SIP_INSTALMENT');

CREATE OR REPLACE VIEW marts.holdings_snapshot AS
SELECT
    account_id,
    (h ->> 'scheme_code') AS scheme_code,
    (h ->> 'units')::numeric AS units,
    (h ->> 'value')::numeric AS value,
    (h ->> 'stale_nav')::boolean AS is_stale,
    (h ->> 'nav_date')::date AS nav_date
FROM core.report_snapshot,
     LATERAL jsonb_array_elements(payload -> 'holdings') AS h;

-- Correction audit with correct grain (one row per accepted revision, plus rejected rows).
CREATE OR REPLACE VIEW marts.correction_kpi AS
SELECT
    count(*) FILTER (WHERE revision_no = 1) AS original_transactions,
    count(*) FILTER (WHERE revision_no > 1) AS applied_operations,
    count(DISTINCT txn_group_id) FILTER (WHERE revision_no > 1) AS corrected_transactions
FROM core.txn_revision;

CREATE OR REPLACE VIEW marts.rejected_kpi AS
SELECT count(*) AS rejected_corrections
FROM core.correction_rejection;
