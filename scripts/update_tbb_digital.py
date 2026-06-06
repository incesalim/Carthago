"""Fetch TBB quarterly digital-banking statistics into SQLite.

Discovers the published quarterly reports, downloads each Excel workbook, parses
it into tidy ``tbb_digital_stats`` rows, and upserts them into the bulletin-lane
DB (``data/bddk_data.db``). After this runs, ``scripts/push_to_d1.py`` syncs the
new rows to Cloudflare D1.

Each workbook carries a trailing ~5 quarters, so the default run (latest 2
reports) refreshes the newest quarter and picks up TBB's revisions to recent
ones. Reports are processed oldest→newest so a later file's revised figures win
on the idempotent upsert (PK = period, channel, segment, section, metric, unit).

Usage:
  python scripts/update_tbb_digital.py                 # latest 2 reports
  python scripts/update_tbb_digital.py --all           # full history (backfill)
  python scripts/update_tbb_digital.py --start-year 2018 --all
  python scripts/update_tbb_digital.py --latest 1      # just the newest quarter
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.tbb.client import discover_reports, download_xls  # noqa: E402
from src.tbb.loader import upsert_stats                     # noqa: E402
from src.tbb.parser import parse_workbook                   # noqa: E402
from src.tbb.schema import init_schema                      # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    ap.add_argument("--start-year", type=int, default=None,
                    help="Earliest year to discover (default: current year - 1)")
    ap.add_argument("--end-year", type=int, default=None,
                    help="Latest year to discover (default: current year)")
    ap.add_argument("--latest", type=int, default=2,
                    help="Process only the newest N reports (default 2)")
    ap.add_argument("--all", action="store_true",
                    help="Process every discovered report (full backfill)")
    args = ap.parse_args()

    now_year = datetime.now().year
    end_year = args.end_year or now_year
    start_year = args.start_year or (2018 if args.all else now_year - 1)

    print(f"Discovering TBB digital reports {start_year}..{end_year} …", flush=True)
    reports = discover_reports(start_year, end_year)  # newest first, xls-verified
    if not reports:
        print("No reports found.", flush=True)
        return 0
    print(f"Found {len(reports)} reports: {', '.join(r.period for r in reports)}", flush=True)

    selected = reports if args.all else reports[: args.latest]
    # Process oldest→newest so revisions in newer files overwrite older values.
    selected = sorted(selected, key=lambda r: r.period)

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with sqlite3.connect(str(db)) as conn:
        init_schema(conn)
        with tempfile.TemporaryDirectory() as tmp:
            for rep in selected:
                path = download_xls(rep, tmp)
                if not path:
                    print(f"  {rep.period}: no Excel link — skipped", flush=True)
                    continue
                stats = parse_workbook(str(path))
                n = upsert_stats(conn, stats)
                periods = sorted({s.period for s in stats})
                print(f"  {rep.period}: parsed {len(stats)} rows "
                      f"(periods {periods[0]}..{periods[-1]}) → upserted {n}", flush=True)
                total += n
        rowcount = conn.execute("SELECT COUNT(*) FROM tbb_digital_stats").fetchone()[0]
        span = conn.execute(
            "SELECT MIN(period), MAX(period) FROM tbb_digital_stats"
        ).fetchone()
    print(f"\nDone. Upserted {total} rows this run; "
          f"table now holds {rowcount} rows spanning {span[0]}..{span[1]}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
