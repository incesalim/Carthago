"""Upsert helpers for news_items."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass


@dataclass
class NewsItem:
    source: str            # 'kap' | 'tcmb' | 'bddk' | 'press' | 'google_news'
    external_id: str       # source-stable id
    published_at: str      # ISO-8601 UTC
    title: str
    url: str
    language: str          # 'tr' | 'en'
    ticker: str | None = None
    category: str | None = None
    summary: str | None = None
    body_text: str | None = None     # full extracted body — populated by source-specific fetch_body()
    raw_json: str | None = None      # JSON blob; set automatically if None


def upsert_items(conn: sqlite3.Connection, items: list[NewsItem]) -> int:
    """INSERT OR REPLACE a batch of items. Preserves any existing body_text
    if the new item doesn't carry one (so list-only resyncs don't clobber
    bodies fetched by an earlier detail pass)."""
    if not items:
        return 0
    # Pull existing body_text for items missing one in the new batch
    existing: dict[tuple[str, str], str | None] = {}
    needs_existing = [(it.source, it.external_id) for it in items if it.body_text is None]
    if needs_existing:
        placeholders = ",".join(["(?, ?)"] * len(needs_existing))
        flat = [v for pair in needs_existing for v in pair]
        rows = conn.execute(
            f"""SELECT source, external_id, body_text FROM news_items
                WHERE (source, external_id) IN (VALUES {placeholders})""",
            flat,
        ).fetchall()
        for src, ext, body in rows:
            existing[(src, ext)] = body

    rows = []
    for it in items:
        body = it.body_text if it.body_text is not None else existing.get((it.source, it.external_id))
        rows.append((
            it.source, it.external_id, it.published_at,
            it.ticker, it.category, it.title, it.summary, body, it.url, it.language,
            it.raw_json or json.dumps(asdict(it), ensure_ascii=False, default=str),
        ))
    cur = conn.executemany(
        """INSERT OR REPLACE INTO news_items
           (source, external_id, published_at, ticker, category, title,
            summary, body_text, url, language, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


def items_missing_body(
    conn: sqlite3.Connection,
    source: str,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Return [(external_id, url), …] for items of `source` that don't yet
    have a non-empty body_text. Used to drive the body-fetch backfill."""
    sql = """SELECT external_id, url FROM news_items
             WHERE source = ?
               AND (body_text IS NULL OR length(body_text) < 30)
             ORDER BY published_at DESC"""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return [(row[0], row[1]) for row in conn.execute(sql, (source,))]


def items_with_body_url(
    conn: sqlite3.Connection,
    source: str,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Return [(external_id, url), …] for ALL items of `source` (regardless of
    whether a body is already cached). Drives a forced body re-scrape, e.g.
    after the extractor learns to capture a new block type (tables)."""
    sql = """SELECT external_id, url FROM news_items
             WHERE source = ?
             ORDER BY published_at DESC"""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return [(row[0], row[1]) for row in conn.execute(sql, (source,))]


# A re-fetch that comes back materially shorter is far more likely to be a page
# that changed shape, an interstitial, or a partial render than genuine editorial
# deletion — and overwriting on that basis destroys content we cannot recover
# except from the source we just failed to read properly. Allow a little slack
# for whitespace/boilerplate churn.
_SHRINK_FLOOR_RATIO = 0.9
_SHRINK_FLOOR_CHARS = 100


def update_body(
    conn: sqlite3.Connection,
    source: str,
    external_id: str,
    body_text: str,
) -> bool:
    """Store a re-fetched body. Returns False (and writes nothing) if the new
    body is materially shorter than what we already hold."""
    row = conn.execute(
        "SELECT length(body_text) FROM news_items WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()
    have = int(row[0] or 0) if row else 0
    now = len(body_text or "")
    if have and now < have * _SHRINK_FLOOR_RATIO and (have - now) > _SHRINK_FLOOR_CHARS:
        print(f"[body] SKIP {source}:{external_id} — refetch shrank {have} → {now} chars",
              flush=True)
        return False
    # Bump fetched_at so the incremental D1 push (which filters on fetched_at)
    # picks up body-only refreshes — UPDATE wouldn't otherwise touch it.
    conn.execute(
        "UPDATE news_items SET body_text = ?, fetched_at = CURRENT_TIMESTAMP "
        "WHERE source = ? AND external_id = ?",
        (body_text, source, external_id),
    )
    conn.commit()
    return True
