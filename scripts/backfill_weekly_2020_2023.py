"""Backfill BDDK weekly data for 2020-01 through 2024-01.

Complements backfill_weekly_2y.py, which covered 2024-01-26 onwards.

Run: python scripts/backfill_weekly_2020_2023.py
"""

from __future__ import annotations
import json
import sys
from datetime import date
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
    catalogue = {int(k): [(c, n) for c, n in v] for k, v in raw.items()}

    # Target window: 2020-01-01 → 2023-02-10 (meets existing data at 2023-02-03,
    # overlap of a few weeks is fine because INSERT OR REPLACE is idempotent).
    start = date(2020, 1, 1)
    end = date(2023, 2, 10)

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
