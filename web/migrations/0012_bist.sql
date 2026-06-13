-- 0012_bist
-- Borsa İstanbul (BIST) equity-market data via the Yahoo Finance chart API.
-- Three tables, all idempotent (INSERT OR REPLACE on the composite/primary key,
-- so push_to_d1's conflict-detection behaves identically):
--   * bist_prices    — daily OHLCV for the 12 BIST-listed banks AND the market
--                      indices (XU100, XBANK). kind distinguishes the two.
--   * bist_dividends — cash dividend events (banks only) for trailing-12m yield.
--   * bist_shares    — shares outstanding per bank (for market cap = close ×
--                      shares). Changes rarely; refreshed best-effort each run
--                      from Yahoo with data/banks/bist_shares.json as fallback.
-- Mirrors evds_series conventions: lowercase snake_case, downloaded_at for
-- incremental D1 sync, indexes on the dashboard read paths.

CREATE TABLE IF NOT EXISTS bist_prices (
    symbol        TEXT NOT NULL,   -- bank ticker (GARAN) or index code (XU100)
    period_date   DATE NOT NULL,   -- trading day, 'YYYY-MM-DD'
    open_price    REAL,
    high_price    REAL,
    low_price     REAL,
    close_price   REAL,
    volume        REAL,
    kind          TEXT,            -- 'bank' | 'index'
    label         TEXT,            -- friendly name (Garanti BBVA / BIST 100)
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, period_date)
);

CREATE INDEX IF NOT EXISTS idx_bist_prices_symbol ON bist_prices(symbol, period_date);
CREATE INDEX IF NOT EXISTS idx_bist_prices_kind   ON bist_prices(kind, period_date);

CREATE TABLE IF NOT EXISTS bist_dividends (
    symbol        TEXT NOT NULL,   -- bank ticker (indices pay no dividends)
    ex_date       DATE NOT NULL,   -- ex-dividend date, 'YYYY-MM-DD'
    amount        REAL,            -- cash dividend per share, TRY
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS bist_shares (
    symbol             TEXT PRIMARY KEY,  -- bank ticker
    shares_outstanding REAL,
    nominal            REAL,              -- nominal value per share, TRY
    as_of              DATE,
    source             TEXT,
    downloaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
