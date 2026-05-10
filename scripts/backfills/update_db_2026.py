"""
One-off driver to fetch newly available BDDK monthly data into the main DB.
Uses the archived API scraper (the one that actually populated the typed tables)
but points it at the real DB in data/bddk_data.db.

Run: python scripts/update_db_2026.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.bddk_api_scraper import BDDKAPIScraper, BANK_TYPES

DB_PATH = ROOT / "data" / "bddk_data.db"

# Months to fetch (verified available via probe)
MONTHS_TO_FETCH = [(2026, 1), (2026, 2)]
CURRENCIES = ["TL"]


def main():
    scraper = BDDKAPIScraper(db_path=DB_PATH)
    scraper.connect_db()
    total = 0
    try:
        for year, month in MONTHS_TO_FETCH:
            print(f"\n===== {year}-{month:02d} =====")
            n = scraper.download_month(
                year=year, month=month,
                tables=list(range(1, 18)),
                currencies=CURRENCIES,
                bank_types=BANK_TYPES,
            )
            total += n
            print(f"Month {year}-{month:02d}: {n} rows")
        print(f"\nTOTAL: {total} rows")
    finally:
        scraper.close_db()


if __name__ == "__main__":
    main()
