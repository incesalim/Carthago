-- 0015_bank_earnings
-- Per-bank, per-quarter earnings artifacts for BIST-listed banks. Two sources
-- feed one table:
--   source='kap' — results-filing events projected from the KAP disclosures
--     already ingested into news_items (kind='results_filing'). KAP carries
--     only the financial-report filing for Turkish banks — NOT earnings-call
--     invites or investor-presentation decks — so those kinds stay empty here.
--   source='ir'  — investor/earnings presentation decks discovered on banks' IR
--     sites (kind='presentation_deck'); see data/banks/investor_presentation_urls.json.
--
-- Powers the /earnings page and the "Earnings & Presentations" block on
-- /banks/[ticker]. Kept byte-identical to src/earnings/schema.py. Idempotent:
-- INSERT OR REPLACE on (source, external_id); fetched_at drives push_to_d1's
-- incremental sync (like news_items).

CREATE TABLE IF NOT EXISTS bank_earnings (
    source        TEXT NOT NULL,   -- 'kap' (results filing) | 'ir' (presentation deck)
    external_id   TEXT NOT NULL,   -- kap: '<TICKER>-<period>-results'; ir: '<TICKER>-<period>-presentation'
    ticker        TEXT NOT NULL,   -- BIST ticker (matches bddk_bank_list.json)
    period        TEXT,            -- 'YYYYQn' derived; NULL when underivable
    kind          TEXT NOT NULL,   -- results_filing | presentation_deck | call | presentation_filing | webcast_replay
    event_date    TEXT NOT NULL,   -- ISO-8601 UTC (KAP publishDate / quarter-end the deck covers)
    title         TEXT,            -- KAP subject or a synthesized deck label
    url           TEXT NOT NULL,   -- KAP filing URL or the presentation PDF URL
    language      TEXT,            -- 'tr' | 'en'
    raw_json      TEXT,            -- classifier evidence / discovery metadata
    fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_earnings_ticker
  ON bank_earnings(ticker, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_bank_earnings_kind
  ON bank_earnings(kind, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_bank_earnings_period
  ON bank_earnings(period, ticker);
