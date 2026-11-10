-- Q4: How many corrections were accepted vs rejected?
SELECT status, count(*) FROM core.correction_group GROUP BY status;
SELECT reason_code, count(*) FROM core.correction_rejection GROUP BY reason_code;
