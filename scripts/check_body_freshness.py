#!/usr/bin/env python3
"""Guard: stored news bodies still match what the source page yields today.

Bodies are fetched once and never revisited — `_backfill_bodies` only selects
rows that are NULL or under 30 chars, so a body that is *present but truncated*
is frozen forever. That is not hypothetical: table extraction landed 2026-05-29
(`f875a47`) and every TCMB item scraped before it kept a table-less body, which
is how the regulation briefing lost the loan-growth caps and an 11-row FX
reserve-requirement table. Nothing failed; the numbers were simply absent.

This samples recent items, re-extracts with today's code, and alerts when the
live page yields materially more than we hold. It is the check that would have
caught that in May instead of two months later.

Read-only — it never writes a body. `sync_news.py --refresh-bodies` is the fix.

Usage:
  python scripts/check_body_freshness.py                 # sample + report
  python scripts/check_body_freshness.py --alert         # + Telegram on drift
  python scripts/check_body_freshness.py --limit 40 --source tcmb
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from notify import notify  # noqa: E402
from src.news.sources import bddk, tcmb  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
FETCHERS = {"tcmb": tcmb.fetch_body, "bddk": bddk.fetch_body}

# A body is "stale" when the live page yields this much more than we stored.
# Absolute floor as well as ratio: a 12-char gain is a layout table appearing in
# the markup, not lost content, and flagging those would train everyone to
# ignore this alert.
MIN_GAIN_CHARS = 200
MIN_GAIN_RATIO = 1.15


_SQL = ("SELECT external_id, url, length(body_text) AS have, "
        "substr(published_at,1,10) AS d FROM news_items "
        "WHERE source = '{src}' AND body_text IS NOT NULL AND url IS NOT NULL "
        "ORDER BY published_at DESC LIMIT {n}")


def sample_local(conn: sqlite3.Connection, source: str, limit: int) -> list[tuple]:
    return [(r[0], r[1], len(r[2] or ""), r[3]) for r in conn.execute(
        """SELECT external_id, url, body_text, substr(published_at, 1, 10)
           FROM news_items
           WHERE source = ? AND body_text IS NOT NULL AND url IS NOT NULL
           ORDER BY published_at DESC LIMIT ?""",
        (source, limit),
    )]


def sample_d1(source: str, limit: int) -> list[tuple]:
    """Same sample, read from D1 — healthcheck.yml never pulls the 86 MB snapshot,
    so the local staging DB isn't there. Only the stored LENGTH is needed, which
    keeps the query tiny."""
    res = subprocess.run(
        ["npx", "--yes", "wrangler", "d1", "execute", "bddk-data", "--remote",
         "--json", "--command", _SQL.format(src=source, n=int(limit))],
        cwd=str(REPO_ROOT / "web"), capture_output=True, text=True,
        shell=os.name == "nt",
    )
    if res.returncode != 0:
        raise RuntimeError(f"wrangler exit {res.returncode}: {res.stderr[-300:]}")
    data = json.loads(res.stdout)
    rows = (data[0] if isinstance(data, list) else data)["results"]
    return [(r["external_id"], r["url"], int(r["have"] or 0), r["d"]) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sorted(FETCHERS), action="append",
                    help="Limit to one source (repeatable). Default: all.")
    ap.add_argument("--limit", type=int, default=25,
                    help="Newest N items per source to probe (default 25).")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--alert", action="store_true", help="Telegram/Discord on drift")
    ap.add_argument("--d1", action="store_true",
                    help="Read the sample from D1 instead of the local staging DB "
                         "(healthcheck.yml has no snapshot).")
    args = ap.parse_args()

    if not args.d1 and not DB_PATH.exists():
        print(f"no local DB at {DB_PATH} — pass --d1 to read from D1", file=sys.stderr)
        return 0

    sources = args.source or sorted(FETCHERS)
    stale: list[str] = []
    checked = failed = 0

    for src in sources:
        if args.d1:
            rows = sample_d1(src, args.limit)
        else:
            with sqlite3.connect(str(DB_PATH)) as conn:
                rows = sample_local(conn, src, args.limit)
        if not rows:
            continue
        fetcher = FETCHERS[src]

        def probe(row):
            ext_id, url, have, date = row
            try:
                return row, fetcher(url), None
            except Exception as e:  # noqa: BLE001 — a dead page is not our bug
                return row, None, f"{type(e).__name__}"

        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            for (ext_id, url, have, date), live, err in ex.map(probe, rows):
                checked += 1
                if err or not live:
                    failed += 1
                    continue
                now = len(live)
                if now - have >= MIN_GAIN_CHARS and now >= have * MIN_GAIN_RATIO:
                    stale.append(f"{src}:{ext_id} ({date}) {have} → {now} chars")

    print(f"[body-freshness] probed {checked} items across {', '.join(sources)}"
          f" ({failed} unreachable)")
    if not stale:
        print("[body-freshness] all sampled bodies are current")
        return 0

    print(f"[body-freshness] {len(stale)} STALE:")
    for s in stale:
        print(f"  {s}")
    msg = (f"⚠️ {len(stale)} stored news bodies are stale — the live pages yield "
           f"materially more than we hold. Fix: dispatch refresh-news-daily.yml "
           f"with refresh_bodies=true.\n" + "\n".join(f"• {s}" for s in stale[:15]))
    if args.alert:
        notify(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
