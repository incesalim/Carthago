"""Incremental monthly BDDK refresh.

Finds the latest (year, month) already in the DB, probes BDDK for any
newer months that are actually published, and scrapes only those.

Idempotent: safe to run daily. `INSERT OR REPLACE` keyed on
(year, month, bank_type_code, item_order) ensures no duplicates even
across retries.

Run: python scripts/update_monthly.py
"""

from __future__ import annotations

import sys
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "archive" / "scrapers"))
sys.path.insert(0, str(ROOT))

import requests                                     # noqa: E402
from bddk_api_scraper import BDDKAPIScraper, BANK_TYPES  # noqa: E402

DB_PATH = ROOT / "data" / "bddk_data.db"

MONTHLY_PROBE_URL = "https://www.bddk.org.tr/BultenAylik/tr/Home/BasitRaporGetir"
PROBE_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0",
}


# ---------------------------------------------------------------------------
def latest_month_in_db() -> tuple[int, int]:
    with sqlite3.connect(DB_PATH) as c:
        row = c.execute(
            "SELECT year, month FROM balance_sheet "
            "ORDER BY year DESC, month DESC LIMIT 1"
        ).fetchone()
    return row if row else (2020, 0)


def month_iter(start: tuple[int, int], stop: tuple[int, int]):
    """Inclusive iterator (start, start+1, ..., stop)."""
    y, m = start
    while (y, m) <= stop:
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def is_published(year: int, month: int) -> bool:
    """Lightweight probe: fetch a single tiny response; is data returned?"""
    payload = {
        "tabloNo": "1", "yil": str(year), "ay": str(month),
        "paraBirimi": "TL", "taraf[0]": "10001",
    }
    try:
        r = requests.post(MONTHLY_PROBE_URL, headers=PROBE_HEADERS,
                          data=payload, timeout=20)
        r.raise_for_status()
        rows = r.json().get("Json", {}).get("data", {}).get("rows", [])
        return bool(rows)
    except Exception as e:
        print(f"  probe error for {year}-{month:02d}: {e}", flush=True)
        return False


# ---------------------------------------------------------------------------
def main():
    latest_y, latest_m = latest_month_in_db()
    print(f"Latest month in DB: {latest_y}-{latest_m:02d}", flush=True)

    # Candidate months: (latest+1) … current calendar month
    today = datetime.today()
    start_next = (latest_y, latest_m + 1) if latest_m < 12 else (latest_y + 1, 1)
    stop = (today.year, today.month)

    if start_next > stop:
        print("Nothing to check — DB is already at or past today's month.", flush=True)
        return

    candidates = list(month_iter(start_next, stop))
    print(f"Checking {len(candidates)} candidate months: "
          f"{candidates[0][0]}-{candidates[0][1]:02d} … "
          f"{candidates[-1][0]}-{candidates[-1][1]:02d}", flush=True)

    to_scrape = [(y, m) for y, m in candidates if is_published(y, m)]
    if not to_scrape:
        print("No new months published by BDDK yet.", flush=True)
        return

    print(f"Scraping {len(to_scrape)} new month(s): {to_scrape}", flush=True)
    scraper = BDDKAPIScraper(db_path=DB_PATH)
    scraper.connect_db()
    try:
        for y, m in to_scrape:
            print(f"\n===== {y}-{m:02d} =====", flush=True)
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rows = scraper.download_month(
                    year=y, month=m,
                    tables=list(range(1, 18)),
                    currencies=["TL"],
                    bank_types=BANK_TYPES,
                )
            print(f"{y}-{m:02d}: {rows:,} rows", flush=True)
    finally:
        scraper.close_db()
    print("\nMonthly update complete.", flush=True)


if __name__ == "__main__":
    main()
