"""Change-only upserts for TBB digital and acquisition statistics."""
from __future__ import annotations

import sqlite3

from src.tbb.acquisition import AcqStat
from src.tbb.parser import TbbStat


def _changed_rows(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    rows: list[tuple],
) -> list[tuple]:
    """Drop rows whose stored, non-stamp contents are already identical."""
    key_at = tuple(columns.index(column) for column in key_columns)
    existing = {
        tuple(row[i] for i in key_at): tuple(row)
        for row in conn.execute(f"SELECT {', '.join(columns)} FROM {table}")
    }
    return [
        row for row in rows
        if existing.get(tuple(row[i] for i in key_at)) != tuple(row)
    ]


def upsert_stats(conn: sqlite3.Connection, stats: list[TbbStat]) -> int:
    """Write only new or revised quarterly rows."""
    if not stats:
        return 0
    rows = [
        (s.period, s.channel, s.segment, s.section_code, s.section_tr,
         s.metric_path, s.metric_slug, s.unit, s.value, s.source_sheet)
        for s in stats
    ]
    columns = (
        "period", "channel", "segment", "section_code", "section_tr",
        "metric_path", "metric_slug", "unit", "value", "source_sheet",
    )
    rows = _changed_rows(
        conn, "tbb_digital_stats", columns,
        ("period", "channel", "segment", "section_code", "metric_slug", "unit"),
        rows,
    )
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tbb_digital_stats
           (period, channel, segment, section_code, section_tr,
            metric_path, metric_slug, unit, value, source_sheet, downloaded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


def upsert_acquisition(conn: sqlite3.Connection, stats: list[AcqStat]) -> int:
    """Write only new or revised remote-vs-branch acquisition rows."""
    if not stats:
        return 0
    rows = [(s.period, s.entity_type, s.method, s.method_tr, s.value) for s in stats]
    columns = ("period", "entity_type", "method", "method_tr", "value")
    rows = _changed_rows(
        conn, "tbb_acquisition_stats", columns,
        ("period", "entity_type", "method"), rows,
    )
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tbb_acquisition_stats
           (period, entity_type, method, method_tr, value, downloaded_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
