"""SQLite + D1 schema for the regulation lane.

Two synced tables, both additive, both keyed on their natural key so a re-run
is idempotent:

- `regulation_events` — one row per document the central bank or the banking
  regulator published in the Resmî Gazete (Official Gazette). The date is the
  Gazette's publication date. `summary` is the opening of the document's own
  text and is NULL when the document carries no text layer — a scanned board
  decision has a title and a link and nothing else, and that is recorded as a
  NULL, not as an empty string.
- `tcmb_card_rate_caps` — the maximum interest rates TCMB sets for credit-card
  and overdraft-account transactions, one row per effective date × currency ×
  debt tier × rate kind. The tier thresholds are VALUES in the row, not part of
  the column names, because TCMB has moved them before.

Mirrors web/migrations/0056_regulation_events.sql verbatim.
"""
from __future__ import annotations

import sqlite3

# Comment-free inside the parens so both sides stay byte-comparable (and so
# scripts/check_schema_naming.py does not read a trailing `--` as a column name).
DDL = """
CREATE TABLE IF NOT EXISTS regulation_events (
    document_id TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    issuer      TEXT NOT NULL,
    instrument  TEXT,
    title       TEXT NOT NULL,
    summary     TEXT,
    gazette_no  TEXT,
    source_url  TEXT NOT NULL,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id)
);

CREATE INDEX IF NOT EXISTS idx_regulation_events_date ON regulation_events(event_date);

CREATE TABLE IF NOT EXISTS tcmb_card_rate_caps (
    period_date     TEXT NOT NULL,
    currency        TEXT NOT NULL,
    tier            TEXT NOT NULL,
    rate_kind       TEXT NOT NULL,
    rate            REAL,
    tier_floor_tl   REAL,
    tier_ceiling_tl REAL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period_date, currency, tier, rate_kind)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()
