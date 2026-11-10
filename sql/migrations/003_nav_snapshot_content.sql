-- 003_nav_snapshot_content.sql — nav_snapshot content columns (M1, FundLens NAV contract 4.4 item 8)
ALTER TABLE core.nav_snapshot ADD COLUMN IF NOT EXISTS row_count BIGINT NOT NULL DEFAULT 0;
ALTER TABLE core.nav_snapshot ADD COLUMN IF NOT EXISTS min_nav_date DATE;
ALTER TABLE core.nav_snapshot ADD COLUMN IF NOT EXISTS max_nav_date DATE;
