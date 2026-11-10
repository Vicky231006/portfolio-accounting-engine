-- Q6: Which schemes have stale NAVs on a given valuation date?
SELECT amfi_scheme_code, max(nav_date) AS latest_nav
FROM core.nav_observation
WHERE nav_snapshot_id = 3 AND nav_date <= '2026-11-09'
GROUP BY amfi_scheme_code
HAVING '2026-11-09'::date - max(nav_date) > 5;
