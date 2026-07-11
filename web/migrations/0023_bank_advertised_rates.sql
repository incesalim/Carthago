-- 0023_bank_advertised_rates
-- Per-bank ADVERTISED (posted-to-new-customers) lending & deposit rates.
--
-- WHY: the pipeline had no per-bank *advertised* rate. TCMB/EVDS (evds_series:
-- TP.KTFTUK / TP.KTF17 / TP.KTF12 / TP.TRY.MT06) publish loan/deposit rates only
-- at SECTOR granularity; the audited P&L (heatmap.ts margin engine) gives each
-- bank's *realized* effective yield/cost — a different basis. This table holds the
-- third tier: what each bank offers new customers right now, scraped weekly from
-- two public comparison pages (loans → doviz.com, deposits → hangikredi).
--
-- Two shapes share the table:
--   POINT rate (loans)    → `rate` set, rate_min/rate_max NULL, rate_basis 'monthly'
--   rate BAND  (deposits) → rate_min/rate_max set, `rate` NULL, rate_basis 'annual'
-- (TR banks quote loans MONTHLY and deposits ANNUALLY — rate_basis records which,
-- so the web layer never has to guess.)
--
-- Columns:
--   source         'doviz.com' | 'hangikredi'
--   rate_type      loan_consumer | loan_mortgage | loan_vehicle | deposit_tl
--   raw_bank_name  bank label verbatim from the page (natural key)
--   bank_ticker    resolved canonical code (banks.ticker); NULL if not in the universe
--   product_name   campaign/product label ('' for deposit bands)
--   rate           POINT rate, % (loans)
--   rate_min/max   advertised BAND, % (deposits)
--   term_min/max   eligibility band, with term_unit 'months' (loans) | 'days' (deposits)
--   amount_min/max eligible principal band, TRY (deposits)
--   snapshot_date  'YYYY-MM-DD' capture day — snapshots accrete history
--
-- Natural key uses raw_bank_name (always present; bank_ticker is NULL for
-- non-universe brands) + snapshot_date, so a re-run on the same day is idempotent
-- while a new day appends. Synced by push_to_d1.py on `downloaded_at`.
-- Mirrors src/rates/schema.py verbatim.

CREATE TABLE IF NOT EXISTS bank_advertised_rates (
    source          TEXT NOT NULL,
    rate_type       TEXT NOT NULL,
    raw_bank_name   TEXT NOT NULL,
    bank_ticker     TEXT,
    product_name    TEXT NOT NULL DEFAULT '',
    currency        TEXT NOT NULL DEFAULT 'TRY',
    rate            REAL,
    rate_min        REAL,
    rate_max        REAL,
    rate_basis      TEXT NOT NULL,
    term_min        INTEGER,
    term_max        INTEGER,
    term_unit       TEXT,
    amount_min      REAL,
    amount_max      REAL,
    snapshot_date   TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, rate_type, raw_bank_name, product_name, currency, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_adv_rates_type_bank
  ON bank_advertised_rates(rate_type, bank_ticker);
CREATE INDEX IF NOT EXISTS idx_adv_rates_snapshot
  ON bank_advertised_rates(snapshot_date);
