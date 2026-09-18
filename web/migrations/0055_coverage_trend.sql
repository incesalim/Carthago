-- Coverage trend — one snapshot row per healthcheck run (daily 06:00 UTC).
-- Gives the /admin coverage matrix a TIME axis: errors/missing as deltas over
-- days ("are we getting cleaner?"), not just point-in-time counts.
--
-- Written directly by scripts/healthcheck.py via wrangler (the 0028
-- source_freshness precedent) and deliberately NOT in push_to_d1's SYNC_TABLES:
-- it is monitoring telemetry about the pipeline, not pipeline data, and must
-- not ride the content-hash/partition-digest write machinery.
CREATE TABLE IF NOT EXISTS coverage_trend (
    checked_at    TIMESTAMP NOT NULL PRIMARY KEY,
    ok            INTEGER NOT NULL,
    manual        INTEGER NOT NULL,
    error         INTEGER NOT NULL,
    missing       INTEGER NOT NULL,
    not_expected  INTEGER NOT NULL,
    lanes         INTEGER NOT NULL
);
