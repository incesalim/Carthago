"""Incremental BDDK non-bank financial-sector refresh (BultenAylikBdmk).

Scrapes aggregate sector balance sheets for leasing / factoring / financing /
asset-management (VYŞ) into ``nonbank_balance_sheet``. Idempotent: INSERT OR
REPLACE keyed on (sector_code, year, month, item_order).

Modes:
    python scripts/update_nonbank.py                  # incremental (latest+1 → now)
    python scripts/update_nonbank.py --backfill 2008  # full history (CI; ~slow)
    python scripts/update_nonbank.py --year 2025 --month 12   # one period, all sectors

On a fresh table the incremental mode scrapes the CURRENT YEAR only (and says
so) — run ``--backfill`` once in CI for the full 2008→ history, per the
no-heavy-local-execution rule.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nonbank.scraper import (  # noqa: E402
    SECTORS, SECTORS_BY_CODE, is_quarter, open_db, scrape_sector,
)

DB_PATH = ROOT / "data" / "bddk_data.db"


def month_iter(start: tuple[int, int], stop: tuple[int, int]):
    """Inclusive ascending iterator over (year, month)."""
    y, m = start
    while (y, m) <= stop:
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def next_month(period: tuple[int, int]) -> tuple[int, int]:
    y, m = period
    return (y, m + 1) if m < 12 else (y + 1, 1)


def latest_period(conn, sector_code: str) -> tuple[int, int] | None:
    row = conn.execute(
        "SELECT year, month FROM nonbank_balance_sheet WHERE sector_code = ? "
        "ORDER BY year DESC, month DESC LIMIT 1",
        (sector_code,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, nargs="?", const=0, default=None,
                    metavar="START_YEAR",
                    help="Full history from START_YEAR (default: each sector's "
                         "first published year) to now.")
    ap.add_argument("--year", type=int, help="Single period: year (with --month).")
    ap.add_argument("--month", type=int, help="Single period: month (with --year).")
    ap.add_argument("--sectors", type=str, default=None,
                    help="Comma-separated sector codes (default all): "
                         "leasing,factoring,financing,amc")
    ap.add_argument("--db", type=str, default=str(DB_PATH))
    args = ap.parse_args()

    today = datetime.today()
    stop = (today.year, today.month)

    sectors = SECTORS
    if args.sectors:
        codes = [c.strip() for c in args.sectors.split(",") if c.strip()]
        sectors = [SECTORS_BY_CODE[c] for c in codes if c in SECTORS_BY_CODE]

    conn = open_db(args.db)
    try:
        grand = 0
        for sector in sectors:
            print(f"\n===== {sector['code']} ({sector['stem']}) =====", flush=True)

            if args.year and args.month:                       # single period
                if sector["cadence"] == "quarterly" and not is_quarter(args.month):
                    print(f"  skip — {sector['code']} is quarterly, "
                          f"{args.month} is not a quarter-end month", flush=True)
                    continue
                periods = [(args.year, args.month)]
                stop_early = False
            elif args.backfill is not None:                    # full history
                start_year = max(args.backfill or sector["start_year"],
                                 sector["start_year"])
                periods = list(month_iter((start_year, 1), stop))
                stop_early = False
            else:                                              # incremental
                latest = latest_period(conn, sector["code"])
                if latest is None:
                    start = (today.year, 1)
                    print(f"  no rows yet — scraping {today.year} only "
                          f"(run --backfill for full history)", flush=True)
                else:
                    start = next_month(latest)
                if start > stop:
                    print(f"  up to date (latest {latest})", flush=True)
                    continue
                periods = list(month_iter(start, stop))
                stop_early = True  # months are sequential; stop at first unpublished

            n = scrape_sector(conn, sector, periods,
                              stop_when_unpublished=stop_early)
            grand += n
            print(f"  {sector['code']} total: {n} rows", flush=True)

        print(f"\nNon-bank update complete: {grand:,} rows.", flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
