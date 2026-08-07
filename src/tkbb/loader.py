"""Change-only upserts for TKBB digital and acquisition statistics."""
from __future__ import annotations

import sqlite3

from src.tkbb.acquisition import TkbbAcqStat
from src.tkbb.digital import TkbbStat


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


def upsert_stats(conn: sqlite3.Connection, stats: list[TkbbStat]) -> int:
    """Write only new or revised quarterly rows."""
    if not stats:
        return 0
    rows = [
        (s.period, s.metric, s.breakdown, s.dim_slug, s.dim_tr,
         s.unit, s.value, s.period_tr, s.source_dashlet)
        for s in stats
    ]
    columns = (
        "period", "metric", "breakdown", "dim_slug", "dim_tr", "unit",
        "value", "period_tr", "source_dashlet",
    )
    rows = _changed_rows(
        conn, "tkbb_digital_stats", columns,
        ("period", "metric", "breakdown", "dim_slug"), rows,
    )
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tkbb_digital_stats
           (period, metric, breakdown, dim_slug, dim_tr,
            unit, value, period_tr, source_dashlet, downloaded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount


def upsert_acquisition(conn: sqlite3.Connection, stats: list[TkbbAcqStat]) -> int:
    """INSERT OR REPLACE monthly acquisition rows. Accumulates beyond the
    source's rolling 12-month window — never deletes."""
    if not stats:
        return 0
    rows = [
        (s.period, s.series, s.measure, s.measure_tr, s.value, s.source_dashlet)
        for s in stats
    ]
    columns = (
        "period", "series", "measure", "measure_tr", "value", "source_dashlet",
    )
    rows = _changed_rows(
        conn, "tkbb_acquisition_stats", columns,
        ("period", "series", "measure"), rows,
    )
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tkbb_acquisition_stats
           (period, series, measure, measure_tr, value, source_dashlet, downloaded_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
