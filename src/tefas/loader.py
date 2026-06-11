"""Idempotent upserts for the tefas_* aggregate tables.

All tables upsert via INSERT OR REPLACE with a refreshed ``downloaded_at`` so
the incremental D1 push picks the rows up. ``tefas_top_funds`` additionally
replaces its (date, fon_tipi) partition: when a re-ingest drops a fund out of
the top 15, the stale code is queued in the ``d1_pending_deletes`` outbox so
``push_to_d1.py`` mirrors the delete remotely (KAP pattern).
"""
from __future__ import annotations

import sqlite3

_UPSERTS = {
    "tefas_manager_daily": (
        "INSERT OR REPLACE INTO tefas_manager_daily"
        " (date, fon_tipi, manager, aum_try, fund_count, investor_count, downloaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
    ),
    "tefas_category_daily": (
        "INSERT OR REPLACE INTO tefas_category_daily"
        " (date, fon_tipi, category, aum_try, fund_count, investor_count, downloaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
    ),
    "tefas_allocation_daily": (
        "INSERT OR REPLACE INTO tefas_allocation_daily"
        " (date, fon_tipi, asset_class, weighted_pct, aum_base_try, downloaded_at)"
        " VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
    ),
    "tefas_top_funds": (
        "INSERT OR REPLACE INTO tefas_top_funds"
        " (date, fon_tipi, fon_kodu, fon_unvan, manager, rank, aum_try, price,"
        "  investor_count, downloaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
    ),
}


def upsert_day(conn: sqlite3.Connection, tables: dict[str, list[tuple]]) -> int:
    """Upsert one ``aggregate_day`` result. Commits once; returns rows written."""
    written = 0
    top_rows = tables.get("tefas_top_funds") or []
    if top_rows:
        day, fon_tipi = top_rows[0][0], top_rows[0][1]
        keep = {r[2] for r in top_rows}
        stale = [
            kodu for (kodu,) in conn.execute(
                "SELECT fon_kodu FROM tefas_top_funds WHERE date = ? AND fon_tipi = ?",
                (day, fon_tipi),
            ) if kodu not in keep
        ]
        if stale:
            conn.execute(
                "DELETE FROM tefas_top_funds WHERE date = ? AND fon_tipi = ?"
                " AND fon_kodu IN (%s)" % ",".join("?" * len(stale)),
                (day, fon_tipi, *stale),
            )
            conn.executemany(
                "INSERT INTO d1_pending_deletes (sql) VALUES (?)",
                [
                    ("DELETE FROM tefas_top_funds WHERE date='{0}' AND fon_tipi='{1}'"
                     " AND fon_kodu='{2}';".format(day, fon_tipi, kodu),)
                    for kodu in stale
                ],
            )
    for table, rows in tables.items():
        if rows:
            written += conn.executemany(_UPSERTS[table], rows).rowcount
    conn.commit()
    return written


def window_done(conn: sqlite3.Connection, fon_tipi: str, win_start: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM tefas_fetch_log WHERE fon_tipi = ? AND win_start = ?",
        (fon_tipi, win_start),
    ).fetchone() is not None


def mark_window(
    conn: sqlite3.Connection,
    fon_tipi: str,
    win_start: str,
    win_end: str,
    info_rows: int,
    alloc_rows: int,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tefas_fetch_log"
        " (fon_tipi, win_start, win_end, info_rows, alloc_rows, fetched_at)"
        " VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (fon_tipi, win_start, win_end, info_rows, alloc_rows),
    )
    conn.commit()
