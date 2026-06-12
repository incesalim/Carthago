"""Re-extract specific banks from the R2 PDFs and backfill D1 + the snapshot.

Used after an extractor fix to correct already-ingested banks (the cron skips
PDFs already extracted with success=1, so it won't self-heal). It:

  1. pulls state/bank_audit.db.gz from R2 → data/bank_audit.db
  2. deletes the named banks' bank_audit_extractions rows (forces re-extract)
  3. re-extracts those banks from their R2 PDFs with the current extractor
  4. rebuilds bank_audit_stages
  5. clears the re-extracted (bank, period, kind) partitions in D1, then pushes
     the fresh rows (push_to_d1 is INSERT OR REPLACE — without the clear an old,
     larger extraction would leave orphan rows the fresh extract no longer makes)
  6. re-uploads the snapshot (with a dated history backup)

The D1/R2 plumbing lives in scripts/audit_d1.py (shared with audit_correct etc.).
Requires R2_* and CLOUDFLARE_API_TOKEN env vars.

  python scripts/backfill_extraction.py --banks EXIM,ZIRAAT
  python scripts/backfill_extraction.py --banks EXIM --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from scripts.audit_d1 import (  # noqa: E402
    DB, AUDIT_TABLES, PUSH_WINDOW_HOURS,
    pull_snapshot, ensure_d1_schema, clear_d1_partitions, push_to_d1, push_snapshot,
)
from scripts.sync_audit_reports import extract_from_r2  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", required=True,
                    help="comma-separated tickers, or ALL for every bank in the config")
    ap.add_argument("--latest-period", action="store_true",
                    help="only re-extract each bank's most recent period (fast, bounded)")
    ap.add_argument("--dry-run", action="store_true", help="re-extract locally; skip D1 push + snapshot upload")
    ap.add_argument("--skip", type=str, default="",
                    help="comma-separated BANK:PERIOD:KIND triples to leave untouched "
                         "(not re-extracted, not cleared in D1 — e.g. an unextractable "
                         "no-text-layer PDF whose old rows must survive: "
                         "ISCTR:2025Q1:consolidated)")
    ap.add_argument("--window-hours", type=int, default=PUSH_WINDOW_HOURS,
                    help="freshness window for the D1 clear+push set (smaller for "
                         "batched runs so batches don't re-push each other)")
    args = ap.parse_args()
    if args.banks.strip().upper() == "ALL":
        cfg = json.loads((REPO / "data" / "banks" / "audit_report_urls.json").read_text(encoding="utf-8"))
        banks = {t.upper() for t in cfg["banks"]}
    else:
        banks = {b.strip().upper() for b in args.banks.split(",") if b.strip()}
    print(f"[backfill] banks: {len(banks)}{' (latest period only)' if args.latest_period else ''}")

    # Guard against CI snapshot-clobber unless this IS the CI run or a dry-run.
    guard = not args.dry_run and os.environ.get("GITHUB_ACTIONS") != "true"
    pull_snapshot(guard=guard)

    skips = [tuple(s.strip().split(":")) for s in args.skip.split(",") if s.strip()]
    if any(len(t) != 3 for t in skips):
        sys.exit(f"--skip entries must be BANK:PERIOD:KIND, got {args.skip!r}")

    # Force re-extraction by clearing the extraction log. With --latest-period
    # only the newest period per bank is cleared (and re-extracted). --skip
    # triples keep their success=1 log row, so extract_from_r2 leaves them
    # alone and their local + D1 rows survive untouched.
    ph = ",".join("?" * len(banks))
    with sqlite3.connect(str(DB)) as conn:
        where = f"bank_ticker IN ({ph})"
        params: tuple = tuple(banks)
        if args.latest_period:
            where += (" AND (bank_ticker, period) IN (SELECT bank_ticker, MAX(period) "
                      f"FROM bank_audit_extractions WHERE bank_ticker IN ({ph}) GROUP BY bank_ticker)")
            params = tuple(banks) * 2
        for bank, period, kind in skips:
            where += " AND NOT (bank_ticker=? AND period=? AND kind=?)"
            params += (bank.upper(), period.upper(), kind.lower())
        before = conn.execute(
            f"SELECT COUNT(*) FROM bank_audit_extractions WHERE {where}", params).fetchone()[0]
        conn.execute(f"DELETE FROM bank_audit_extractions WHERE {where}", params)
        conn.commit()
    print(f"[backfill] cleared {before} extraction records → will re-extract"
          + (f" (skipping {len(skips)})" if skips else ""))

    counts = extract_from_r2(workers=8, db_path=DB, only=banks, latest_period=args.latest_period)
    print(f"[backfill] re-extract: {counts}")

    subprocess.run([sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
                    "--db", str(DB)], check=True)

    if args.dry_run:
        print("[backfill] dry-run: skipping D1 clear + push + snapshot upload")
        return

    ensure_d1_schema()                          # create any missing tables before clear/push
    clear_d1_partitions(DB, args.window_hours)  # derive the (bank,period,kind) set from the window
    push_to_d1(DB, args.window_hours, AUDIT_TABLES)
    push_snapshot(DB)
    print("[backfill] done")


if __name__ == "__main__":
    main()
