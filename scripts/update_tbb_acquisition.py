"""Fetch TBB remote-vs-branch customer-acquisition statistics into SQLite.

Downloads the newest "Uzaktan ve Şubeden Müşteri Edinim İstatistikleri" workbook,
parses its monthly series into tidy ``tbb_acquisition_stats`` rows, and upserts
them into the bulletin-lane DB (``data/bddk_data.db``). After this runs,
``scripts/push_to_d1.py`` syncs the new rows to Cloudflare D1.

Each monthly workbook is **cumulative** (it carries the full history Mayıs 2021 →
latest), so a single download refreshes the whole series; the idempotent upsert
(PK = period, entity_type, method) overwrites in place, picking up any revisions.

Usage:
  python scripts/update_tbb_acquisition.py
  python scripts/update_tbb_acquisition.py --db data/bddk_data.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.tbb.acquisition import download_latest, parse_workbook  # noqa: E402
from src.tbb.loader import upsert_acquisition                    # noqa: E402
from src.tbb.schema import init_acquisition_schema               # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    args = ap.parse_args()

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        init_acquisition_schema(conn)
        with tempfile.TemporaryDirectory() as tmp:
            print("Discovering newest TBB acquisition report …", flush=True)
            found = download_latest(tmp)
            if not found:
                print("No report found.", flush=True)
                return 0
            period, path = found
            print(f"Latest report: {period} ({path.name})", flush=True)
            stats = parse_workbook(str(path))
            n = upsert_acquisition(conn, stats)
            periods = sorted({s.period for s in stats})
            print(f"Parsed {len(stats)} rows (months {periods[0]}..{periods[-1]}) "
                  f"→ upserted {n}.", flush=True)
        rowcount = conn.execute("SELECT COUNT(*) FROM tbb_acquisition_stats").fetchone()[0]
        span = conn.execute(
            "SELECT MIN(period), MAX(period) FROM tbb_acquisition_stats"
        ).fetchone()
    print(f"Done. Table now holds {rowcount} rows spanning {span[0]}..{span[1]}.",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
