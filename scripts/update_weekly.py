"""Incremental weekly BDDK refresh.

The weekly JSON API always returns the most recent 13 weeks anchored at
`tarih=today`. Running one pass of every (item × bank × currency) at the
current anchor picks up any new weeks automatically. INSERT OR REPLACE
handles overlaps idempotently.

Also covers small gaps: if a week was missed (Monitor stopped, etc.) the
overlapping 13-week window usually heals it.

Run: python scripts/update_weekly.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.weekly_api_scraper import (          # noqa: E402
    BDDKWeeklyAPIScraper, PRIMARY_WEEKLY_CODES, CATEGORY_NAMES,
)

DB_PATH = ROOT / "data" / "bddk_data.db"
CATALOGUE_FILE = ROOT / "scripts" / "_weekly_catalogue.json"


def _ensure_catalogue() -> dict:
    """Regenerate the catalogue file if missing (scraper probe)."""
    if CATALOGUE_FILE.exists():
        raw = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
        return {int(k): [(c, n) for c, n in v] for k, v in raw.items()}

    # Regenerate by probing
    print("Catalogue missing — probing BDDK …", flush=True)
    import requests
    H = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://www.bddk.org.tr/BultenHaftalik"}
    URL = "https://www.bddk.org.tr/BultenHaftalik/tr/Home/KiyaslamaJsonGetir"

    catalogue = {}
    anchor = datetime.today().strftime("%d.%m.%Y")
    for cat in range(1, 8):
        catalogue[cat] = []
        for item in range(1, 60):
            cid = f"{cat}.0.{item}"
            payload = {"dil": "tr", "tarih": anchor, "id": cid,
                       "parabirimi": "TRY", "sutun": "3",
                       "tarafKodu": "10001", "gun": "90"}
            try:
                r = requests.post(URL, headers=H, data=payload, timeout=10)
                d = r.json()
                if d.get("XEkseni"):
                    name = d.get("Baslik", "").split(" (TRY)")[0].strip()
                    catalogue[cat].append((cid, name))
            except Exception:
                pass

    CATALOGUE_FILE.write_text(
        json.dumps({str(k): v for k, v in catalogue.items()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Catalogue saved with {sum(len(v) for v in catalogue.values())} items.",
          flush=True)
    return catalogue


def main():
    catalogue = _ensure_catalogue()

    scraper = BDDKWeeklyAPIScraper(DB_PATH)
    scraper.open()
    try:
        anchor = datetime.today().date()
        tarih = anchor.strftime("%d.%m.%Y")
        all_items = [(cat, cid, name) for cat, items in catalogue.items()
                     for (cid, name) in items]

        total = len(all_items) * len(PRIMARY_WEEKLY_CODES) * 3
        print(f"Refreshing latest 13 weeks — {total:,} calls "
              f"({len(all_items)} items × {len(PRIMARY_WEEKLY_CODES)} banks × 3 sutun)",
              flush=True)

        done = 0
        t0 = time.time()
        for (cat, cid, _) in all_items:
            slug = CATEGORY_NAMES.get(int(cat), f"cat{cat}")
            for taraf in PRIMARY_WEEKLY_CODES:
                for sutun in (1, 2, 3):
                    scraper.fetch_and_store(cid, slug, tarih, sutun, taraf)
                    done += 1
                    time.sleep(0.5)
                    if done % 500 == 0:
                        elapsed = time.time() - t0
                        eta = elapsed * (total - done) / done
                        print(f"[{done:>5}/{total}] elapsed={elapsed/60:.1f}m "
                              f"eta={eta/60:.1f}m  rows={scraper.stats['rows_inserted']:,}",
                              flush=True)

        print(f"\nWeekly update complete. "
              f"Elapsed {(time.time()-t0)/60:.1f}m  "
              f"rows={scraper.stats['rows_inserted']:,}  "
              f"empty={scraper.stats['empty']}  err={scraper.stats['errors']}",
              flush=True)
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
