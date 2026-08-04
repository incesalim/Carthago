"""Idempotent upserts for the tefas_* aggregate tables.

All tables upsert via INSERT OR REPLACE with a refreshed ``downloaded_at`` so
the incremental D1 push picks the rows up — but only for rows whose values
actually moved. ``update_tefas.py`` re-fetches a trailing ``--days`` (7) window
on every daily run, so six of every seven days come back byte-identical;
rewriting them refreshed ``downloaded_at``, and ``push_to_d1`` (which windows on
exactly that column) then re-sent all of them to D1 with identical values. That
is the bug the EVDS scraper carried until 2026-07-27, where it cost ~17M rows
written/month against a 50M/month allowance. Comparing the stored tuple first is
the whole fix: an unchanged row keeps its old ``downloaded_at``, so the push
window never sees it, while a genuine revision still writes.
See docs/OPERATIONS.md -> D1 write budget.

``tefas_top_funds`` additionally replaces its (date, fon_tipi) partition: when a
re-ingest drops a fund out of the top 15, the stale code is queued in the
``d1_pending_deletes`` outbox so ``push_to_d1.py`` mirrors the delete remotely
(KAP pattern).
"""
from __future__ import annotations

import sqlite3

# (key columns, value columns) per table, in the order upsert_day receives them
# in each row tuple. Every tefas_* aggregate keys on (date, fon_tipi, <dimension>);
# the value columns are what a re-ingest may legitimately revise. `downloaded_at`
# is neither — it is the push window's clock, and must move only when a value does.
_COLUMNS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "tefas_manager_daily": (
        ("date", "fon_tipi", "manager"),
        ("aum_try", "fund_count", "investor_count"),
    ),
    "tefas_category_daily": (
        ("date", "fon_tipi", "category"),
        ("aum_try", "fund_count", "investor_count"),
    ),
    "tefas_allocation_daily": (
        ("date", "fon_tipi", "asset_class"),
        ("weighted_pct", "aum_base_try"),
    ),
    "tefas_top_funds": (
        ("date", "fon_tipi", "fon_kodu"),
        ("fon_unvan", "manager", "rank", "aum_try", "price", "investor_count"),
    ),
}

_UPSERTS = {
    table: (
        f"INSERT OR REPLACE INTO {table}"
        f" ({', '.join(keys + vals)}, downloaded_at)"
        f" VALUES ({', '.join('?' * (len(keys) + len(vals)))}, CURRENT_TIMESTAMP)"
    )
    for table, (keys, vals) in _COLUMNS.items()
}


def changed_rows(
    conn: sqlite3.Connection, table: str, rows: list[tuple]
) -> list[tuple]:
    """Return only the rows whose stored values differ from what we already hold.

    One read per (date, fon_tipi) partition, not per row: every row in a single
    ``upsert_day`` call shares that pair, so this is normally a single query.
    A key we have never seen has no entry and always counts as changed.
    """
    keys, vals = _COLUMNS[table]
    n = len(keys)
    cols = ", ".join(keys + vals)
    existing: dict[tuple, tuple] = {}
    for day, fon_tipi in {(r[0], r[1]) for r in rows}:
        for r in conn.execute(
            f"SELECT {cols} FROM {table} WHERE {keys[0]} = ? AND {keys[1]} = ?",
            (day, fon_tipi),
        ):
            existing[tuple(r[:n])] = tuple(r[n:])
    return [r for r in rows if existing.get(tuple(r[:n])) != tuple(r[n:])]


def upsert_day(conn: sqlite3.Connection, tables: dict[str, list[tuple]]) -> int:
    """Upsert one ``aggregate_day`` result. Commits once.

    Returns the number of rows actually written — which on a re-fetched window is
    far below the number of rows supplied, and is meant to be: a steady-state day
    that returns 0 means TEFAS restated nothing, not that the fetch failed.
    """
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
            # Filter BEFORE writing. The stale-partition sweep above still runs
            # over the full incoming set, so dropping unchanged rows here cannot
            # hide a fund that fell out of the top 15.
            fresh = changed_rows(conn, table, rows)
            if fresh:
                written += conn.executemany(_UPSERTS[table], fresh).rowcount
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
