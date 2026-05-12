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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news.loader import items_missing_body, update_body, upsert_items  # noqa: E402
from src.news.schema import init_schema  # noqa: E402
from src.news.sources import bddk, kap, tcmb  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kap-only", action="store_true")
    ap.add_argument("--tcmb-only", action="store_true")
    ap.add_argument("--bddk-only", action="store_true")
    ap.add_argument("--kap-days", type=int, default=90,
                    help="KAP look-back window in days (default 90)")
    ap.add_argument("--tcmb-years-back", type=int, default=5,
                    help="How many calendar years of TCMB press releases to fetch (default 5)")
    ap.add_argument("--tcmb-years", type=int, nargs="+", default=None,
                    help="Explicit TCMB year list (overrides --tcmb-years-back)")
    ap.add_argument("--bddk-limit", type=int, default=600,
                    help="Max BDDK rows from the announcement list (default 600 ≈ 5+ years)")
    ap.add_argument("--skip-bodies", action="store_true",
                    help="Skip the per-item body backfill")
    ap.add_argument("--body-workers", type=int, default=8,
                    help="Parallel detail-page fetchers (default 8)")
    ap.add_argument("--body-limit", type=int, default=None,
                    help="Cap on body-fetches per source per run (default unlimited)")
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
            items = tcmb.fetch(years=args.tcmb_years, years_back=args.tcmb_years_back)
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
                # Self-heal: drop any historical rows that match the current
                # BDDK noise patterns (e.g. data-publication notices, internal
                # HR posts). Patterns can evolve over time; this keeps the
                # cache in sync without manual cleanup.
                deleted = _delete_bddk_noise(conn)
            totals["bddk"] = len(items)
            print(f"[bddk] upserted {len(items):>4d} duyurus (latest {args.bddk_limit})"
                  + (f"; purged {deleted} legacy-noise rows" if deleted else ""))
        except Exception as e:
            print(f"[bddk] FAILED: {type(e).__name__}: {e}", flush=True)

    # Body backfill — incremental: only fetch detail pages for rows that
    # don't yet have a body cached. Cheap on first run after the column
    # was added, near-free on every subsequent run.
    if not args.skip_bodies:
        for source_name, fetcher in [("tcmb", tcmb.fetch_body), ("bddk", bddk.fetch_body)]:
            if only_one and not getattr(args, f"{source_name}_only"):
                continue
            try:
                _backfill_bodies(source_name, fetcher, args.body_workers, args.body_limit)
            except Exception as e:
                print(f"[{source_name}-body] FAILED: {type(e).__name__}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\ntotal: {sum(totals.values())} items in {elapsed:.1f}s "
          f"(kap={totals['kap']} tcmb={totals['tcmb']} bddk={totals['bddk']})")


def _backfill_bodies(source: str, fetcher, workers: int, limit: int | None) -> None:
    """Fetch and store body_text for any rows of `source` that don't have one."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        pending = items_missing_body(conn, source, limit=limit)
    if not pending:
        print(f"[{source}-body] up to date")
        return
    print(f"[{source}-body] fetching {len(pending)} detail pages × {workers} workers")
    ok = fail = 0
    with sqlite3.connect(str(DB_PATH)) as conn, \
         ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetcher, url): (ext, url) for ext, url in pending}
        for fut in as_completed(futures):
            ext_id, url = futures[fut]
            try:
                body = fut.result()
            except Exception as e:
                fail += 1
                print(f"  [FAIL] {ext_id}: {type(e).__name__}: {e}", flush=True)
                continue
            if body:
                update_body(conn, source, ext_id, body)
                ok += 1
            else:
                fail += 1
    print(f"[{source}-body] ok={ok} fail={fail}")


def _delete_bddk_noise(conn: sqlite3.Connection) -> int:
    """Apply bddk.NOISE_PATTERNS as DELETEs to existing rows. The scraper
    already filters new ones; this cleans up anything that slipped in
    before the pattern was added."""
    rows = conn.execute(
        "SELECT external_id, title FROM news_items WHERE source = 'bddk'"
    ).fetchall()
    to_delete = [ext_id for ext_id, title in rows if bddk.is_noise(title or "")]
    if not to_delete:
        return 0
    conn.executemany(
        "DELETE FROM news_items WHERE source = 'bddk' AND external_id = ?",
        [(eid,) for eid in to_delete],
    )
    conn.commit()
    return len(to_delete)


if __name__ == "__main__":
    main()
