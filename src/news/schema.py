"""SQLite + D1 schema for the qualitative-data layer.

One table: `news_items`. Each row is one disclosure or press release
from KAP (Public Disclosure Platform), TCMB (CBRT), or BDDK (banking
regulator). Idempotent ingestion via (source, external_id) PK.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS news_items (
    source        TEXT NOT NULL,            -- 'kap' | 'tcmb' | 'bddk'
    external_id   TEXT NOT NULL,            -- source-stable id (KAP disclosureIndex,
                                            --   TCMB ANO code, BDDK Duyuru id)
    published_at  TEXT NOT NULL,            -- ISO-8601 UTC; if source provides
                                            --   only date, '00:00:00' is used
    ticker        TEXT,                     -- BIST ticker if applicable (KAP)
    category      TEXT,                     -- source-specific category string
    title         TEXT NOT NULL,
    summary       TEXT,                     -- short body / first paragraph
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
