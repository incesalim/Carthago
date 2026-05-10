"""Backfill BDDK monthly data for 2020-01 through 2023-12.

Uses the archived API scraper pointed at the main DB. Emits one line per
month to stdout so a Monitor can stream progress.

Run: python scripts/backfill_2020_2023.py
"""

from __future__ import annotations
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.bddk_api_scraper import BDDKAPIScraper, BANK_TYPES  # noqa: E402

DB_PATH = ROOT / "data" / "bddk_data.db"

START = (2020, 1)
END = (2023, 12)
CURRENCIES = ["TL"]


def month_iter(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def main():
    scraper = BDDKAPIScraper(db_path=DB_PATH)
    scraper.connect_db()

    total_months = sum(1 for _ in month_iter(START, END))
    done = 0
    grand_total_rows = 0
    started = time.time()

    print(f"BACKFILL start: {START[0]}-{START[1]:02d} -> {END[0]}-{END[1]:02d} "
          f"({total_months} months)", flush=True)

    try:
        for y, m in month_iter(START, END):
            t0 = time.time()
            # Suppress noisy per-request prints from the scraper by temporarily
            # redirecting its stdout — we only want one line per month here.
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rows = scraper.download_month(
                    year=y, month=m,
                    tables=list(range(1, 18)),
                    currencies=CURRENCIES,
                    bank_types=BANK_TYPES,
                )
            done += 1
            grand_total_rows += rows
            dt = time.time() - t0
            elapsed = time.time() - started
            eta = (elapsed / done) * (total_months - done) if done else 0
            print(
                f"[{done:>2}/{total_months}] {y}-{m:02d} "
                f"rows={rows:>6,}  took={dt:>5.1f}s  "
                f"elapsed={elapsed/60:>4.1f}m  eta={eta/60:>4.1f}m",
                flush=True,
            )
    except KeyboardInterrupt:
        print("INTERRUPTED", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        scraper.close_db()
        print(
            f"DONE  months={done}/{total_months}  rows={grand_total_rows:,}  "
            f"total_time={(time.time() - started)/60:.1f}m",
            flush=True,
        )


if __name__ == "__main__":
    main()
