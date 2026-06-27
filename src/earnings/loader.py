"""Upsert helpers for bank_earnings."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class EarningsEvent:
    source: str             # 'kap' | 'ir'
    external_id: str        # stable id (see schema.py)
    ticker: str
    kind: str               # results_filing | presentation_deck | ...
    event_date: str         # ISO-8601 UTC
    url: str
    period: str | None = None
    title: str | None = None
    language: str | None = None
    raw_json: str | None = None


def upsert_events(conn: sqlite3.Connection, events: list[EarningsEvent]) -> int:
    """INSERT OR REPLACE a batch of earnings events (idempotent on the PK)."""
    if not events:
        return 0
    rows = [
        (
            e.source, e.external_id, e.ticker, e.period, e.kind, e.event_date,
            e.title, e.url, e.language,
            e.raw_json or json.dumps(asdict(e), ensure_ascii=False, default=str),
        )
        for e in events
    ]
    cur = conn.executemany(
        """INSERT OR REPLACE INTO bank_earnings
           (source, external_id, ticker, period, kind, event_date,
            title, url, language, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
