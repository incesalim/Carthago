"""Re-extract every PDF in R2 with the FULL extractor (BS + PL + credit quality).

Unlike backfill_credit_quality.py (CQ-only), this runs the complete
extractor.extract pipeline through loader.upsert_report, so it picks up the
latest fixes in both the main BS/PL parser AND the credit-quality module.

Usage:
  python scripts/reextract_all.py --workers 8                # all banks/periods
  python scripts/reextract_all.py --workers 8 --period 2025Q4
  python scripts/reextract_all.py --workers 8 --ticker AKBNK

The script is idempotent — re-running is safe; upsert_report wipes & re-inserts
per (bank, period, kind).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def _worker(args):
    ticker, period, kind, key, tmp_dir = args
    t0 = time.time()
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    try:
        r2_storage.download_to(key, dest)
        rep = extract(str(dest))
    except Exception as e:
        return (ticker, period, kind, key, False, 0, 0, 0, 0, 0,
                time.time() - t0, f"{type(e).__name__}:{str(e)[:80]}",
                None, str(dest))
    return (
        ticker, period, kind, key, True,
        len(rep.bs_assets), len(rep.bs_liabilities), len(rep.off_balance),
        len(rep.profit_loss), len(rep.credit_quality),
        time.time() - t0, "", rep, str(dest),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--period", help="Filter to one period, e.g. 2025Q4")
    ap.add_argument("--ticker", help="Filter to one ticker, e.g. AKBNK")
    ap.add_argument("--kind", choices=["consolidated", "unconsolidated"])
    ap.add_argument("--skip-recent-hours", type=int, default=0,
                    help="Skip PDFs whose extracted_at is within the last N hours. "
                         "Use --skip-recent-hours=24 to resume a crashed full re-run.")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        # Ensure rows_credit_quality column exists (added after the schema was
        # first deployed; init_schema's CREATE TABLE IF NOT EXISTS doesn't
        # backfill columns on existing tables).
        try:
            conn.execute("ALTER TABLE bank_audit_extractions ADD COLUMN rows_credit_quality INTEGER")
        except sqlite3.OperationalError:
            pass

        # Build the "already done recently" set so we can resume after a crash.
        recently_done: set[tuple[str, str, str]] = set()
        if args.skip_recent_hours > 0:
            recently_done = {
                (t, p, k) for t, p, k in conn.execute(
                    "SELECT bank_ticker, period, kind FROM bank_audit_extractions "
                    "WHERE extracted_at >= datetime('now', ?)",
                    (f"-{args.skip_recent_hours} hours",),
                )
            }

    pdfs: list[tuple[str, str, str, str]] = []
    for ticker, period, kind, key in r2_storage.list_audit_pdfs():
        if args.ticker and ticker != args.ticker.upper():
            continue
        if args.period and period != args.period.upper():
            continue
        if args.kind and kind != args.kind:
            continue
        if (ticker, period, kind) in recently_done:
            continue
        pdfs.append((ticker, period, kind, key))
    print(f"[reextract] {len(pdfs)} PDFs to re-process with {args.workers} workers "
          f"({len(recently_done)} skipped as recently-done)", flush=True)
    if not pdfs:
        return

    counts = {"ok": 0, "warn": 0, "fail": 0}
    with tempfile.TemporaryDirectory(prefix="reextract_") as tmp_dir, \
         sqlite3.connect(str(DB_PATH)) as conn, \
         ProcessPoolExecutor(max_workers=args.workers) as ex:
        work = [(t, p, k, key, tmp_dir) for (t, p, k, key) in pdfs]
        futures = [ex.submit(_worker, w) for w in work]
        for i, fut in enumerate(as_completed(futures), 1):
            (ticker, period, kind, key, ok,
             bsa, bsl, obs, pl, cq,
             secs, err, rep, path_str) = fut.result()
            if not ok:
                counts["fail"] += 1
                print(f"  [{i:>4}/{len(pdfs)}] FAIL {ticker:<8} {period} {kind:<14} {err}",
                      flush=True)
            else:
                upsert_report(conn, ticker, period, kind, rep, key)
                tag = "OK" if (bsa >= 20 and bsl >= 20 and pl >= 20) else "WARN"
                counts["ok" if tag == "OK" else "warn"] += 1
                print(
                    f"  [{i:>4}/{len(pdfs)}] {tag:<4} {ticker:<8} {period} {kind:<14} "
                    f"BSA={bsa} BSL={bsl} OBS={obs} PL={pl} CQ={cq}  ({secs:.1f}s)",
                    flush=True,
                )
            try:
                Path(path_str).unlink()
            except OSError:
                pass

    print(f"\n[reextract] ok={counts['ok']} warn={counts['warn']} fail={counts['fail']}")


if __name__ == "__main__":
    main()
