-- TKBB (participation banks association) digital-banking lane.
-- Mirrors src/tkbb/schema.py verbatim so push_to_d1's INSERT OR REPLACE
-- conflict detection matches. Values are stored in RAW source units
-- (persons / count / TRY) — scaling happens in the web layer.

CREATE TABLE IF NOT EXISTS tkbb_digital_stats (
    period         TEXT NOT NULL,   -- 'YYYY-MM' quarter-end (Mar/Jun/Sep/Dec)
    metric         TEXT NOT NULL,   -- 'active_customers' | 'txn_volume' | 'txn_count' (+ _mix/_channel/_segment/_category/_province variants)
    breakdown      TEXT NOT NULL,   -- 'total' | 'channel_mix' | 'channel' | 'segment' | 'category' | 'province'
    dim_slug       TEXT NOT NULL,   -- slugified dimension value; 'total' for scalars
    dim_tr         TEXT NOT NULL,   -- verbatim Turkish label ('' for scalars)
    unit           TEXT NOT NULL,   -- 'persons' | 'count' | 'try' (RAW source units)
    value          REAL,
    period_tr      TEXT NOT NULL,   -- verbatim Turboard filter label ('2025 4.Dönem')
    source_dashlet TEXT NOT NULL,   -- Turboard dashlet id
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, metric, breakdown, dim_slug)
);

CREATE INDEX IF NOT EXISTS idx_tkbb_digital_lookup
  ON tkbb_digital_stats(metric, breakdown, dim_slug, period);

-- Monthly remote-vs-branch customer acquisition. The public dashboard exposes
-- only a rolling last-12-months window; rows accumulate here — never deleted.
CREATE TABLE IF NOT EXISTS tkbb_acquisition_stats (
    period         TEXT NOT NULL,   -- 'YYYY-MM' (monthly)
    series         TEXT NOT NULL,   -- 'remote' | 'branch'
    measure        TEXT NOT NULL,   -- 'applications' | 'customers'
    measure_tr     TEXT NOT NULL,   -- measure alias verbatim from the dashboard definition
    value          REAL,
    source_dashlet TEXT NOT NULL,
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, series, measure)
);

CREATE INDEX IF NOT EXISTS idx_tkbb_acq_lookup
  ON tkbb_acquisition_stats(series, measure, period);
