"""Fetch TKBB quarterly participation-bank digital statistics into SQLite.

Pulls the "Dijital Bankacılık İstatistikleri" Turboard dashboard behind TKBB's
Veri Peteği (see src/tkbb/turboard.py for the API recipe), one period-filter
value at a time, and upserts tidy ``tkbb_digital_stats`` rows into the
bulletin-lane DB. After this runs, ``scripts/push_to_d1.py`` syncs to D1.

The default run is incremental: it fetches the periods missing from the local
DB plus the newest stored period (revision safety). On an empty table that
means the FULL 2020Q1→present backfill (~25 periods × 11 dashlets ≈ 275 GETs,
a few minutes at the default throttle) — no separate backfill mode.

Usage:
  python scripts/update_tkbb_digital.py            # incremental (auto-backfills)
  python scripts/update_tkbb_digital.py --all      # re-fetch every period
  python scripts/update_tkbb_digital.py --sleep 1  # slower throttle
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

from src.tkbb.digital import (  # noqa: E402
    PERIOD_FILTER_ID,
    fetch_period,
    period_from_label,
    verify_dashboard,
)
from src.tkbb.loader import upsert_stats     # noqa: E402
from src.tkbb.schema import init_schema      # noqa: E402
from src.tkbb.turboard import _session, get_filter_values  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    ap.add_argument("--all", action="store_true",
                    help="Re-fetch every published period (not just missing ones)")
    ap.add_argument("--sleep", type=float, default=0.5,
                    help="Seconds between periods (politeness throttle)")
    args = ap.parse_args()

    session = _session()

    print("Verifying dashboard registry …", flush=True)
    for warning in verify_dashboard(session=session):
        print(f"  [warn] {warning}", flush=True)

    labels = get_filter_values(PERIOD_FILTER_ID, session=session)
    parsed = []
    for label in labels:
        period = period_from_label(label)
        if period is None:
            print(f"  [warn] unparseable period label {label!r} — skipped", flush=True)
            continue
        parsed.append((period, label))
    parsed.sort()  # oldest→newest so revisions in later fetches win
    print(f"Live periods: {len(parsed)} "
          f"({parsed[0][0]}..{parsed[-1][0]})" if parsed else "No periods.",
          flush=True)
    if not parsed:
        return 0

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with sqlite3.connect(str(db)) as conn:
        init_schema(conn)
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM tkbb_digital_stats")}
        if args.all:
            selected = parsed
        else:
            newest_stored = max(have) if have else None
            selected = [(p, lbl) for p, lbl in parsed
                        if p not in have or p == newest_stored]
        if not selected:
            print("Nothing to fetch — table is current.", flush=True)
        for period, label in selected:
            stats = fetch_period(label, session=session)
            n = upsert_stats(conn, stats)
            print(f"  {period} ({label}): {len(stats)} rows → upserted {n}",
                  flush=True)
            total += n
            time.sleep(args.sleep)
        rowcount = conn.execute(
            "SELECT COUNT(*) FROM tkbb_digital_stats").fetchone()[0]
        span = conn.execute(
            "SELECT MIN(period), MAX(period) FROM tkbb_digital_stats").fetchone()
    print(f"\nDone. Upserted {total} rows this run; "
          f"table now holds {rowcount} rows spanning {span[0]}..{span[1]}.",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
