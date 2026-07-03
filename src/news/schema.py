"""SQLite + D1 schema for the qualitative-data layer.

Three synced tables:
- `news_items` — one row per KAP/TCMB/BDDK disclosure or press release.
- `news_item_banks` — bank-mention tags for press/google_news items
  (one row per article × bank; see src/news/bank_tagger.py). Mirrored in
  web/migrations/0018_news_item_banks.sql — keep the DDL byte-identical.
- `regulation_briefings` — weekly Kimi-generated thematic summaries
  over recent TCMB+BDDK news items.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS news_items (
    source        TEXT NOT NULL,            -- 'kap'|'tcmb'|'bddk'|'press'|'google_news'
    external_id   TEXT NOT NULL,            -- source-stable id (KAP disclosureIndex,
                                            --   TCMB ANO code, BDDK Duyuru id,
                                            --   press/google_news link or guid hash)
    published_at  TEXT NOT NULL,            -- ISO-8601 UTC; if source provides
                                            --   only date, '00:00:00' is used
    ticker        TEXT,                     -- BIST ticker if applicable (KAP)
    category      TEXT,                     -- source-specific category string
    title         TEXT NOT NULL,
    summary       TEXT,                     -- short body / first paragraph
    body_text     TEXT,                     -- full extracted body (TCMB/BDDK detail page)
    url           TEXT NOT NULL,            -- canonical link to the original
    language      TEXT NOT NULL,            -- 'tr' | 'en'
    raw_json      TEXT,                     -- json blob of the source record
    fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_news_published
  ON news_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_ticker
  ON news_items(ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source
  ON news_items(source, published_at DESC);

-- Which bank(s) a press/google_news item mentions (Yahoo-style per-ticker
-- news). Written by src/news/bank_tagger.py as a sync_news post-step;
-- `fetched_at` drives push_to_d1's incremental sync (like news_items).
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

-- Shared staging-side outbox (created by the KAP/TEFAS/faaliyet lanes too;
-- IF NOT EXISTS). bank_tagger queues junction-row DELETEs here when an alias
-- change untags an item, so the INSERT OR REPLACE-only D1 push can't leave
-- orphan tags remotely.
CREATE TABLE IF NOT EXISTS d1_pending_deletes (
    sql        TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regulation_briefings (
    generated_at    TEXT NOT NULL PRIMARY KEY,
    window_days     INTEGER NOT NULL,
    item_count      INTEGER NOT NULL,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    raw_response    TEXT,
    fetched_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Authoritative annual baseline: TCMB's "Monetary Policy for YYYY" document
-- (annex tables = the regulatory regime in force at the start of the year).
-- The briefing summarizer grounds on the latest row, then layers the raw
-- feed on top. Python-only (the web never reads it), so it is not synced to
-- D1 — it travels in the R2 SQLite snapshot.
-- Single-row guard so the weekly briefing run can no-op when its inputs
-- (feed items + baseline + prompt version) are unchanged — avoids burning LLM
-- calls to regenerate identical output in quiet weeks. Local-only; not synced.
CREATE TABLE IF NOT EXISTS briefing_input_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    input_hash  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regulation_baseline (
    year          INTEGER NOT NULL PRIMARY KEY,  -- policy year the doc covers
    title         TEXT NOT NULL,
    source_url    TEXT,                           -- where it was fetched from
    content       TEXT NOT NULL,                  -- extracted text (annex tables + body)
    content_hash  TEXT NOT NULL,                  -- sha256 of content; skip re-ingest if unchanged
    fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


if __name__ == "__main__":
    import sys
    from pathlib import Path
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/bddk_data.db")
    with sqlite3.connect(db) as conn:
        init_schema(conn)
    print(f"Initialized news_items schema in {db}")
