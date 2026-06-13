-- 0011_tbb_acquisition_stats
-- TBB "Uzaktan ve Şubeden Müşteri Edinim İstatistikleri" — monthly remote
-- (digital) vs branch (non-digital) customer acquisition, sector-wide. One tidy
-- long row per (period, entity_type, method). Mirrors src/tbb/schema.py exactly;
-- the composite PRIMARY KEY matches the SQLite staging table so push_to_d1's
-- INSERT OR REPLACE conflict-detection behaves identically. Idempotent.
CREATE TABLE IF NOT EXISTS tbb_acquisition_stats (
    period        TEXT NOT NULL,   -- 'YYYY-MM' (monthly)
    entity_type   TEXT NOT NULL,   -- 'individual' | 'merchant' | 'legal'
    method        TEXT NOT NULL,   -- remote_application|remote_rep|bulk|remote_courier|branch
    method_tr     TEXT NOT NULL,   -- Turkish header label
    value         REAL,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, entity_type, method)
);

CREATE INDEX IF NOT EXISTS idx_tbb_acq_lookup
  ON tbb_acquisition_stats(entity_type, method, period);
