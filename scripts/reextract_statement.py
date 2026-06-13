"""Targeted single-statement fleet re-extraction.

Re-parses ONLY the requested statement from each PDF — `extract(only={statement})`
skips the six slow deep-scan extractors — then upserts just that one table and
pushes just that one table to D1. This lets a one-lane extractor fix be applied
across the fleet without re-running all 14 extractors per PDF (the difference
between minutes-to-an-hour and ~3.5 hrs).

  python scripts/reextract_statement.py --statement equity_change --banks ALL
  python scripts/reextract_statement.py --statement equity_change --banks AKBNK,GARAN --dry-run

Post-step (unchanged, run after this): revalidate_audit_db.py → push_to_d1
--only-tables bank_audit_validation → sync_audit_expected.py --push.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.equity_change import (  # noqa: E402
    EquityChangeReport, upsert as _upsert_equity,
)
from scripts.sync_audit_reports import list_r2_pdfs, _restrict_to_latest_period  # noqa: E402
from scripts.audit_d1 import DB, pull_snapshot, push_partitions, push_snapshot  # noqa: E402

# statement key → its D1/SQLite table. Only the per-table-upsert-able lanes.
STATEMENT_TABLE = {
    "equity_change": "bank_audit_equity_change",
}


def _worker(args):
    """Pickleable worker: download one PDF, extract ONLY the requested statement,
    return its rows. Upsert happens in the parent (single DB connection)."""
    ticker, period, kind, key, statement, tmp_dir = args
    t0 = time.time()
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    try:
        r2_storage.download_to(key, dest)
    except Exception as e:  # noqa: BLE001
        return (ticker, period, kind, False, 0, time.time() - t0,
                f"r2:{type(e).__name__}", None, str(dest))
    try:
        rep = extract(str(dest), only={statement})
    except Exception as e:  # noqa: BLE001
        return (ticker, period, kind, False, 0, time.time() - t0,
                f"extract:{type(e).__name__}:{str(e)[:60]}", None, str(dest))
    eq = getattr(rep, "equity_change", None)
    n = len(eq.rows) if eq and getattr(eq, "rows", None) else 0
    return (ticker, period, kind, True, n, time.time() - t0, "", rep, str(dest))


def _upsert(conn, statement, bank, period, kind, rep) -> int:
    if statement == "equity_change":
        report = getattr(rep, "equity_change", None) or EquityChangeReport(pdf_path=rep.pdf_path)
        return _upsert_equity(conn, bank, period, kind, report)
    raise ValueError(f"upsert not wired for statement {statement!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", required=True, choices=list(STATEMENT_TABLE))
    ap.add_argument("--banks", default="ALL", help="ALL or comma-separated tickers")
    ap.add_argument("--periods", default="", help="comma-separated YYYYQn (optional)")
    ap.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 4)))
    ap.add_argument("--latest-period", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="re-extract + upsert LOCAL db only; no D1 push / snapshot")
    args = ap.parse_args()
    statement = args.statement
    table = STATEMENT_TABLE[statement]
    banks = (None if args.banks.strip().upper() == "ALL"
             else {b.strip().upper() for b in args.banks.split(",") if b.strip()})
    periods = {p.strip().upper() for p in args.periods.split(",") if p.strip()} or None

    if not args.dry_run:
        pull_snapshot(guard=True)

    pdfs = list_r2_pdfs()
    if banks:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if t.upper() in banks]
    if periods:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if p.upper() in periods]
    if args.latest_period:
        pdfs = _restrict_to_latest_period(pdfs)
    print(f"[reext] statement={statement} table={table} pdfs={len(pdfs)} "
          f"workers={args.workers}{' (dry-run)' if args.dry_run else ''}", flush=True)
    if not pdfs:
        print("[reext] nothing to do"); return 0

    touched: list[tuple[str, str, str]] = []
    counts = {"ok": 0, "fail": 0, "rows": 0}
    with tempfile.TemporaryDirectory(prefix="bddk_reext_") as td:
        work = [(t, p, k, key, statement, td) for (t, p, k, key) in pdfs]
        # NOTE: no max_tasks_per_child — on Windows it can DEADLOCK the pool at a
        # recycle boundary (hung a fleet run at ~task 400). Single-statement
        # extraction is light (the six deep-scan extractors are skipped), so worker
        # memory doesn't grow enough to need recycling anyway.
        with sqlite3.connect(str(DB)) as conn, \
             ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_worker, w) for w in work]
            done = 0
            for fut in as_completed(futs):
                t, p, k, ok, n, secs, err, rep, path = fut.result()
                done += 1
                if not ok:
                    counts["fail"] += 1
                    print(f"  [FAIL] {t:<8} {p} {k:<14} {err}", flush=True)
                    continue
                _upsert(conn, statement, t, p, k, rep)
                conn.execute(
                    "UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                    "WHERE bank_ticker=? AND period=? AND kind=?", (t, p, k))
                touched.append((t, p, k))
                counts["ok"] += 1
                counts["rows"] += n
                if done % 50 == 0:
                    conn.commit()
                    print(f"  [{done}/{len(work)}] last {t} {p} {k} rows={n} ({secs:.0f}s)", flush=True)
                try:
                    Path(path).unlink()
                except OSError:
                    pass
            conn.commit()
    print(f"[reext] ok={counts['ok']} fail={counts['fail']} rows={counts['rows']}", flush=True)

    if args.dry_run:
        print("[reext] dry-run — no D1 push / snapshot", flush=True)
        return 0
    push_partitions(touched, db_path=DB, window_hours=24, tables=[table])
    push_snapshot(DB)
    print("[reext] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
