-- Q9: Which NAV observations conflict across source files?
SELECT * FROM core.nav_revision_conflict ORDER BY amfi_scheme_code, nav_date;
