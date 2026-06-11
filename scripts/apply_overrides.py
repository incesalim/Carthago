"""Apply curated per-cell overrides to the production DB and push the affected
partitions to D1 — NO re-extraction. For balance-sheet/income-statement rows
the deterministic extractor can't recover (one-off OCR artifacts) but whose
correct values are legible in the PDF. Each override is transcribed by hand
into data/audit_overrides.json.

  python scripts/apply_overrides.py [--dry-run] [--no-push]

Override entry (data/audit_overrides.json "overrides" list):
  BS:  {bank_ticker, period, kind, statement: assets|liabilities|off_balance,
        hierarchy, item_name, amount_tl, amount_fc, amount_total, note}
  P&L: {bank_ticker, period, kind, statement: "profit_loss",
        hierarchy, item_name, amount, note}
Matched by (bank, period, kind, statement, hierarchy); the row is UPDATED in
place, or INSERTED (at max item_order+1) if the parser dropped it.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.validator import validate_report  # noqa: E402
from scripts.backfill_extraction import (  # noqa: E402
    AUDIT_TABLES, _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
OVR = REPO / "data" / "audit_overrides.json"
SNAP = "state/bank_audit.db.gz"


def _apply_one(conn: sqlite3.Connection, o: dict) -> str:
    b, p, k = o["bank_ticker"], o["period"], o["kind"]
    st = o["statement"]
    h = o["hierarchy"]
    if st == "profit_loss":
        row = conn.execute(
            "SELECT item_order FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? "
            "AND kind=? AND hierarchy=?", (b, p, k, h)).fetchone()
        if row:
            conn.execute(
                "UPDATE bank_audit_profit_loss SET amount=?, item_name=? "
                "WHERE bank_ticker=? AND period=? AND kind=? AND item_order=?",
                (o["amount"], o.get("item_name", h), b, p, k, row[0]))
            return f"PL update {b} {p} {k} {h}={o['amount']:,.0f}"
        nxt = (conn.execute("SELECT COALESCE(MAX(item_order),0)+1 FROM bank_audit_profit_loss "
                            "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k)).fetchone()[0])
        conn.execute(
            "INSERT INTO bank_audit_profit_loss (bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
            "VALUES (?,?,?,?,?,?,?)", (b, p, k, nxt, h, o.get("item_name", h), o["amount"]))
        return f"PL insert {b} {p} {k} {h}={o['amount']:,.0f}"
    # balance sheet
    row = conn.execute(
        "SELECT item_order FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? "
        "AND kind=? AND statement=? AND hierarchy=?", (b, p, k, st, h)).fetchone()
    if row:
        conn.execute(
            "UPDATE bank_audit_balance_sheet SET amount_tl=?, amount_fc=?, amount_total=?, item_name=? "
            "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order=?",
            (o["amount_tl"], o["amount_fc"], o["amount_total"], o.get("item_name", h), b, p, k, st, row[0]))
        return f"BS update {b} {p} {k} {st} {h}"
    if "item_order" in o:  # positional insert: shift later rows down, slot in at the right spot
        # two-step via negatives — a plain +1 collides with the UNIQUE(item_order) index mid-update
        conn.execute("UPDATE bank_audit_balance_sheet SET item_order=-(item_order+1) "
                     "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order>=?",
                     (b, p, k, st, o["item_order"]))
        conn.execute("UPDATE bank_audit_balance_sheet SET item_order=-item_order "
                     "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order<0",
                     (b, p, k, st))
        nxt = o["item_order"]
    else:
        nxt = (conn.execute("SELECT COALESCE(MAX(item_order),0)+1 FROM bank_audit_balance_sheet "
                            "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
                            (b, p, k, st)).fetchone()[0])
    conn.execute(
        "INSERT INTO bank_audit_balance_sheet "
        "(bank_ticker,period,kind,statement,item_order,hierarchy,item_name,amount_tl,amount_fc,amount_total) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (b, p, k, st, nxt, h, o.get("item_name", h), o["amount_tl"], o["amount_fc"], o["amount_total"]))
    return f"BS insert {b} {p} {k} {st} {h} @order{nxt}"


def _revalidate_partition(conn, b, p, k):
    from src.audit_reports import validator as v
    def rows(stmt):
        return [dict(zip(("hierarchy", "item_name", "amount_tl", "amount_fc", "amount_total"), r))
                for r in conn.execute(
                    "SELECT hierarchy,item_name,amount_tl,amount_fc,amount_total FROM bank_audit_balance_sheet "
                    "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? ORDER BY item_order",
                    (b, p, k, stmt))]
    a, li = rows("assets"), rows("liabilities")
    res = {"assets": v.validate_statement(a), "liabilities": v.validate_statement(li),
           "cross": v.check_cross_statement(a, li)}
    v.upsert_validation(conn, b, p, k, res)
    return sum(r.failed for r in res.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    overrides = json.loads(OVR.read_text(encoding="utf-8"))["overrides"]
    if not args.dry_run and not args.no_push:
        _guard_against_ci_writers()
        r2_storage.download_to(SNAP, GZ)
        with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
            shutil.copyfileobj(s, d)
        print(f"[ovr] pulled snapshot → {DB.stat().st_size/1e6:.1f} MB")

    parts = set()
    with sqlite3.connect(str(DB)) as conn:
        for o in overrides:
            print("  ", _apply_one(conn, o))
            parts.add((o["bank_ticker"], o["period"], o["kind"]))
        # re-validate each touched partition + bump extracted_at for the push window
        for b, p, k in sorted(parts):
            f = _revalidate_partition(conn, b, p, k)
            print(f"  revalidate {b} {p} {k}: {f} failures")
            conn.execute("UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                         "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k))
        conn.commit()

    if args.dry_run or args.no_push:
        print("[ovr] local only — not pushing")
        return 0

    _ensure_d1_schema()
    stmts = []
    for tbl in AUDIT_TABLES:
        for b, p, k in parts:
            stmts.append(f"DELETE FROM {tbl} WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}';")
    sqlp = Path(tempfile.gettempdir()) / "d1_ovr_clear.sql"
    sqlp.write_text("\n".join(stmts) + "\n", encoding="utf-8")
    print(f"[ovr] clearing {len(parts)} partitions in D1")
    _retry_wrangler(sqlp, "D1 override clear")
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "1", "--only-tables", ",".join(AUDIT_TABLES)], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[ovr] uploaded snapshot ({size/1e6:.1f} MB)")
    print("[ovr] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
