"""Idempotent upsert for tkbb_digital_stats / tkbb_acquisition_stats."""
from __future__ import annotations

import sqlite3

from src.tkbb.acquisition import TkbbAcqStat
from src.tkbb.digital import TkbbStat


def upsert_stats(conn: sqlite3.Connection, stats: list[TkbbStat]) -> int:
    """INSERT OR REPLACE a batch of quarterly rows. ``downloaded_at`` is
    refreshed so the incremental D1 push picks them up."""
    if not stats:
        return 0
    rows = [
        (s.period, s.metric, s.breakdown, s.dim_slug, s.dim_tr,
         s.unit, s.value, s.period_tr, s.source_dashlet)
        for s in stats
    ]
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
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tkbb_acquisition_stats
           (period, series, measure, measure_tr, value, source_dashlet, downloaded_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
