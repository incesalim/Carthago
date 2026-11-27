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
    BDDKWeeklyAPIScraper, PRIMARY_WEEKLY_CODES, CATEGORY_NAMES, HEADERS, URL,
    columns_for,
)
from src.scrapers._http import bddk_verify             # noqa: E402

DB_PATH = ROOT / "data" / "bddk_data.db"
CATALOGUE_FILE = ROOT / "scripts" / "_weekly_catalogue.json"

# How far to look for charts in a table. The bulletin's largest prints 45; the
# old bound of 59 was assumed, not measured, and a 46th chart in that table
# would have been invisible. A table is closed after this many empty ids in a
# row, which is what keeps the probe from walking to the bound every run.
PROBE_ITEM_LIMIT = 200
PROBE_MISS_STOP = 40


def _chart_is_live(d: dict) -> bool:
    """True for anything that returns dates. Zeros are data.

    An undefined id and a retired id — 9.0.1 … 9.0.10 are the pre-2023
    numbering of the FX-position rows — both come back with empty axes, and
    that is the whole test. A chart returning twelve zeros is NOT excluded:
    FX-protected deposits (4.0.12) are zero across the current window because
    the stock has wound down, and a first version of this probe dropped it and
    four charts of table 7 with it, which would have ended each series at its
    last non-zero week instead of showing the decline.

    The tenth table (the maturity split, all zero since 11.12.2020) is kept out
    by not being in CATEGORY_NAMES, not by a rule here.
    """
    return bool(d.get("XEkseni"))


def _probe_catalogue() -> dict:
    """Ask BDDK which charts each table prints, today."""
    import requests
    catalogue: dict = {}
    session = requests.Session()
    session.headers.update(HEADERS)
    session.verify = bddk_verify()
    anchor = datetime.today().strftime("%d.%m.%Y")
    for cat in CATEGORY_NAMES:
        catalogue[cat] = []
        misses = 0
        for item in range(1, PROBE_ITEM_LIMIT + 1):
            cid = f"{cat}.0.{item}"
            payload = {"dil": "tr", "tarih": anchor, "id": cid,
                       "parabirimi": "TRY", "sutun": "3",
                       "tarafKodu": "10001", "gun": "90"}
            try:
                r = session.post(URL, data=payload, timeout=10)
                live = _chart_is_live(r.json())
            except Exception:
                live = False
            if live:
                misses = 0
                d = r.json()
                name = d.get("Baslik", "").split(" (TRY)")[0].strip()
                catalogue[cat].append((cid, name))
            else:
                misses += 1
                if misses >= PROBE_MISS_STOP:
                    break
            time.sleep(0.2)
    return catalogue


def _ensure_catalogue() -> dict:
    """The catalogue of live charts per table, probing BDDK when needed.

    The file is a local cache and nothing more: a fresh checkout (every CI
    run) has none and probes. A file that predates a table is regenerated
    rather than trusted — adding categories 8 and 9 would otherwise have
    changed nothing on a machine that already held the seven.
    """
    if CATALOGUE_FILE.exists():
        try:
            raw = json.loads(CATALOGUE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        if raw is not None and set(raw) == {str(c) for c in CATEGORY_NAMES}:
            return {int(k): [(c, n) for c, n in v] for k, v in raw.items()}

    print("Catalogue missing or stale — probing BDDK …", flush=True)
    catalogue = _probe_catalogue()
    CATALOGUE_FILE.write_text(
        json.dumps({str(k): v for k, v in catalogue.items()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Catalogue saved with {sum(len(v) for v in catalogue.values())} items "
          f"across {len(catalogue)} tables.", flush=True)
    return catalogue


def _latest_week_in_db(scraper) -> str | None:
    row = scraper.conn.execute(
        "SELECT MAX(period_date) FROM weekly_series"
    ).fetchone()
    return row[0] if row and row[0] else None


def _latest_week_on_api(anchor_tarih: str) -> str | None:
    """One probe call to see the newest available Friday on BDDK."""
    import requests
    session = requests.Session()
    session.headers.update(HEADERS)
    payload = {"dil": "tr", "tarih": anchor_tarih, "id": "1.0.1",
               "parabirimi": "TRY", "sutun": "3",
               "tarafKodu": "10001", "gun": "90"}
    r = session.post(
        URL,
        data=payload, timeout=20, verify=bddk_verify(),
    )
    xs = r.json().get("XEkseni", [])
    if not xs:
        return None
    d, m, y = xs[-1].split(".")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def main():
    catalogue = _ensure_catalogue()

    scraper = BDDKWeeklyAPIScraper(DB_PATH)
    scraper.open()
    try:
        # Heal before the early-exit probe so historical gaps close even on
        # runs where BDDK has published nothing new.
        healed = scraper.heal_missing_totals()
        if healed:
            print(f"Healed {healed} missing TOTAL rows (TL+FX).", flush=True)

        anchor = datetime.today().date()
        tarih = anchor.strftime("%d.%m.%Y")

        # ---- Early-exit probe ----
        db_latest = _latest_week_in_db(scraper)
        api_latest = _latest_week_on_api(tarih)
        print(f"DB latest week:  {db_latest}", flush=True)
        print(f"API latest week: {api_latest}", flush=True)
        if db_latest and api_latest and db_latest >= api_latest:
            print("No new week published by BDDK — nothing to scrape.", flush=True)
            return

        all_items = [(cat, cid, name) for cat, items in catalogue.items()
                     for (cid, name) in items]

        total = (sum(len(columns_for(int(cat))) for cat, _c, _n in all_items)
                 * len(PRIMARY_WEEKLY_CODES))
        print(f"Refreshing latest 13 weeks — {total:,} calls "
              f"({len(all_items)} items × {len(PRIMARY_WEEKLY_CODES)} banks × "
              f"1-3 sutun)", flush=True)

        done = 0
        t0 = time.time()
        for (cat, cid, _) in all_items:
            slug = CATEGORY_NAMES.get(int(cat), f"cat{cat}")
            for taraf in PRIMARY_WEEKLY_CODES:
                for sutun in columns_for(int(cat)):
                    scraper.fetch_and_store(cid, slug, tarih, sutun, taraf)
                    done += 1
                    time.sleep(0.5)
                    if done % 500 == 0:
                        elapsed = time.time() - t0
                        eta = elapsed * (total - done) / done
                        print(f"[{done:>5}/{total}] elapsed={elapsed/60:.1f}m "
                              f"eta={eta/60:.1f}m  rows={scraper.stats['rows_inserted']:,}",
                              flush=True)

        healed = scraper.heal_missing_totals()
        if healed:
            print(f"Healed {healed} missing TOTAL rows (TL+FX) post-scrape.",
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
