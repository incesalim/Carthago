"""Recompute bank_audit_validation for every partition in a local audit DB.

Normally validation rows are written at extraction time (loader.upsert_report).
This recomputes them from the STORED rows (balance sheet + P&L) — for partitions
extracted before the validator existed (ALBRK/BURGAN), excluded from a backfill
(TSKB), or whenever the validator's checks change (e.g. P&L validation added).
Pure over stored rows: no PDF re-extraction. Push with
`scripts/push_to_d1.py --db <db> --only-tables bank_audit_validation`.

  python scripts/revalidate_audit_db.py --db data/bank_audit.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import validator as v  # noqa: E402


def _rows(conn, bank, period, kind, stmt):
    return [dict(zip(("hierarchy", "item_name", "amount_tl", "amount_fc", "amount_total"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount_tl, amount_fc, amount_total "
                "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? "
                "AND kind=? AND statement=? ORDER BY item_order",
                (bank, period, kind, stmt))]


def _pl_rows(conn, bank, period, kind):
    return [dict(zip(("hierarchy", "item_name", "amount"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount FROM bank_audit_profit_loss "
                "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY item_order",
                (bank, period, kind))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    parts = conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet").fetchall()
    failed_parts = 0
    for n, (bank, period, kind) in enumerate(sorted(parts), 1):
        a = _rows(conn, bank, period, kind, "assets")
        li = _rows(conn, bank, period, kind, "liabilities")
        pl = _pl_rows(conn, bank, period, kind)
        results = {
            "assets": v.validate_statement(a),
            "liabilities": v.validate_statement(li),
            "cross": v.check_cross_statement(a, li),
            "profit_loss": v.check_profit_loss(pl, li),
        }
        v.upsert_validation(conn, bank, period, kind, results)
        if any(r.failed for r in results.values()):
            failed_parts += 1
        if n % 200 == 0:
            print(f"[revalidate] {n}/{len(parts)}", flush=True)
    conn.commit()
    print(f"[revalidate] {len(parts)} partitions revalidated; "
          f"{failed_parts} with failing identity checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
