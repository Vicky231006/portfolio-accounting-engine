-- Q1: How many observations are in the immutable NAV snapshot?
SELECT count(*), min(nav_date), max(nav_date), count(DISTINCT amfi_scheme_code)
FROM core.nav_observation
WHERE nav_snapshot_id = 3;
