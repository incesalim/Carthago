"""Load a partition whose statement PAGE is a scanned image: re-extract the PDF
for the text statements (assets, P&L) and OVERLAY the hand-transcribed statements
from data/manual_statements.json, then write the whole partition to the prod DB
+ D1. No OCR. Validated to 0 failures before push.

  python scripts/load_partition.py --bank FIBA --period 2025Q1 --kind unconsolidated
  python scripts/load_partition.py ... --dry-run     # local DB only, prints validation

Use for the BRSA reports that publish their balance-sheet pages as flattened
images (FIBA quarterly liabilities pages, etc.) — the deterministic extractor
gets the text pages, the JSON supplies the image ones.
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
from src.audit_reports.extractor import extract, StatementRow  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports import validator as v  # noqa: E402
from scripts.backfill_extraction import (  # noqa: E402
    AUDIT_TABLES, _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
MAN = REPO / "data" / "manual_statements.json"
SNAP = "state/bank_audit.db.gz"

_FIELD = {"assets": "bs_assets", "liabilities": "bs_liabilities",
          "off_balance": "off_balance", "profit_loss": "profit_loss"}


def _rows_to_statementrows(rows: list[dict]) -> list[StatementRow]:
    out = []
    for i, r in enumerate(rows, 1):
        if "amount" in r:  # profit_loss: single-column
            out.append(StatementRow(order=i, hierarchy=r["h"], name=r["name"], footnote=None,
                                    cur_amount=r.get("amount")))
        else:  # balance sheet: TL / FC / Total
            out.append(StatementRow(
                order=i, hierarchy=r["h"], name=r["name"], footnote=None,
                cur_tl=r.get("tl"), cur_fc=r.get("fc"), cur_total=r.get("total")))
    return out


def _pl_bottomline_check(conn, b, p, k) -> int:
    """Cross-check: the P&L period net profit (last 'DÖNEM NET' roman row) must
    equal the balance-sheet equity row 16.6.2 (Dönem Net Kâr veya Zararı). The
    structural validator doesn't cover P&L, so this is the income-statement gate."""
    # candidate P&L "net profit" amounts — total (XXV) and, for consolidated, the
    # group share (25.1, which is what lands in BS equity 16.6.2; total = group + minority).
    cands = [r[0] for r in conn.execute(
        "SELECT amount FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=? "
        "AND (item_name LIKE '%DÖNEM NET KAR%' OR item_name LIKE '%DÖNEM NET KÂR%' "
        "     OR item_name LIKE '%NET PERIOD PROFIT%' OR item_name LIKE '%DÖNEM KÂRI%' "
        "     OR item_name LIKE '%Grubun%' OR item_name LIKE '%Group%')",
        (b, p, k)) if r[0] is not None]
    bs_net = conn.execute(
        "SELECT amount_total FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? AND kind=? "
        "AND statement='liabilities' AND hierarchy IN ('16.6.2','14.6.2')", (b, p, k)).fetchone()
    if cands and bs_net and bs_net[0] is not None:
        if any(abs(c - bs_net[0]) <= 1 for c in cands):
            print(f"    [pl] bottom line OK: P&L net = BS 16.6.2 ({bs_net[0]:,.0f})")
            return 0
        print(f"    [pl] BOTTOM-LINE MISMATCH: P&L net {cands} vs BS 16.6.2 {bs_net[0]:,.0f}")
        return 1
    return 0


def _revalidate(conn, b, p, k) -> int:
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
    for nm, r in res.items():
        if r.failed:
            for f in r.failures:
                print(f"    [{nm}] {f}")
    return sum(r.failed for r in res.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--kind", required=True, choices=["consolidated", "unconsolidated"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    b, p, k = args.bank.upper(), args.period.upper(), args.kind
    key = f"{b.lower()}/{b}_{p}_{k}.pdf"

    manual = [m for m in json.loads(MAN.read_text(encoding="utf-8"))["statements"]
              if m["bank"].upper() == b and m["period"].upper() == p and m["kind"] == k]
    if not manual:
        print(f"no manual statements for {b} {p} {k}")
        return 1

    if not args.dry_run:
        _guard_against_ci_writers()
        r2_storage.download_to(SNAP, GZ)
        with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
            shutil.copyfileobj(s, d)
        print(f"[lp] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    with tempfile.TemporaryDirectory(prefix="bddk_lp_") as td:
        pdf = Path(td) / "r.pdf"
        r2_storage.download_to(key, str(pdf))
        rep = extract(str(pdf))

    for m in manual:
        field = _FIELD[m["statement"]]
        setattr(rep, field, _rows_to_statementrows(m["rows"]))
        print(f"[lp] overlaid {m['statement']} ({len(m['rows'])} manual rows)")
    print(f"[lp] {b} {p} {k}: assets={len(rep.bs_assets)} liab={len(rep.bs_liabilities)} "
          f"offbs={len(rep.off_balance)} pl={len(rep.profit_loss)}")

    with sqlite3.connect(str(DB)) as conn:
        upsert_report(conn, b, p, k, rep, key)
        fails = _revalidate(conn, b, p, k)
        fails += _pl_bottomline_check(conn, b, p, k)
        conn.commit()
    print(f"[lp] validation failures: {fails}")
    if fails:
        print("[lp] ABORT: partition does not validate — not pushing")
        return 1

    if args.dry_run:
        print("[lp] dry-run — not pushing")
        return 0

    _ensure_d1_schema()
    stmts = [f"DELETE FROM {t} WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}';" for t in AUDIT_TABLES]
    sqlp = Path(tempfile.gettempdir()) / "d1_lp_clear.sql"
    sqlp.write_text("\n".join(stmts) + "\n", encoding="utf-8")
    print(f"[lp] clearing {b} {p} {k} in D1")
    _retry_wrangler(sqlp, "D1 partition clear")
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "1", "--only-tables", ",".join(AUDIT_TABLES)], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[lp] uploaded snapshot ({size / 1e6:.1f} MB)")
    print("[lp] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
