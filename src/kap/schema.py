"""SQLite + D1 schema for the KAP ownership-structure lane.

One tidy long table: each row is one line of a bank's KAP Genel Bilgi Formu
§5 capital/ownership section (shareholder grid row, free-float line, or a
scalar like paid-in capital). The lane does a full per-bank replace on every
weekly run, so (bank_ticker, item, seq) is a stable natural key for the
idempotent D1 push.

``d1_pending_deletes`` is a staging-side outbox: when a bank's grid shrinks,
the loader queues matching DELETEs here and ``push_to_d1.py`` replays them
against D1 before its INSERTs (the push is otherwise INSERT OR REPLACE-only
and would leave orphan rows remotely).
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS kap_ownership (
    bank_ticker    TEXT NOT NULL,   -- our audit-lane ticker (AKBNK, ZIRAAT, …)
    bank_name      TEXT NOT NULL,   -- bank legal name as on KAP
    kap_company_id INTEGER NOT NULL,-- KAP company id (URL prefix, e.g. 2413)
    item           TEXT NOT NULL,   -- 'shareholder' | 'indirect_shareholder' |
                                    -- 'free_float' | 'paid_in_capital' | 'capital_ceiling'
    seq            INTEGER NOT NULL,-- row order within the source grid (0 for scalars)
    holder         TEXT,            -- shareholder / subsidiary name / free-float ISIN
    share_tl       REAL,            -- nominal amount; TL except subsidiary rows,
                                    -- where it is in `currency` (bank's capital share)
    ratio_pct      REAL,            -- % of capital
    voting_pct     REAL,            -- % of voting rights (direct shareholders only)
    as_of          TEXT,            -- ISO filing date of the form item
    currency       TEXT,            -- subsidiary rows: ISO code of share_tl (TRY/EUR/…)
    activity       TEXT,            -- subsidiary rows: scope of activities
    relation       TEXT,            -- subsidiary rows: Bağlı Ortaklık / İştirak / …
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, item, seq)
);

CREATE INDEX IF NOT EXISTS idx_kap_ownership_item
  ON kap_ownership(item, bank_ticker);

CREATE TABLE IF NOT EXISTS d1_pending_deletes (
    sql        TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# Columns added after the table first shipped (D1 migration 0007). CREATE IF
# NOT EXISTS won't touch an existing table, so ensure them here for staging
# DBs / R2 snapshots created before the column landed.
_LATER_COLUMNS = {"currency": "TEXT", "activity": "TEXT", "relation": "TEXT"}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    have = {c[1] for c in conn.execute("PRAGMA table_info(kap_ownership)")}
    for col, typ in _LATER_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE kap_ownership ADD COLUMN {col} {typ}")
    conn.commit()
