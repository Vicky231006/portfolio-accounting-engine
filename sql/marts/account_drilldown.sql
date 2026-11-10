-- Mart: account drilldown holdings (Page 2).
SELECT txn_group_id, txn_type, effective_date, scheme_code, source_scheme_code, target_scheme_code,
       amount_instructed, units_instructed, is_voided
FROM core.txn_version_current
ORDER BY effective_date, posting_sequence;
