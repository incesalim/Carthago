"""Re-extract ONE PDF and replace ONLY its profit_loss rows in the prod DB + D1.

No fleet loop, no other tables touched — for P&L pages the old extractor garbled
(e.g. letter-spaced ISCTR 2024Q4 unconsolidated, fixed by the _detect_pl_ncols
fitz-fallback). The balance sheet / off-balance / credit-quality rows of the
partition are left exactly as they are; only bank_audit_profit_loss is rewritten.

  python scripts/reextract_pl.py --bank ISCTR --period 2024Q4 --kind unconsolidated
  python scripts/reextract_pl.py ... --dry-run     # local DB only, no D1/snapshot
"""
from __future__ import annotations

import argparse
import gzip
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
from src.audit_reports.extractor import extract  # noqa: E402
from scripts.audit_d1 import (  # noqa: E402
    _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--kind", required=True, choices=["consolidated", "unconsolidated"])
    ap.add_argument("--dry-run", action="store_true", help="rewrite local DB only; no D1 push / snapshot")
    args = ap.parse_args()
    b, p, k = args.bank.upper(), args.period.upper(), args.kind
    key = f"{b.lower()}/{b}_{p}_{k}.pdf"

    if not args.dry_run:
        _guard_against_ci_writers()
        r2_storage.download_to(SNAP, GZ)
        with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
            shutil.copyfileobj(s, d)
        print(f"[pl] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    with tempfile.TemporaryDirectory(prefix="bddk_pl_") as td:
        pdf = Path(td) / "r.pdf"
        r2_storage.download_to(key, str(pdf))
        rep = extract(str(pdf))
    pl = rep.profit_loss
    print(f"[pl] {b} {p} {k}: extracted {len(pl)} profit_loss rows")
    if len(pl) < 20:
        print("[pl] ABORT: <20 P&L rows — extraction looks bad, refusing to overwrite")
        return 1

    with sqlite3.connect(str(DB)) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?",
            (b, p, k)).fetchone()[0]
        conn.execute("DELETE FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?",
                     (b, p, k))
        conn.executemany(
            "INSERT INTO bank_audit_profit_loss "
            "(bank_ticker,period,kind,item_order,hierarchy,item_name,footnote,amount) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(b, p, k, r.order, r.hierarchy, r.name, r.footnote, r.cur_amount) for r in pl])
        conn.execute("UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                     "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k))
        conn.commit()
    print(f"[pl] DB profit_loss rows {before} → {len(pl)}")

    if args.dry_run:
        print("[pl] dry-run — not pushing")
        return 0

    _ensure_d1_schema()
    sqlp = Path(tempfile.gettempdir()) / "d1_pl_clear.sql"
    sqlp.write_text(
        f"DELETE FROM bank_audit_profit_loss WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}';\n",
        encoding="utf-8")
    print(f"[pl] clearing {b} {p} {k} profit_loss in D1")
    _retry_wrangler(sqlp, "D1 P&L clear")
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "1", "--only-tables", "bank_audit_profit_loss"], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[pl] uploaded snapshot ({size / 1e6:.1f} MB)")
    print("[pl] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
