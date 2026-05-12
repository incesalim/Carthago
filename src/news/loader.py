"""Upsert helpers for news_items."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class NewsItem:
    source: str            # 'kap' | 'tcmb' | 'bddk'
    external_id: str       # source-stable id
    published_at: str      # ISO-8601 UTC
    title: str
    url: str
    language: str          # 'tr' | 'en'
    ticker: str | None = None
    category: str | None = None
    summary: str | None = None
    raw_json: str | None = None      # JSON blob; set automatically if None


def upsert_items(conn: sqlite3.Connection, items: list[NewsItem]) -> int:
    """INSERT OR REPLACE a batch of items. Returns the rowcount."""
    if not items:
        return 0
    rows = [
        (
            it.source, it.external_id, it.published_at,
            it.ticker, it.category, it.title, it.summary, it.url, it.language,
            it.raw_json or json.dumps(asdict(it), ensure_ascii=False, default=str),
        )
        for it in items
    ]
    cur = conn.executemany(
        """INSERT OR REPLACE INTO news_items
           (source, external_id, published_at, ticker, category, title,
            summary, url, language, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
