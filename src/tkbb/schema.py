"""SQLite + D1 schema for the TKBB participation-bank digital lane.

Two tidy long tables mirroring web/migrations/0017_tkbb_stats.sql verbatim.
Values are stored in RAW source units (persons / count / TRY); the web layer
scales for display. Natural keys make re-ingestion idempotent.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS tkbb_digital_stats (
    period         TEXT NOT NULL,   -- 'YYYY-MM' quarter-end (Mar/Jun/Sep/Dec)
    metric         TEXT NOT NULL,   -- 'active_customers' | 'txn_volume' | 'txn_count' (+ variants)
    breakdown      TEXT NOT NULL,   -- 'total' | 'channel_mix' | 'channel' | 'segment' | 'category' | 'province'
    dim_slug       TEXT NOT NULL,   -- slugified dimension value; 'total' for scalars
    dim_tr         TEXT NOT NULL,   -- verbatim Turkish label ('' for scalars)
    unit           TEXT NOT NULL,   -- 'persons' | 'count' | 'try' (RAW source units)
    value          REAL,
    period_tr      TEXT NOT NULL,   -- verbatim Turboard filter label ('2025 4.Dönem')
    source_dashlet TEXT NOT NULL,   -- Turboard dashlet id
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, metric, breakdown, dim_slug)
);

CREATE INDEX IF NOT EXISTS idx_tkbb_digital_lookup
  ON tkbb_digital_stats(metric, breakdown, dim_slug, period);
"""

# Monthly remote-vs-branch acquisition. The public dashboard exposes only a
# rolling last-12-months window; rows accumulate here — never deleted.
ACQ_DDL = """
CREATE TABLE IF NOT EXISTS tkbb_acquisition_stats (
    period         TEXT NOT NULL,   -- 'YYYY-MM' (monthly)
    series         TEXT NOT NULL,   -- 'remote' | 'branch'
    measure        TEXT NOT NULL,   -- 'applications' | 'customers'
    measure_tr     TEXT NOT NULL,   -- measure alias verbatim from the dashboard definition
    value          REAL,
    source_dashlet TEXT NOT NULL,
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, series, measure)
);

CREATE INDEX IF NOT EXISTS idx_tkbb_acq_lookup
  ON tkbb_acquisition_stats(series, measure, period);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def init_acquisition_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ACQ_DDL)
    conn.commit()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/bddk_data.db")
    with sqlite3.connect(db) as conn:
        init_schema(conn)
        init_acquisition_schema(conn)
    print(f"Initialized tkbb_* schemas in {db}")
