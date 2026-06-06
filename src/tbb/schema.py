"""SQLite + D1 schema for the TBB digital-banking statistics lane.

One tidy long table: each row is a single (period, channel, segment, section,
metric, unit) measurement. The natural key makes the incremental D1 push and
cross-file backfill idempotent — re-ingesting a quarter (or a later file that
revises it) overwrites in place.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS tbb_digital_stats (
    period        TEXT NOT NULL,   -- 'YYYY-MM' quarter-end (Mar/Jun/Sep/Dec)
    channel       TEXT NOT NULL,   -- 'digital' | 'internet' | 'mobile'
    segment       TEXT NOT NULL,   -- 'individual' | 'corporate' | 'total'
    section_code  TEXT NOT NULL,   -- 'I' | 'II' | 'III.1' … 'III.6' | 'IV'
    section_tr    TEXT NOT NULL,   -- Turkish section name
    metric_path   TEXT NOT NULL,   -- '>'-joined Turkish header path
    metric_slug   TEXT NOT NULL,   -- ascii slug of metric_path (stable join key)
    unit          TEXT NOT NULL,   -- 'persons_thousands' | 'count_thousands' | 'volume_bn_try'
    value         REAL,
    source_sheet  TEXT,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period, channel, segment, section_code, metric_slug, unit)
);

CREATE INDEX IF NOT EXISTS idx_tbb_digital_lookup
  ON tbb_digital_stats(channel, segment, section_code, unit, period);
CREATE INDEX IF NOT EXISTS idx_tbb_digital_period
  ON tbb_digital_stats(period);
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
    print(f"Initialized tbb_digital_stats schema in {db}")
