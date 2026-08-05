"""Backfill the FULL Stage-3 / NPL history for the banks fixed by the FC-only
extractor patch (see PROJECT_STATE → "Stage-3 NPL understated by FC-only
sub-table").

`backfill_extraction.py --banks ALL --latest-period` already corrected 2026Q1.
This corrects the historical interim quarters too, so the /cross-bank Over-time
view has no fake cliff. The affected banks' interim quarters all read the
foreign-currency-only NPL sub-table; re-extracting with the fixed parser pulls
the total III/IV/V classification instead. (Year-end quarters that used the
inline `loans_amounts` row re-extract identically — idempotent.)

Why this isn't just `backfill_extraction.py --banks <list>`: a single push of
N banks × all periods is hundreds of thousands of rows, past D1's per-`execute`
limit. So we re-extract everything locally ONCE, then replace PER PERIOD (each ≈
the proven weekly latest-period size) through `audit_d1.replace_partitions`,
which builds each period's scoped DELETEs and rows into one cost-guarded file
that wrangler executes atomically.

Requires R2_* and CLOUDFLARE_API_TOKEN env vars.

  python scripts/backfills/backfill_npl_history.py            # all banks, all periods
  python scripts/backfills/backfill_npl_history.py --dry-run  # local only
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.sync_audit_reports import extract_from_r2  # noqa: E402
from scripts.audit_d1 import (  # noqa: E402
    AUDIT_TABLES, DB, GZ, SNAP, replace_partitions,
)

# Banks whose templates grabbed the FC-only NPL sub-table (the set that changed
# in the 2026Q1 latest-period backfill). Their full history needs re-extraction.
AFFECTED_BANKS = [
    "AKBNK", "AKTIF", "DENIZ", "FIBA", "ICBCT", "ISCTR",
    "KUVEYT", "ODEA", "TEB", "YKBNK", "ZIRAAT",
]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", default=",".join(AFFECTED_BANKS),
                    help="comma-separated tickers (default: the FC-only-affected set)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="re-extract locally + rebuild stages; skip D1 push + snapshot upload")
    args = ap.parse_args()
    banks = [b.strip().upper() for b in args.banks.split(",") if b.strip()]
    print(f"[npl-history] banks: {banks}")

    DB.parent.mkdir(parents=True, exist_ok=True)
    if not r2_storage.exists(SNAP):
        sys.exit(f"no snapshot at R2 {SNAP}")
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[npl-history] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    # Force re-extraction of every period for these banks.
    ph = ",".join("?" * len(banks))
    with sqlite3.connect(str(DB)) as conn:
        before = conn.execute(
            f"SELECT COUNT(*) FROM bank_audit_extractions WHERE bank_ticker IN ({ph})",
            tuple(banks)).fetchone()[0]
        conn.execute(
            f"DELETE FROM bank_audit_extractions WHERE bank_ticker IN ({ph})", tuple(banks))
        conn.commit()
    print(f"[npl-history] cleared {before} extraction records → re-extracting all periods")

    counts = extract_from_r2(workers=args.workers, db_path=DB, only=set(banks))
    print(f"[npl-history] re-extract: {counts}")

    subprocess.run([sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
                    "--db", str(DB)], check=True)

    # Periods to push (oldest first), derived from the freshly-extracted log.
    with sqlite3.connect(str(DB)) as conn:
        periods = [r[0] for r in conn.execute(
            f"SELECT DISTINCT period FROM bank_audit_extractions "
            f"WHERE bank_ticker IN ({ph}) ORDER BY period", tuple(banks))]
    print(f"[npl-history] {len(periods)} periods to push: {periods}")

    # One guarded, atomic replace per period. This used to build its own
    # DELETE+INSERT file and hand it straight to run_wrangler: no billed-row
    # guard on an explicitly high-volume audit backfill, and no partition
    # digest/row-count state, so the next push had to rediscover everything it
    # had just written. Period-level chunking is preserved — each period is one
    # bounded remote call, which is what kept these runs debuggable.
    with sqlite3.connect(str(DB)) as conn:
        by_period: dict[str, list[tuple[str, str, str]]] = {}
        for period in periods:
            by_period[period] = conn.execute(
                f"SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_extractions "
                f"WHERE bank_ticker IN ({ph}) AND period = ?", (*banks, period)
            ).fetchall()
    for i, period in enumerate(periods, 1):
        parts = by_period[period]
        verb = "would replace" if args.dry_run else "replace"
        print(f"[npl-history] {verb} {i}/{len(periods)} {period} "
              f"({len(parts)} partitions)", flush=True)
        if args.dry_run:
            continue
        replace_partitions(parts, DB, AUDIT_TABLES)

    if args.dry_run:
        print("[npl-history] dry-run: skipped D1 push + snapshot upload")
        return

    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[npl-history] uploaded snapshot ({size / 1e6:.1f} MB) → R2 {SNAP}")
    print("[npl-history] done")


if __name__ == "__main__":
    main()
