"""News / qualitative-data sync — pull KAP + TCMB + BDDK + press into SQLite.

After this runs, scripts/push_to_d1.py syncs the new news_items rows to D1.
Designed for the GitHub Actions cron — no laptop dependency.

Sources: kap/tcmb/bddk are primary regulator + disclosure feeds; `press`
aggregates banking-sector journalism from TR financial-media RSS feeds
(data/news/press_feeds.json) — see src/news/sources/press.py.

Usage:
  python scripts/sync_news.py                # all sources
  python scripts/sync_news.py --kap-only     # for ad-hoc debugging
  python scripts/sync_news.py --press-only   # just the media feeds
  python scripts/sync_news.py --kap-days 7   # smaller KAP window
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news.loader import (  # noqa: E402
    items_missing_body,
    items_with_body_url,
    update_body,
    upsert_items,
)
from src.earnings.from_kap import events_from_kap  # noqa: E402
from src.earnings.loader import upsert_events  # noqa: E402
from src.earnings.schema import init_schema as init_earnings_schema  # noqa: E402
from src.news.schema import init_schema  # noqa: E402
from src.news.sources import bddk, google_news, kap, press, tcmb  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kap-only", action="store_true")
    ap.add_argument("--tcmb-only", action="store_true")
    ap.add_argument("--bddk-only", action="store_true")
    ap.add_argument("--press-only", action="store_true")
    ap.add_argument("--google-only", action="store_true")
    ap.add_argument("--google-max-decode", type=int, default=google_news.MAX_DECODE_PER_RUN,
                    help="Cap on Google News redirect-token decodes per run "
                         f"(default {google_news.MAX_DECODE_PER_RUN}); the rest "
                         "are picked up on subsequent runs")
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
    ap.add_argument("--refresh-bodies", action="store_true",
                    help="Re-fetch body_text for ALL tcmb/bddk items (not just "
                         "missing ones) and overwrite. Use after a fetch_body "
                         "change, e.g. adding table extraction. Failed/empty "
                         "fetches never clobber an existing body.")
    ap.add_argument("--body-workers", type=int, default=8,
                    help="Parallel detail-page fetchers (default 8)")
    ap.add_argument("--body-limit", type=int, default=None,
                    help="Cap on body-fetches per source per run (default unlimited)")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)

    only_one = (args.kap_only or args.tcmb_only or args.bddk_only
                or args.press_only or args.google_only)

    t0 = time.time()
    totals = {"kap": 0, "tcmb": 0, "bddk": 0, "press": 0, "google_news": 0}

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

        # Earnings events (tier 1): classify the KAP disclosures just stored into
        # results-filing events for the /earnings calendar. Pure reclassification
        # over local rows — no network. (Banks don't file call/presentation
        # invites on KAP, so only results filings are produced here.)
        print("[earnings] classifying KAP disclosures...")
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_earnings_schema(conn)
                n = upsert_events(conn, events_from_kap(conn))
            print(f"[earnings] upserted {n:>4d} earnings events from KAP")
        except Exception as e:
            print(f"[earnings] FAILED: {type(e).__name__}: {e}", flush=True)

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

    if not only_one or args.press_only:
        print("[press] fetching...")
        try:
            items = press.fetch()
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                upsert_items(conn, items)
                # Self-heal: drop stored items from outlets no longer in
                # press_feeds.json (e.g. Hürriyet, removed for a stale feed).
                # Keeps the snapshot from re-pushing them; the matching D1 rows
                # are deleted once by hand (the D1 push is insert-only).
                purged = _delete_unconfigured_press(conn)
            totals["press"] = len(items)
            print(f"[press] upserted {len(items):>4d} banking-sector press items"
                  + (f"; purged {purged} rows from removed feeds" if purged else ""))
        except Exception as e:
            print(f"[press] FAILED: {type(e).__name__}: {e}", flush=True)

    if not only_one or args.google_only:
        print("[google] fetching...")
        try:
            # news_items is the decode cache: skip items already resolved to a
            # real publisher URL, so we only ever decode new (or still-google)
            # links and never clobber a good URL.
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                decoded_ids = {
                    row[0] for row in conn.execute(
                        "SELECT external_id FROM news_items WHERE source = 'google_news' "
                        "AND url NOT LIKE 'https://news.google.com/%'"
                    )
                }
            items = google_news.fetch(decoded_ids=decoded_ids, max_decode=args.google_max_decode)
            with sqlite3.connect(str(DB_PATH)) as conn:
                init_schema(conn)
                upsert_items(conn, items)
                # Self-heal: drop google_news rows whose outlet is now also a
                # press feed (added after the item was stored), so the same
                # outlet isn't shown on both tabs.
                purged = _delete_overlapping_google(conn)
            totals["google_news"] = len(items)
            print(f"[google] upserted {len(items):>4d} google-news items"
                  + (f"; purged {purged} rows now covered by press" if purged else ""))
        except Exception as e:
            print(f"[google] FAILED: {type(e).__name__}: {e}", flush=True)

    # Body backfill — incremental: only fetch detail pages for rows that
    # don't yet have a body cached. Cheap on first run after the column
    # was added, near-free on every subsequent run.
    if not args.skip_bodies:
        for source_name, fetcher in [("tcmb", tcmb.fetch_body), ("bddk", bddk.fetch_body)]:
            if only_one and not getattr(args, f"{source_name}_only"):
                continue
            try:
                _backfill_bodies(source_name, fetcher, args.body_workers,
                                 args.body_limit, refresh=args.refresh_bodies)
            except Exception as e:
                print(f"[{source_name}-body] FAILED: {type(e).__name__}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\ntotal: {sum(totals.values())} items in {elapsed:.1f}s "
          f"(kap={totals['kap']} tcmb={totals['tcmb']} bddk={totals['bddk']} "
          f"press={totals['press']})")


def _backfill_bodies(source: str, fetcher, workers: int, limit: int | None,
                     refresh: bool = False) -> None:
    """Fetch and store body_text for rows of `source`.

    Default: only rows missing a body. With `refresh=True`: every row, to
    overwrite stale bodies after a fetch_body change. update_body only writes
    on a truthy result, so a failed re-fetch leaves the existing body intact.
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        pending = (items_with_body_url(conn, source, limit=limit) if refresh
                   else items_missing_body(conn, source, limit=limit))
    if not pending:
        print(f"[{source}-body] up to date")
        return
    verb = "re-fetching" if refresh else "fetching"
    print(f"[{source}-body] {verb} {len(pending)} detail pages × {workers} workers")
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


def _delete_unconfigured_press(conn: sqlite3.Connection) -> int:
    """Delete press rows whose outlet (stored in `category`) is no longer an
    enabled feed in press_feeds.json. Mirrors _delete_bddk_noise: the scraper
    already stops fetching the removed feed; this purges anything stored before
    the removal so it never re-pushes."""
    keep = press.enabled_outlets()
    rows = conn.execute(
        "SELECT external_id, category FROM news_items WHERE source = 'press'"
    ).fetchall()
    to_delete = [ext_id for ext_id, outlet in rows if (outlet or "") not in keep]
    if not to_delete:
        return 0
    conn.executemany(
        "DELETE FROM news_items WHERE source = 'press' AND external_id = ?",
        [(eid,) for eid in to_delete],
    )
    conn.commit()
    return len(to_delete)


def _delete_overlapping_google(conn: sqlite3.Connection) -> int:
    """Delete google_news rows whose publisher host is now covered by a press
    feed. The scraper already skips these hosts for new items; this purges
    anything stored before the press feed was added, so an outlet never appears
    on both /news and /news/google."""
    hosts = {google_news._host(u) for u in press.feed_urls()}
    hosts.discard(None)
    if not hosts:
        return 0
    rows = conn.execute(
        "SELECT external_id, raw_json FROM news_items WHERE source = 'google_news'"
    ).fetchall()
    to_delete = []
    for ext_id, raw in rows:
        try:
            host = (json.loads(raw) or {}).get("host") if raw else None
        except (json.JSONDecodeError, TypeError):
            host = None
        if host and host in hosts:
            to_delete.append(ext_id)
    if not to_delete:
        return 0
    conn.executemany(
        "DELETE FROM news_items WHERE source = 'google_news' AND external_id = ?",
        [(eid,) for eid in to_delete],
    )
    conn.commit()
    return len(to_delete)


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
