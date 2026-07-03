"""Fetch TKBB monthly remote-vs-branch customer acquisition into SQLite.

Pulls the "Uzaktan Müşteri Edinim İstatistikleri" Turboard dashboard behind
TKBB's Veri Peteği. The public dashlets expose only a rolling last-12-months
window, so each run upserts that window and the table accumulates history —
rows are never deleted. Measure names (applications/customers) are resolved
from the live dashboard's measure aliases, never assumed.

Usage:
  python scripts/update_tkbb_acquisition.py
  python scripts/update_tkbb_acquisition.py --db data/scratch.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.tkbb.acquisition import fetch_all           # noqa: E402
from src.tkbb.loader import upsert_acquisition        # noqa: E402
from src.tkbb.schema import init_acquisition_schema   # noqa: E402
from src.tkbb.turboard import _session                # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    args = ap.parse_args()

    print("Fetching TKBB acquisition window …", flush=True)
    stats = fetch_all(session=_session())
    if not stats:
        print("No rows returned.", flush=True)
        return 0
    months = sorted({s.period for s in stats})
    print(f"Window: {months[0]}..{months[-1]} ({len(stats)} rows)", flush=True)

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        init_acquisition_schema(conn)
        n = upsert_acquisition(conn, stats)
        rowcount = conn.execute(
            "SELECT COUNT(*) FROM tkbb_acquisition_stats").fetchone()[0]
        span = conn.execute(
            "SELECT MIN(period), MAX(period) FROM tkbb_acquisition_stats"
        ).fetchone()
    print(f"Done. Upserted {n} rows; table now holds {rowcount} rows "
          f"spanning {span[0]}..{span[1]}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
