"""Regulation primary record → `regulation_events` + `tcmb_card_rate_caps`.

Two light reads of official sources into the bulletin-lane SQLite, pushed to
D1 by push_to_d1 like every other table there:

  1. TCMB's card-rate caps — one page, compared row by row before writing.
  2. The Resmî Gazete — the last --days days' listings, every document read,
     the central bank's and the banking regulator's kept.

A source that fails is reported and the other still runs; both failing exits
non-zero, so a dead source is an error rather than a quiet `0 new`.

Run: python scripts/update_regulation.py [--days 9] [--db PATH]
                                         [--skip-gazette] [--skip-card-rates]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.regulation import card_rates, gazette                     # noqa: E402
from src.regulation.schema import init_schema                      # noqa: E402

DB_PATH = ROOT / "data" / "bddk_data.db"


def update_card_rates(conn) -> bool:
    session = card_rates.requests.Session()
    session.headers.update(card_rates.HEADERS)
    try:
        rows = card_rates.fetch_rows(session)
        if not rows:
            print("[card-rates] TCMB's page carried no dated rows", flush=True)
            return False
        counts = card_rates.store_rows(conn, rows)
    except Exception as exc:                                        # noqa: BLE001
        print(f"[card-rates] unreadable: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return False
    finally:
        session.close()
    conn.commit()
    print(f"[card-rates] {len(rows)} rows across {len({r['period_date'] for r in rows})} months: "
          f"new={counts['new']} changed={counts['changed']} same={counts['same']}", flush=True)
    for period, currency, tier, kind, rate in card_rates.changed_rates(rows):
        print(f"[card-rates]   {period} {currency} {tier} {kind} -> {rate}", flush=True)
    return True


def update_gazette(conn, days: int) -> bool:
    session = gazette.requests.Session()
    session.headers.update(gazette.HEADERS)
    today = dt.date.today()
    counts = {"new": 0, "changed": 0, "same": 0}
    days_read = documents = unreadable = 0
    try:
        for back in range(days):
            day = today - dt.timedelta(days=back)
            try:
                listing = gazette.fetch_listing(session, day)
            except Exception as exc:                                # noqa: BLE001
                print(f"[gazette] {day}: listing unreadable ({type(exc).__name__})", file=sys.stderr, flush=True)
                continue
            days_read += 1
            for doc in listing:
                documents += 1
                try:
                    lines = gazette.fetch_lines(session, doc)
                except Exception as exc:                            # noqa: BLE001
                    unreadable += 1
                    print(f"[gazette] {doc['document_id']}: unreadable ({type(exc).__name__})", file=sys.stderr, flush=True)
                    lines = None
                event = gazette.build_event(doc, lines, day)
                if event is not None:
                    counts[gazette.store_event(conn, event)] += 1
                time.sleep(gazette.REQUEST_PAUSE)
    finally:
        session.close()
    conn.commit()
    print(f"[gazette] {days_read} issue(s), {documents} documents read, {unreadable} unreadable: "
          f"events new={counts['new']} changed={counts['changed']} same={counts['same']}", flush=True)
    return days_read > 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--days", type=int, default=9,
                    help="how many days of the Resmî Gazete to read (default 9: one week plus the day itself)")
    ap.add_argument("--skip-gazette", action="store_true")
    ap.add_argument("--skip-card-rates", action="store_true")
    args = ap.parse_args()

    import sqlite3
    conn = sqlite3.connect(args.db)
    try:
        init_schema(conn)
        ok = []
        if not args.skip_card_rates:
            ok.append(update_card_rates(conn))
        if not args.skip_gazette:
            ok.append(update_gazette(conn, args.days))
    finally:
        conn.close()
    if ok and not any(ok):
        print("regulation update: every source failed", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
