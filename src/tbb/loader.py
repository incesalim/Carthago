"""Idempotent upsert for tbb_digital_stats / tbb_acquisition_stats."""
from __future__ import annotations

import sqlite3

from src.tbb.acquisition import AcqStat
from src.tbb.parser import TbbStat


def upsert_stats(conn: sqlite3.Connection, stats: list[TbbStat]) -> int:
    """INSERT OR REPLACE a batch of parsed rows. ``downloaded_at`` is refreshed
    so the incremental D1 push picks them up."""
    if not stats:
        return 0
    rows = [
        (s.period, s.channel, s.segment, s.section_code, s.section_tr,
         s.metric_path, s.metric_slug, s.unit, s.value, s.source_sheet)
        for s in stats
    ]
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
    """INSERT OR REPLACE remote-vs-branch acquisition rows. ``downloaded_at`` is
    refreshed so the incremental D1 push picks them up."""
    if not stats:
        return 0
    rows = [(s.period, s.entity_type, s.method, s.method_tr, s.value) for s in stats]
    cur = conn.executemany(
        """INSERT OR REPLACE INTO tbb_acquisition_stats
           (period, entity_type, method, method_tr, value, downloaded_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        rows,
    )
    conn.commit()
    return cur.rowcount
