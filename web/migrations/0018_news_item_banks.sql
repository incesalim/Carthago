-- 0018: news_item_banks — which bank(s) a press/google_news item mentions
-- (Yahoo-style per-ticker news).
--
-- Junction table: one row per article × bank, so a story naming several
-- banks surfaces on each bank's /banks/[ticker] page. news_items.ticker
-- keeps its KAP semantics (the single bank a disclosure belongs to);
-- press/google tags live here instead.
--
-- Written by src/news/bank_tagger.py (deterministic alias-regex matcher,
-- data/news/bank_aliases.json) as a post-step of scripts/sync_news.py.
-- Kept byte-identical to the DDL in src/news/schema.py (the Python side
-- creates it in the local SQLite staging DB; this migration creates it in
-- D1). Idempotent: the tagger diffs and INSERT OR REPLACEs on the PK;
-- `fetched_at` drives push_to_d1.py's incremental sync (like news_items),
-- and untagged rows are removed via the d1_pending_deletes outbox.
CREATE TABLE IF NOT EXISTS news_item_banks (
    source        TEXT NOT NULL,            -- FK half -> news_items(source, external_id)
    external_id   TEXT NOT NULL,
    ticker        TEXT NOT NULL,            -- canonical bank ticker (kap_company_map universe)
    matched_in    TEXT NOT NULL,            -- 'title' | 'summary' (title = stronger signal)
    fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, external_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_nib_ticker
  ON news_item_banks(ticker);
