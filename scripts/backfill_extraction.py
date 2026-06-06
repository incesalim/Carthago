"""Re-extract specific banks from the R2 PDFs and backfill D1 + the snapshot.

Used after an extractor fix to correct already-ingested banks (the cron skips
PDFs already extracted with success=1, so it won't self-heal). It:

  1. pulls state/bank_audit.db.gz from R2 → data/bank_audit.db
  2. deletes the named banks' bank_audit_extractions rows (forces re-extract)
  3. re-extracts those banks from their R2 PDFs with the current extractor
  4. rebuilds bank_audit_stages, pushes the rows to D1
  5. re-uploads the snapshot (with a dated history backup)

Requires R2_* and CLOUDFLARE_API_TOKEN env vars.

  python scripts/backfill_extraction.py --banks EXIM,ZIRAAT
  python scripts/backfill_extraction.py --banks EXIM --dry-run
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.sync_audit_reports import extract_from_r2  # noqa: E402

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"
AUDIT_TABLES = [
    "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_credit_quality",
    "bank_audit_profile", "bank_audit_loans_by_sector", "bank_audit_npl_movement",
    "bank_audit_stages", "bank_audit_extractions",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", required=True,
                    help="comma-separated tickers, or ALL for every bank in the config")
    ap.add_argument("--latest-period", action="store_true",
                    help="only re-extract each bank's most recent period (fast, bounded)")
    ap.add_argument("--dry-run", action="store_true", help="re-extract locally; skip D1 push + snapshot upload")
    args = ap.parse_args()
    if args.banks.strip().upper() == "ALL":
        cfg = json.loads((REPO / "data" / "banks" / "audit_report_urls.json").read_text(encoding="utf-8"))
        banks = {t.upper() for t in cfg["banks"]}
    else:
        banks = {b.strip().upper() for b in args.banks.split(",") if b.strip()}
    print(f"[backfill] banks: {len(banks)}{' (latest period only)' if args.latest_period else ''}")

    DB.parent.mkdir(parents=True, exist_ok=True)
    if not r2_storage.exists(SNAP):
        sys.exit(f"no snapshot at R2 {SNAP}")
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[backfill] pulled snapshot → {DB.stat().st_size/1e6:.1f} MB")

    # Force re-extraction by clearing the extraction log. With --latest-period
    # only the newest period per bank is cleared (and re-extracted).
    ph = ",".join("?" * len(banks))
    with sqlite3.connect(str(DB)) as conn:
        where = f"bank_ticker IN ({ph})"
        params: tuple = tuple(banks)
        if args.latest_period:
            where += (" AND (bank_ticker, period) IN (SELECT bank_ticker, MAX(period) "
                      f"FROM bank_audit_extractions WHERE bank_ticker IN ({ph}) GROUP BY bank_ticker)")
            params = tuple(banks) * 2
        before = conn.execute(
            f"SELECT COUNT(*) FROM bank_audit_extractions WHERE {where}", params).fetchone()[0]
        conn.execute(f"DELETE FROM bank_audit_extractions WHERE {where}", params)
        conn.commit()
    print(f"[backfill] cleared {before} extraction records → will re-extract")

    counts = extract_from_r2(workers=8, db_path=DB, only=banks, latest_period=args.latest_period)
    print(f"[backfill] re-extract: {counts}")

    subprocess.run([sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
                    "--db", str(DB)], check=True)

    if args.dry_run:
        print("[backfill] dry-run: skipping D1 push + snapshot upload")
        return

    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "24",
                    "--only-tables", ",".join(AUDIT_TABLES)], check=True)

    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[backfill] uploaded snapshot ({size/1e6:.1f} MB) → R2 {SNAP}")
    print("[backfill] done")


if __name__ == "__main__":
    main()
