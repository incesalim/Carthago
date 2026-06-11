-- 0007_tefas_funds
-- TEFAS (tefas.gov.tr) fund-market lane — sector-level daily aggregates,
-- computed at ingest from the per-fund fonGnlBlgSiraliGetir /
-- dagilimSiraliGetirT JSON endpoints (per-fund raw rows are not persisted).
-- AUM stored in raw TL; allocation percentages are AUM-weighted over the
-- funds covered by both endpoints that day. Mirrors src/tefas/schema.py
-- exactly (minus the staging-only tefas_fetch_log); composite PRIMARY KEYs
-- match the SQLite staging tables so push_to_d1's INSERT OR REPLACE
-- conflict-detection behaves identically. Idempotent (IF NOT EXISTS).
-- tefas_top_funds partitions are replaced on re-ingest; stale fund codes are
-- deleted via the d1_pending_deletes outbox in the staging DB.

CREATE TABLE IF NOT EXISTS tefas_manager_daily (
    date           TEXT NOT NULL,   -- 'YYYY-MM-DD' trading day
    fon_tipi       TEXT NOT NULL,   -- 'YAT'|'EMK'|'BYF'|'GYF'|'GSYF'
    manager        TEXT NOT NULL,   -- normalize.extract_manager(fonUnvan)
    aum_try        REAL,            -- Σ portfoyBuyukluk, raw TL
    fund_count     INTEGER,
    investor_count INTEGER,         -- Σ kisiSayisi (double-counts multi-fund investors)
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, manager)
);

CREATE INDEX IF NOT EXISTS idx_tefas_manager_tipi
  ON tefas_manager_daily(fon_tipi, date);

CREATE TABLE IF NOT EXISTS tefas_allocation_daily (
    date          TEXT NOT NULL,
    fon_tipi      TEXT NOT NULL,
    asset_class   TEXT NOT NULL,    -- normalize.ASSET_CLASSES (~11 classes)
    weighted_pct  REAL,             -- AUM-weighted %, can sit outside 0..100 (repo borrowing)
    aum_base_try  REAL,             -- covered AUM the weighting ran over, raw TL
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, asset_class)
);

CREATE TABLE IF NOT EXISTS tefas_category_daily (
    date           TEXT NOT NULL,
    fon_tipi       TEXT NOT NULL,
    category       TEXT NOT NULL,   -- normalize.categorize_fund(fonUnvan)
    aum_try        REAL,
    fund_count     INTEGER,
    investor_count INTEGER,
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, category)
);

CREATE TABLE IF NOT EXISTS tefas_top_funds (
    date           TEXT NOT NULL,
    fon_tipi       TEXT NOT NULL,
    fon_kodu       TEXT NOT NULL,
    fon_unvan      TEXT,
    manager        TEXT,
    rank           INTEGER NOT NULL,  -- 1..15 by AUM within (date, fon_tipi)
    aum_try        REAL,
    price          REAL,              -- NAV per unit
    investor_count INTEGER,
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, fon_kodu)
);

CREATE INDEX IF NOT EXISTS idx_tefas_top_rank
  ON tefas_top_funds(fon_tipi, date, rank);
