"""Targeted single-statement fleet re-extraction.

Re-parses ONLY the requested statement from each PDF — `extract(only={statement})`
skips the six slow deep-scan extractors — then upserts just that one table and
pushes just that one table to D1. This lets a one-lane extractor fix be applied
across the fleet without re-running all 14 extractors per PDF (the difference
between minutes-to-an-hour and ~3.5 hrs).

  python scripts/reextract_statement.py --statement equity_change --banks ALL
  python scripts/reextract_statement.py --statement equity_change --banks AKBNK,GARAN --dry-run
  # fast iterate loop — re-extract only what's failing, validate inline:
  python scripts/reextract_statement.py --statement equity_change --only-failing --dry-run

Validation is computed INLINE per partition by default (recomputes the whole
partition from stored rows, persists bank_audit_validation, prints live [vFAIL]
lines) — so a separate revalidate_audit_db.py pass is NOT needed for touched
partitions. Pass --no-inline-validate to skip it (then run revalidate_audit_db.py
→ push_to_d1 --only-tables bank_audit_validation → sync_audit_expected.py --push).
The non-dry-run push includes bank_audit_validation when validated inline; run
sync_audit_expected.py --push afterward to refresh the coverage matrix.
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
from src.audit_reports import validator as _validator  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.equity_change import (  # noqa: E402
    EquityChangeReport, upsert as _upsert_equity,
)
from src.audit_reports.oci import OCIReport, upsert as _upsert_oci  # noqa: E402
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402
from scripts.sync_audit_reports import list_r2_pdfs, _restrict_to_latest_period  # noqa: E402
from scripts.audit_d1 import DB, pull_snapshot, push_partitions, push_snapshot  # noqa: E402

# statement key → its D1/SQLite table. Only the per-table-upsert-able lanes.
STATEMENT_TABLE = {
    "equity_change": "bank_audit_equity_change",
    "oci": "bank_audit_oci",
    "cash_flow": "bank_audit_cash_flow",
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
    if statement == "oci":
        n = len(getattr(rep, "other_comprehensive_income", []) or [])
    elif statement == "cash_flow":
        n = len(getattr(rep, "cash_flow", []) or [])
    else:
        eq = getattr(rep, "equity_change", None)
        n = len(eq.rows) if eq and getattr(eq, "rows", None) else 0
    return (ticker, period, kind, True, n, time.time() - t0, "", rep, str(dest))


def _upsert(conn, statement, bank, period, kind, rep) -> int:
    if statement == "equity_change":
        report = getattr(rep, "equity_change", None) or EquityChangeReport(pdf_path=rep.pdf_path)
        return _upsert_equity(conn, bank, period, kind, report)
    if statement == "oci":
        report = OCIReport(pdf_path=rep.pdf_path,
                           rows=getattr(rep, "other_comprehensive_income", []) or [])
        return _upsert_oci(conn, bank, period, kind, report)
    if statement == "cash_flow":
        rows = getattr(rep, "cash_flow", []) or []
        conn.execute('DELETE FROM bank_audit_cash_flow WHERE bank_ticker=? AND period=? AND kind=?',
                     (bank, period, kind))
        if rows:
            conn.executemany(
                'INSERT INTO bank_audit_cash_flow '
                '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [(bank, period, kind, r.order, r.hierarchy, r.name, r.footnote, r.cur_amount)
                 for r in rows])
        return len(rows)
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
    ap.add_argument("--only-failing", action="store_true",
                    help="re-extract ONLY partitions currently failing this statement's "
                         "validation (reads bank_audit_validation in the LOCAL db)")
    ap.add_argument("--no-inline-validate", action="store_true",
                    help="skip inline per-partition validation (fall back to the separate "
                         "revalidate_audit_db.py step)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite even partitions whose stored data already PASSES this "
                         "statement's validation (default: leave correct data untouched)")
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
    if args.only_failing:
        # Intersect with the partitions that currently FAIL this statement's
        # validation (local db — populated by a prior inline run or revalidate).
        with sqlite3.connect(str(DB)) as _c:
            failing = {(t.upper(), p.upper(), k) for (t, p, k) in _c.execute(
                "SELECT bank_ticker, period, kind FROM bank_audit_validation "
                "WHERE statement=? AND checks_failed>0", (statement,))}
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs
                if (t.upper(), p.upper(), k) in failing]
        print(f"[reext] --only-failing -> {len(pdfs)} failing {statement} partition(s)",
              flush=True)
    print(f"[reext] statement={statement} table={table} pdfs={len(pdfs)} "
          f"workers={args.workers}{' (dry-run)' if args.dry_run else ''}", flush=True)
    if not pdfs:
        print("[reext] nothing to do"); return 0

    touched: list[tuple[str, str, str]] = []
    counts = {"ok": 0, "fail": 0, "rows": 0, "vok": 0, "vfail": 0, "keep": 0}
    inline = not args.no_inline_validate
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
                # Non-destructive: never overwrite data that already validates
                # (--only-failing already excludes these, but the guard makes a
                # plain re-extract safe too). --force overrides.
                if not args.force and _validator.statement_passes(conn, t, p, k, statement):
                    counts["keep"] += 1
                    continue
                _upsert(conn, statement, t, p, k, rep)
                conn.execute(
                    "UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                    "WHERE bank_ticker=? AND period=? AND kind=?", (t, p, k))
                touched.append((t, p, k))
                counts["ok"] += 1
                counts["rows"] += n
                # Inline validation: recompute the WHOLE partition from stored rows
                # (the just-upserted statement + the others already in the db) and
                # persist it, so failures surface DURING the run and the separate
                # revalidate_audit_db.py pass is unnecessary for touched partitions.
                if inline:
                    results = revalidate_partition(conn, t, p, k)
                    _validator.upsert_validation(conn, t, p, k, results)
                    eqr = results.get(statement)
                    if eqr is not None and eqr.failed:
                        counts["vfail"] += 1
                        chk = eqr.failures[0].get("check", "?") if eqr.failures else "?"
                        print(f"  [vFAIL] {t:<8} {p} {k:<14} {statement} "
                              f"P{eqr.passed}/F{eqr.failed}/S{eqr.skipped} {chk}", flush=True)
                    elif eqr is not None:
                        counts["vok"] += 1
                if done % 50 == 0:
                    conn.commit()
                    tally = f" vpass={counts['vok']} vfail={counts['vfail']}" if inline else ""
                    print(f"  [{done}/{len(work)}] last {t} {p} {k} rows={n} ({secs:.0f}s){tally}",
                          flush=True)
                try:
                    Path(path).unlink()
                except OSError:
                    pass
            conn.commit()
    vtally = f" | validated: pass={counts['vok']} FAIL={counts['vfail']}" if inline else ""
    keptt = f" kept={counts['keep']}" if counts['keep'] else ""
    print(f"[reext] ok={counts['ok']} fail={counts['fail']}{keptt} rows={counts['rows']}{vtally}",
          flush=True)

    if args.dry_run:
        print("[reext] dry-run — no D1 push / snapshot", flush=True)
        return 0
    # Push the validation rows too when computed inline, so the dashboard/matrix
    # reflect the fresh pass/fail without a separate revalidate+push.
    push_tables = [table] + (["bank_audit_validation"] if inline else [])
    push_partitions(touched, db_path=DB, window_hours=24, tables=push_tables)
    push_snapshot(DB)
    print("[reext] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
