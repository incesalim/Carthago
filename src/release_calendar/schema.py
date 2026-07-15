"""SQLite + D1 schema for the release-calendar lane.

One long table of SCHEDULED events, mirroring web/migrations/0025_release_calendar.sql
verbatim. Only scraped events live here (the derived BDDK/BRSA cadence rows stay
computed in web/app/lib/ahead.ts). `source` is 'tcmb' today; TÜİK data-release
dates would land here later with source='tuik' and no schema change.

Natural key (source, kind, event_date) — one row per event, so a re-scrape is
idempotent via INSERT OR REPLACE.
"""
from __future__ import annotations

import sqlite3

# Column semantics are documented in web/migrations/0025_release_calendar.sql.
# Kept comment-free inside the parens so both sides stay byte-comparable (and so
# scripts/check_schema_naming.py doesn't read a trailing `--` as a column name).
DDL = """
CREATE TABLE IF NOT EXISTS release_calendar (
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    event_date    TEXT NOT NULL,
    title         TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, kind, event_date)
);

CREATE INDEX IF NOT EXISTS idx_release_calendar_date ON release_calendar(event_date);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()
