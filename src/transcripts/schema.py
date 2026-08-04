"""SQLite + D1 schema for the earnings-call transcript lane.

One table, ``bank_call_transcripts`` — one row per bank per call. The speaker
turns live in ``transcript_json`` rather than a child table on purpose: a call
is only ever read whole, and D1 bills rows *written*, so 146 fat rows cost
~1/25th of the ~3,650 thin ones a turns table would have needed.

The DDL here is kept byte-identical to
``web/migrations/0036_bank_call_transcripts.sql`` so a local SQLite snapshot and
the remote D1 agree (``push_to_d1`` relies on it).
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS bank_call_transcripts (
    source              TEXT NOT NULL,     -- 'alphaspread' (room for a second transcriber)
    bank_ticker         TEXT NOT NULL,     -- internal code, joins banks.ticker
    period              TEXT NOT NULL,     -- 'YYYYQn' as the source labels the call
    call_date           TEXT,              -- 'YYYY-MM-DD'; NULL when the page omits it
    source_url          TEXT NOT NULL,
    title               TEXT,
    language            TEXT,              -- 'en' (these are the English calls)
    turn_count          INTEGER,           -- speaker turns parsed
    word_count          INTEGER,           -- words across all turns
    speaker_count       INTEGER,           -- distinct named speakers
    analyst_turn_count  INTEGER,           -- turns the source tagged role='analyst'
    indiscernible_count INTEGER,           -- '[indiscernible]' markers — attribution quality
    transcript_json     TEXT NOT NULL,     -- [{seq, speaker, role, text}]
    fetched_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, bank_ticker, period)
);

CREATE INDEX IF NOT EXISTS idx_bank_call_transcripts_bank
  ON bank_call_transcripts(bank_ticker, period DESC);
CREATE INDEX IF NOT EXISTS idx_bank_call_transcripts_date
  ON bank_call_transcripts(call_date DESC);
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
    print(f"Initialized bank_call_transcripts schema in {db}")
