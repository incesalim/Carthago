"""Backfill 2 years of BDDK weekly data via the JSON API.

Emits one progress line every 500 calls (Monitor-friendly).

Run: python scripts/backfill_weekly_2y.py
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.weekly_api_scraper import (
    BDDKWeeklyAPIScraper,
    PRIMARY_WEEKLY_CODES,
)


DB_PATH = ROOT / "data" / "bddk_data.db"
CATALOGUE_FILE = ROOT / "scripts" / "_weekly_catalogue.json"


def main():
    if not CATALOGUE_FILE.exists():
        print(f"Missing catalogue file: {CATALOGUE_FILE}", flush=True)
        sys.exit(1)

    raw = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
    # JSON keys are strings — cast to int
    catalogue = {int(k): [(c, n) for c, n in v] for k, v in raw.items()}

    # Target window: last 2 years, ending today
    end = datetime.today().date()
    start = end - timedelta(days=365 * 2)

    scraper = BDDKWeeklyAPIScraper(DB_PATH)
    scraper.open()
    try:
        scraper.backfill(
            catalogue=catalogue,
            start=start,
            end=end,
            bank_codes_weekly=PRIMARY_WEEKLY_CODES,
            sutuns=(1, 2, 3),
        )
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
