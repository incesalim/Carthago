"""Fetch TEFAS fund-market data into the bulletin-lane SQLite, aggregated.

Pulls per-fund daily rows from the two tefas.gov.tr JSON endpoints (prices/AUM
and portfolio allocation), aggregates them at ingest (per-fund rows are never
persisted — see src/tefas/aggregate.py) and upserts the four ``tefas_*``
tables in ``data/bddk_data.db``. ``scripts/push_to_d1.py`` then syncs the
rows to Cloudflare D1.

Two modes:

- **Daily** (default): one trailing window of ``--days`` (7) per fund type —
  ~10–14 rate-limited requests, ≈2.5 min. Re-fetching the recent window every
  run self-heals TEFAS's T+1 publishing lag, weekend/holiday gaps and
  revisions via the idempotent upsert.
- **Backfill** (``--backfill --from … [--to …]``): consecutive 28-day windows,
  oldest→newest, resumable — completed windows are recorded in
  ``tefas_fetch_log`` and skipped on re-run. Windows are aligned from
  ``--from``, so resume with the SAME ``--from`` date. With ``--push-every K``
  the new rows are pushed to D1 every K windows (a single end-of-run push of
  the full history would generate an SQL file too large for wrangler).

The client paces requests at ~5.5/min (server limit ~6/min). Never run two
instances concurrently.

Usage:
  python scripts/update_tefas.py                                  # daily
  python scripts/update_tefas.py --backfill --from 2020-06-01 --push-every 15
  python scripts/update_tefas.py --backfill --from 2026-05-01 --to 2026-06-10
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.tefas.aggregate import aggregate_day                      # noqa: E402
from src.tefas.client import (                                     # noqa: E402
    FUND_TYPES,
    fetch_allocation,
    fetch_info,
    _session,
)
from src.tefas.loader import mark_window, upsert_day, window_done  # noqa: E402
from src.tefas.schema import init_schema                           # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
BACKFILL_WINDOW_DAYS = 28
TEFAS_TABLES = ("tefas_manager_daily,tefas_category_daily,"
                "tefas_allocation_daily,tefas_top_funds")


def process_window(conn, session, fon_tipi: str, start: date, end: date) -> tuple[int, int, int]:
    """Fetch + aggregate + upsert one (fund type, window).
    Returns (info_rows, alloc_rows, upserted)."""
    info = fetch_info(session, fon_tipi, start, end)
    alloc = fetch_allocation(session, fon_tipi, start, end)
    info_by_day: dict[str, list[dict]] = defaultdict(list)
    alloc_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in info:
        info_by_day[row["tarih"]].append(row)
    for row in alloc:
        alloc_by_day[row["tarih"]].append(row)
    upserted = 0
    for day in sorted(info_by_day):
        tables = aggregate_day(fon_tipi, day, info_by_day[day], alloc_by_day.get(day, []))
        upserted += upsert_day(conn, tables)
    return len(info), len(alloc), upserted


def push_tefas_tables(hours: int) -> None:
    """Sync the tefas_* tables to D1; raises on failure (a backfill must not
    keep accumulating unpushed rows past a broken push)."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "push_to_d1.py"),
           "--hours", str(hours), f"--only-tables={TEFAS_TABLES}"]
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    ap.add_argument("--days", type=int, default=7,
                    help="Daily mode: trailing window length (default 7)")
    ap.add_argument("--backfill", action="store_true",
                    help="Resumable historical backfill (needs --from)")
    ap.add_argument("--from", dest="date_from", default=None,
                    help="Backfill start date YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", default=None,
                    help="Backfill end date YYYY-MM-DD (default: today)")
    ap.add_argument("--types", default=",".join(FUND_TYPES),
                    help=f"Comma-separated fund types (default {','.join(FUND_TYPES)})")
    ap.add_argument("--push-every", type=int, default=0,
                    help="Backfill: push tefas_* tables to D1 every K windows (0 = never)")
    args = ap.parse_args()

    types = [t.strip().upper() for t in args.types.split(",") if t.strip()]
    unknown = [t for t in types if t not in FUND_TYPES]
    if unknown:
        print(f"ERROR: unknown fund type(s) {unknown}", file=sys.stderr)
        return 1

    today = date.today()
    if args.backfill:
        if not args.date_from:
            print("ERROR: --backfill requires --from YYYY-MM-DD", file=sys.stderr)
            return 1
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to) if args.date_to else today
        windows = []
        cur = start
        while cur <= end:
            windows.append((cur, min(cur + timedelta(days=BACKFILL_WINDOW_DAYS - 1), end)))
            cur += timedelta(days=BACKFILL_WINDOW_DAYS)
    else:
        windows = [(today - timedelta(days=args.days), today)]

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    session = _session()
    total_upserted = 0
    done_windows = 0
    with sqlite3.connect(str(db)) as conn:
        init_schema(conn)
        n_total = len(windows) * len(types)
        for w_start, w_end in windows:
            for fon_tipi in types:
                if args.backfill and window_done(conn, fon_tipi, w_start.isoformat()):
                    done_windows += 1
                    print(f"  [{done_windows}/{n_total}] {fon_tipi} {w_start}..{w_end}: "
                          "already fetched — skipped", flush=True)
                    continue
                n_info, n_alloc, upserted = process_window(
                    conn, session, fon_tipi, w_start, w_end)
                if args.backfill:
                    mark_window(conn, fon_tipi, w_start.isoformat(),
                                w_end.isoformat(), n_info, n_alloc)
                done_windows += 1
                total_upserted += upserted
                print(f"  [{done_windows}/{n_total}] {fon_tipi} {w_start}..{w_end}: "
                      f"{n_info} info + {n_alloc} alloc rows → {upserted} upserts",
                      flush=True)
                if (args.push_every and done_windows % args.push_every == 0
                        and total_upserted):
                    push_tefas_tables(hours=3)

        summary = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM tefas_manager_daily"
        ).fetchone()

    if args.push_every and total_upserted:
        push_tefas_tables(hours=3)

    print(f"\nDone. Upserted {total_upserted} aggregate rows this run; "
          f"tefas_manager_daily holds {summary[0]} rows "
          f"spanning {summary[1]}..{summary[2]}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
