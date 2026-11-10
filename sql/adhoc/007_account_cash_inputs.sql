-- Q7: What contribution/withdrawal cash moved per account (external flows only)?
SELECT b.account_id,
  coalesce(sum(CASE WHEN c.txn_type = 'CONTRIBUTION' THEN c.amount_instructed ELSE 0 END), 0) AS contributions,
  coalesce(sum(CASE WHEN c.txn_type = 'WITHDRAWAL' THEN c.amount_instructed ELSE 0 END), 0) AS withdrawals
FROM core.txn_version_current c
JOIN core.txn_business b ON b.txn_group_id = c.txn_group_id
WHERE c.txn_type IN ('CONTRIBUTION','WITHDRAWAL','SIP_INSTALMENT')
GROUP BY b.account_id;
