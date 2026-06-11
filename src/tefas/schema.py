"""SQLite + D1 schema for the TEFAS fund-market lane.

Four skinny aggregate tables — per-fund raw rows are aggregated at ingest and
never persisted (see ``aggregate.py``). AUM is stored in raw TL (the web lib
rescales, same as the digital lane). ``tefas_fetch_log`` is staging-side only
(backfill resume bookkeeping) and must NOT be pushed to D1; the D1 migration
``web/migrations/0007_tefas_funds.sql`` mirrors everything else.

``tefas_top_funds`` partitions (date, fon_tipi) are fully replaced on
re-ingest; stale fund codes are queued in the ``d1_pending_deletes`` outbox
(KAP pattern) so the INSERT OR REPLACE-only D1 push can't leave orphans.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS tefas_manager_daily (
    date           TEXT NOT NULL,   -- 'YYYY-MM-DD' trading day
    fon_tipi       TEXT NOT NULL,   -- 'YAT'|'EMK'|'BYF'|'GYF'|'GSYF'
    manager        TEXT NOT NULL,   -- normalize.extract_manager(fonUnvan)
    aum_try        REAL,            -- Σ portfoyBuyukluk, raw TL
    fund_count     INTEGER,
    investor_count INTEGER,         -- Σ kisiSayisi (double-counts multi-fund investors)
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, manager)
);
CREATE INDEX IF NOT EXISTS idx_tefas_manager_tipi
  ON tefas_manager_daily(fon_tipi, date);

CREATE TABLE IF NOT EXISTS tefas_allocation_daily (
    date          TEXT NOT NULL,
    fon_tipi      TEXT NOT NULL,
    asset_class   TEXT NOT NULL,    -- normalize.ASSET_CLASSES
    weighted_pct  REAL,             -- AUM-weighted %, can exceed 0..100 (repo borrowing)
    aum_base_try  REAL,             -- covered AUM the weighting ran over, raw TL
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, asset_class)
);

CREATE TABLE IF NOT EXISTS tefas_category_daily (
    date           TEXT NOT NULL,
    fon_tipi       TEXT NOT NULL,
    category       TEXT NOT NULL,   -- normalize.categorize_fund(fonUnvan)
    aum_try        REAL,
    fund_count     INTEGER,
    investor_count INTEGER,
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, fon_tipi, fon_kodu)
);
CREATE INDEX IF NOT EXISTS idx_tefas_top_rank
  ON tefas_top_funds(fon_tipi, date, rank);

-- Staging-side only: one row per completed backfill window (resume marker).
CREATE TABLE IF NOT EXISTS tefas_fetch_log (
    fon_tipi   TEXT NOT NULL,
    win_start  TEXT NOT NULL,   -- 'YYYY-MM-DD'
    win_end    TEXT NOT NULL,
    info_rows  INTEGER,
    alloc_rows INTEGER,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fon_tipi, win_start)
);

-- Shared staging-side outbox (created by the KAP lane too; IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS d1_pending_deletes (
    sql        TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    print(f"Initialized tefas_* schema in {db}")
