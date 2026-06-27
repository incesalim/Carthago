"""SQLite + D1 schema for the earnings lane.

One table, ``bank_earnings`` — a per-bank, per-quarter timeline of earnings
artifacts. Two sources feed it:

* ``source='kap'`` — results filings projected from classified ``news_items``
  KAP rows (kind ``results_filing``). The full disclosure body stays in
  ``news_items``; this table holds only the back-link + the derived period.
* ``source='ir'`` — investor/earnings presentation decks discovered on banks'
  IR sites (kind ``presentation_deck``).

The DDL here is kept byte-identical to ``web/migrations/0015_bank_earnings.sql``
so a local SQLite snapshot and the remote D1 agree.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS bank_earnings (
    source        TEXT NOT NULL,   -- 'kap' (results filing) | 'ir' (presentation deck)
    external_id   TEXT NOT NULL,   -- kap: '<TICKER>-<period>-results'; ir: '<TICKER>-<period>-presentation'
    ticker        TEXT NOT NULL,   -- BIST ticker (matches bddk_bank_list.json)
    period        TEXT,            -- 'YYYYQn' derived; NULL when underivable
    kind          TEXT NOT NULL,   -- results_filing | presentation_deck | call | presentation_filing | webcast_replay
    event_date    TEXT NOT NULL,   -- ISO-8601 UTC (KAP publishDate / discovery date)
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
    print(f"Initialized bank_earnings schema in {db}")
