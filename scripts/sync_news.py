"""News / qualitative-data sync — pull KAP + TCMB + BDDK into local SQLite.

After this runs, scripts/push_to_d1.py syncs the new news_items rows to D1.
Designed for the GitHub Actions cron — no laptop dependency.

Usage:
  python scripts/sync_news.py                # all three sources
  python scripts/sync_news.py --kap-only     # for ad-hoc debugging
  python scripts/sync_news.py --kap-days 7   # smaller KAP window
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news.loader import upsert_items  # noqa: E402
from src.news.schema import init_schema  # noqa: E402
from src.news.sources import bddk, kap, tcmb  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kap-only", action="store_true")
    ap.add_argument("--tcmb-only", action="store_true")
    ap.add_argument("--bddk-only", action="store_true")
    ap.add_argument("--kap-days", type=int, default=30,
                    help="KAP look-back window in days (default 30)")
    ap.add_argument("--tcmb-years", type=int, nargs="+", default=None,
                    help="Years to fetch from TCMB (default: current year)")
    ap.add_argument("--bddk-limit", type=int, default=200,
                    help="Max BDDK rows from the announcement list (default 200)")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)

    only_one = args.kap_only or args.tcmb_only or args.bddk_only

    t0 = time.time()
    totals = {"kap": 0, "tcmb": 0, "bddk": 0}

    if not only_one or args.kap_only:
        print("[kap] fetching...")
        try:
            items = kap.fetch(days_back=args.kap_days)
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                upsert_items(conn, items)
            totals["kap"] = len(items)
            print(f"[kap]  upserted {len(items):>4d} bank disclosures (last {args.kap_days}d)")
        except Exception as e:
            print(f"[kap]  FAILED: {type(e).__name__}: {e}", flush=True)

    if not only_one or args.tcmb_only:
        print("[tcmb] fetching...")
        try:
            items = tcmb.fetch(years=args.tcmb_years)
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                upsert_items(conn, items)
            totals["tcmb"] = len(items)
            print(f"[tcmb] upserted {len(items):>4d} press releases")
        except Exception as e:
            print(f"[tcmb] FAILED: {type(e).__name__}: {e}", flush=True)

    if not only_one or args.bddk_only:
        print("[bddk] fetching...")
        try:
            items = bddk.fetch(limit=args.bddk_limit)
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                upsert_items(conn, items)
            totals["bddk"] = len(items)
            print(f"[bddk] upserted {len(items):>4d} duyurus (latest {args.bddk_limit})")
        except Exception as e:
            print(f"[bddk] FAILED: {type(e).__name__}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\ntotal: {sum(totals.values())} items in {elapsed:.1f}s "
          f"(kap={totals['kap']} tcmb={totals['tcmb']} bddk={totals['bddk']})")


if __name__ == "__main__":
    main()
