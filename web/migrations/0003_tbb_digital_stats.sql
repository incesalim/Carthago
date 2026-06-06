-- 0003_tbb_digital_stats
-- TBB (Banks Association of Türkiye) quarterly digital-banking statistics —
-- sector-wide (no per-bank breakdown). One tidy long row per measurement.
-- Mirrors src/tbb/schema.py exactly; the composite PRIMARY KEY matches the
-- SQLite staging table so push_to_d1's INSERT OR REPLACE conflict-detection
-- behaves identically. Idempotent (IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS tbb_digital_stats (
    period        TEXT NOT NULL,   -- 'YYYY-MM' quarter-end (Mar/Jun/Sep/Dec)
    channel       TEXT NOT NULL,   -- 'digital' | 'internet' | 'mobile'
    segment       TEXT NOT NULL,   -- 'individual' | 'corporate' | 'total'
    section_code  TEXT NOT NULL,   -- 'I' | 'II' | 'III.1' … 'III.6' | 'IV'
    section_tr    TEXT NOT NULL,   -- Turkish section name
    metric_path   TEXT NOT NULL,   -- '>'-joined Turkish header path
    metric_slug   TEXT NOT NULL,   -- ascii slug of metric_path (stable join key)
    unit          TEXT NOT NULL,   -- 'persons_thousands' | 'count_thousands' | 'volume_bn_try'
    value         REAL,
    source_sheet  TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, channel, segment, section_code, metric_slug, unit)
);

CREATE INDEX IF NOT EXISTS idx_tbb_digital_lookup
  ON tbb_digital_stats(channel, segment, section_code, unit, period);
CREATE INDEX IF NOT EXISTS idx_tbb_digital_period
  ON tbb_digital_stats(period);
