"""Upsert helpers for bank_call_transcripts."""
from __future__ import annotations

import sqlite3

from src.transcripts.alphaspread import SOURCE, Call


def upsert_calls(conn: sqlite3.Connection, calls: list[Call],
                 source: str = SOURCE) -> int:
    """INSERT OR REPLACE a batch of calls (idempotent on the PK).

    A call with no parsed turns is skipped, not stored: an empty
    ``transcript_json`` would satisfy the NOT NULL and then render as a blank
    reader page, which reads as "the bank said nothing" rather than "we failed
    to parse it".
    """
    rows = [
        (
            source, c.bank_ticker, c.period, c.call_date, c.source_url,
            f"{c.period[4:]} {c.period[:4]} earnings call", "en",
            len(c.turns), c.word_count, c.speaker_count,
            c.analyst_turn_count, c.indiscernible_count, c.transcript_json(),
        )
        for c in calls if c.turns
    ]
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR REPLACE INTO bank_call_transcripts
           (source, bank_ticker, period, call_date, source_url, title, language,
            turn_count, word_count, speaker_count, analyst_turn_count,
            indiscernible_count, transcript_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


def existing_periods(conn: sqlite3.Connection, bank_ticker: str,
                     source: str = SOURCE) -> set[str]:
    """Periods already stored for a bank — lets a re-run skip refetching."""
    cur = conn.execute(
        "SELECT period FROM bank_call_transcripts WHERE source = ? AND bank_ticker = ?",
        (source, bank_ticker),
    )
    return {r[0] for r in cur.fetchall()}
