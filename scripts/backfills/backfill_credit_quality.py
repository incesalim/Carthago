"""One-shot backfill: pull every R2 PDF, run ONLY the credit-quality extractor,
upsert into bank_audit_credit_quality.

The main extractor (BS / P&L) is unchanged — this script touches only the new
credit-quality table. Safe to re-run; it skips (bank, period, kind) tuples
already present unless --force is set.

Usage:
  python scripts/backfill_credit_quality.py                 # all R2 PDFs, skip done
  python scripts/backfill_credit_quality.py --force         # re-extract every PDF
  python scripts/backfill_credit_quality.py --period 2025Q4 # filter to one period
  python scripts/backfill_credit_quality.py --workers 8
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.credit_quality import extract, upsert  # noqa: E402
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
        return ticker, period, kind, False, 0, time.time() - t0, f"{type(e).__name__}:{str(e)[:80]}", None, str(dest)
    return ticker, period, kind, True, len(rep.rows), time.time() - t0, "", rep, str(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true",
                    help="Re-extract even (bank, period, kind) tuples already in the table.")
    ap.add_argument("--period", default=None,
                    help="Filter to one period, e.g. 2025Q4.")
    ap.add_argument("--ticker", default=None,
                    help="Filter to one ticker, e.g. AKBNK.")
    ap.add_argument("--kind", default=None,
                    choices=["consolidated", "unconsolidated"])
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        done: set[tuple[str, str, str]] = set()
        if not args.force:
            done = {
                (t, p, k) for t, p, k in conn.execute(
                    "SELECT DISTINCT bank_ticker, period, kind "
                    "FROM bank_audit_credit_quality"
                ).fetchall()
            }

    # List PDFs in R2 and apply CLI filters.
    pdfs: list[tuple[str, str, str, str]] = []
    for ticker, period, kind, key in r2_storage.list_audit_pdfs():
        if args.ticker and ticker != args.ticker.upper():
            continue
        if args.period and period != args.period.upper():
            continue
        if args.kind and kind != args.kind:
            continue
        if (ticker, period, kind) in done:
            continue
        pdfs.append((ticker, period, kind, key))

    print(f"[backfill] {len(pdfs)} PDFs to process ({len(done)} already done)", flush=True)
    if not pdfs:
        return

    counts = {"ok": 0, "fail": 0, "empty": 0, "rows": 0}
    with tempfile.TemporaryDirectory(prefix="cq_") as tmp_dir, \
         sqlite3.connect(str(DB_PATH)) as conn, \
         ProcessPoolExecutor(max_workers=args.workers) as ex:
        work = [(t, p, k, key, tmp_dir) for (t, p, k, key) in pdfs]
        futures = [ex.submit(_worker, w) for w in work]
        for i, fut in enumerate(as_completed(futures), 1):
            ticker, period, kind, ok, nrows, secs, err, rep, path_str = fut.result()
            if not ok:
                counts["fail"] += 1
                print(f"  [{i:>4}/{len(pdfs)}] FAIL {ticker:<8} {period} {kind:<14} {err}", flush=True)
            else:
                upsert(conn, ticker, period, kind, rep)
                counts["rows"] += nrows
                if nrows == 0:
                    counts["empty"] += 1
                    print(f"  [{i:>4}/{len(pdfs)}] EMTY {ticker:<8} {period} {kind:<14}  ({secs:.1f}s)", flush=True)
                else:
                    counts["ok"] += 1
                    # Show one-liner with the loans_ecl Stage 3 if present (NPL proxy)
                    npl = next((r for r in rep.rows
                                if r.section == "loans_ecl" and r.period_type == "current"), None)
                    npl_str = (f"NPL-prov={npl.stage3:,.0f}" if npl and npl.stage3 else "")
                    print(f"  [{i:>4}/{len(pdfs)}] OK   {ticker:<8} {period} {kind:<14} "
                          f"rows={nrows} {npl_str}  ({secs:.1f}s)", flush=True)
            try:
                Path(path_str).unlink()
            except OSError:
                pass

    print(f"\n[backfill] ok={counts['ok']} empty={counts['empty']} fail={counts['fail']} "
          f"total_rows={counts['rows']}")


if __name__ == "__main__":
    main()
