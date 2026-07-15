"""Telegram ping when a NEW BDDK weekly/monthly period was FETCHED this run.

The refresh workflow snapshots the latest weekly + monthly periods right after
restoring the R2 SQLite (i.e. BEFORE this run scrapes), then calls this after the
push. We compare "before" to what's in the DB now and notify only when something
new actually landed — so a routine run that found nothing published stays quiet
(no spam), and the ping means "published AND fetched", not "ran".

  python scripts/notify_new_bddk.py --before-weekly 2026-07-03 --before-monthly 202605
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import notify  # noqa: E402

DB = ROOT / "data" / "bddk_data.db"


def latest_periods(db_path: Path = DB) -> tuple[str, int]:
    """(latest weekly period_date 'YYYY-MM-DD', latest monthly as year*100+month)."""
    conn = sqlite3.connect(str(db_path))
    try:
        w = conn.execute("SELECT MAX(period_date) FROM weekly_series").fetchone()[0]
        m = conn.execute("SELECT MAX(year * 100 + month) FROM balance_sheet").fetchone()[0]
    finally:
        conn.close()
    return (w or ""), int(m or 0)


def new_messages(
    before_weekly: str, before_monthly: int, now_weekly: str, now_monthly: int
) -> list[str]:
    """The bulletins that advanced this run — one line each, or [] if none."""
    msgs: list[str] = []
    if now_weekly and now_weekly > (before_weekly or ""):
        msgs.append(f"Weekly bulletin — week ending {now_weekly}")
    if now_monthly and now_monthly > (before_monthly or 0):
        year, month = divmod(now_monthly, 100)
        msgs.append(f"Monthly bulletin — {year}-{month:02d}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-weekly", default="")
    ap.add_argument("--before-monthly", type=int, default=0)
    args = ap.parse_args()

    now_weekly, now_monthly = latest_periods()
    msgs = new_messages(args.before_weekly, args.before_monthly, now_weekly, now_monthly)
    if msgs:
        notify("📊 BDDK published & fetched:\n- " + "\n- ".join(msgs))
        print("notified:", msgs)
    else:
        print("no new BDDK periods this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
