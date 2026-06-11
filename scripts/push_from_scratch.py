"""Push ALREADY-EXTRACTED audit rows from the scratch DB straight to production
— NO re-extraction. Copies the named banks' bank_audit_* rows from
data/fleet_scratch.db into the production local DB, clears those partitions in
D1, pushes the fresh rows, and uploads the snapshot. One extraction, saved,
pushed.

  python scripts/push_from_scratch.py --banks ALNTF,FIBA,...   [--dry-run]
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.backfill_extraction import (  # noqa: E402
    AUDIT_TABLES, _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
    run_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SCRATCH = REPO / "data" / "fleet_scratch.db"
SNAP = "state/bank_audit.db.gz"


def _copy_banks(prod: sqlite3.Connection, banks: list[str]) -> dict[str, int]:
    """Replace each bank's audit rows in the production DB with the scratch
    rows. Returns per-table copied counts."""
    prod.execute(f"ATTACH DATABASE '{SCRATCH}' AS scr")
    counts = {}
    ph = ",".join("?" * len(banks))
    for tbl in AUDIT_TABLES:
        # tables both DBs have
        have_prod = prod.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
        have_scr = prod.execute(
            "SELECT 1 FROM scr.sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
        if not (have_prod and have_scr):
            continue
        prod.execute(f"DELETE FROM {tbl} WHERE bank_ticker IN ({ph})", banks)
        prod.execute(f"INSERT INTO {tbl} SELECT * FROM scr.{tbl} WHERE bank_ticker IN ({ph})", banks)
        counts[tbl] = prod.execute(
            f"SELECT COUNT(*) FROM {tbl} WHERE bank_ticker IN ({ph})", banks).fetchone()[0]
    prod.commit()
    prod.execute("DETACH DATABASE scr")
    return counts


def _clear_d1(banks: list[str]) -> None:
    parts = []
    with sqlite3.connect(str(DB)) as c:
        ph = ",".join("?" * len(banks))
        parts = c.execute(
            f"SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_extractions "
            f"WHERE bank_ticker IN ({ph})", banks).fetchall()
    stmts = []
    for tbl in AUDIT_TABLES:
        for b, p, k in parts:
            stmts.append(f"DELETE FROM {tbl} WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}';")
    sql = Path(tempfile.gettempdir()) / "d1_scratch_clear.sql"
    sql.write_text("\n".join(stmts) + "\n", encoding="utf-8")
    print(f"[push] clearing {len(parts)} partitions × {len(AUDIT_TABLES)} tables in D1")
    _retry_wrangler(sql, "D1 partition clear")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--window-hours", type=int, default=6)
    args = ap.parse_args()
    banks = [b.strip().upper() for b in args.banks.split(",") if b.strip()]

    if not args.dry_run:
        _guard_against_ci_writers()
    # Pull fresh production snapshot so we copy onto the latest state.
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[push] pulled snapshot → {DB.stat().st_size/1e6:.1f} MB")

    with sqlite3.connect(str(DB)) as prod:
        # bump extracted_at so the push window picks these rows up
        counts = _copy_banks(prod, banks)
        ph = ",".join("?" * len(banks))
        prod.execute(
            f"UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
            f"WHERE bank_ticker IN ({ph})", banks)
        prod.commit()
    print(f"[push] copied from scratch: {counts}")

    if args.dry_run:
        print("[push] dry-run: skipping D1 + snapshot")
        return 0

    _ensure_d1_schema()
    _clear_d1(banks)
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", str(args.window_hours),
                    "--only-tables", ",".join(AUDIT_TABLES)], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[push] uploaded snapshot ({size/1e6:.1f} MB) → {SNAP}")
    print("[push] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
