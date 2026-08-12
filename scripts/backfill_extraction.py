"""Re-extract specific banks from the R2 PDFs and backfill D1 + the snapshot.

Used after an extractor fix to correct already-ingested banks (the cron skips
PDFs already extracted with success=1, so it won't self-heal). It:

  1. pulls state/bank_audit.db.gz from R2 → data/bank_audit.db
  2. deletes the named banks' bank_audit_extractions rows (forces re-extract)
  3. re-extracts those banks from their R2 PDFs with the current extractor
  4. rebuilds bank_audit_stages
  5. REPLACES the re-extracted (bank, period, kind) partitions in D1 — scoped
     DELETEs plus the fresh rows in ONE cost-guarded file that wrangler executes
     atomically. The DELETE half matters because a plain push is INSERT OR
     REPLACE and cannot delete, so an old, larger extraction would otherwise
     leave orphan rows the fresh extract no longer produces.
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
    DB, PUSH_WINDOW_HOURS,
    pull_snapshot, ensure_d1_schema, clear_d1_partitions, push_snapshot,
)
from scripts.sync_audit_reports import (  # noqa: E402
    _restrict_to_latest_period, extract_from_r2, list_r2_pdfs,
)


def latest_period_in_r2(banks: set[str]) -> dict[str, str]:
    """{ticker: newest period PRESENT IN R2} for `banks`.

    ⚠️ Must be R2, not `bank_audit_extractions`. The two disagree exactly when a
    quarter has been acquired but not yet extracted — which is the normal state
    during a filing season, and the state any extraction stall creates. This
    function is the shared answer so the DELETE below and `extract_from_r2`
    cannot pick different quarters; when they did, `--latest-period` cleared the
    DB's newest period (2026Q1) while the extractor re-read R2's newest (2026Q2),
    leaving 2026Q1 with no extraction log row and nothing to rebuild it.
    """
    rows = [(t, p) for (t, p, _k, _key) in list_r2_pdfs() if t.upper() in banks]
    return {t.upper(): p.upper() for t, p in _restrict_to_latest_period(rows)}


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
            # Scope the clear to the SAME quarter extract_from_r2 will re-read —
            # the newest in R2. This used to be MAX(period) from
            # bank_audit_extractions, and the two are only equal while every
            # acquired PDF has been extracted. Whenever R2 was ahead (a live
            # filing season, or any extraction stall) the clear took the older
            # quarter and the re-extract took the newer, so the older one lost
            # its log row and was never rebuilt.
            latest = latest_period_in_r2(banks)
            if not latest:
                sys.exit("[backfill] --latest-period: no R2 PDFs for the named "
                         "banks; refusing to clear anything.")
            pairs = " OR ".join(["(bank_ticker=? AND period=?)"] * len(latest))
            where += f" AND ({pairs})"
            for t, p in sorted(latest.items()):
                params += (t, p)
            print("[backfill] latest period per bank (from R2): "
                  + ", ".join(f"{t}:{p}" for t, p in sorted(latest.items())))
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
    # One atomic replace: the DELETEs and the INSERTs travel in a single guarded
    # wrangler file. This used to be clear_d1_partitions() followed by
    # push_to_d1(), where anything going wrong between the two left the
    # partitions deleted and unrestored.
    clear_d1_partitions(DB, args.window_hours)
    push_snapshot(DB)
    print("[backfill] done")


if __name__ == "__main__":
    main()
