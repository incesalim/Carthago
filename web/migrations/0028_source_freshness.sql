-- 0028_source_freshness
-- The latest data-freshness verdict per source, recorded by the daily health
-- check (scripts/healthcheck.py) so the /admin panel can show GROUND TRUTH
-- instead of a calendar estimate.
--
-- WHY: the BDDK monthly bulletin publishes on no fixed schedule, so "are we
-- current?" can only be answered by asking BDDK. The daily health check already
-- runs that probe (src/scrapers/bddk_probe) to alert; this table lets it also
-- persist the answer, and the admin page reads it — one row, overwritten each
-- run. The Worker can't probe BDDK per request (slow, and BDDK serves a broken
-- cert chain), so it reads the recorded verdict here.
--
-- Written DIRECTLY to remote D1 by the health-check workflow (a tiny status row,
-- refreshed daily) — it is NOT part of the local-SQLite → R2 → push_to_d1
-- pipeline, so it is deliberately absent from push_to_d1.py's SYNC_TABLES.
--
-- Columns:
--   source         'bddk_monthly' (extensible to other sources)
--   checked_at     ISO-8601 UTC of the probe
--   status         'fresh' | 'stale' | 'unknown'
--   latest_period  the period held when checked ('YYYY-MM'); the admin trusts the
--                  verdict only while this still matches the newest data in D1
--   note           human line ("2026-06 not yet published by BDDK")

CREATE TABLE IF NOT EXISTS source_freshness (
    source        TEXT NOT NULL PRIMARY KEY,
    checked_at    TEXT NOT NULL,
    status        TEXT NOT NULL,
    latest_period TEXT,
    note          TEXT
);
