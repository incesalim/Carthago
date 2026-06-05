-- 0002_drop_weekly_bulletin
-- weekly_bulletin is the deprecated pre-`weekly_series` table: read nowhere in
-- src/, scripts/, or web/ (verified), no longer written by the weekly scraper,
-- and not pushed by push_to_d1 (it has no time column). Drop it from D1.
-- Safe: idempotent, and recoverable via D1 Time Travel / R2 backups if needed.
DROP TABLE IF EXISTS weekly_bulletin;
