"""One-time hierarchy-key normalization — the durable companion to loader._canon_hier.

A few banks' source PDFs print sub-item hierarchy codes with a trailing dot
("1.1." / "2.1." — KUVEYT) where the BRSA standard (every other bank) is "1.1" /
"2.1". The extractor captured them verbatim, but consumers that key on the exact
code — the per-bank Financials table and the cross-bank heatmap — then can't match
those rows, so the numbers silently vanish from the UI.

`loader._canon_hier` now strips them on every WRITE so it can't recur. This script
fixes the EXISTING data — the R2 snapshot (master) AND the live D1 — for the four
statement tables that carry a hierarchy column. Values are never touched, only the
key string. Idempotent (already-clean rows don't match). `--dry-run` reports scope.

  python scripts/normalize_hierarchy_keys.py --dry-run
  python scripts/normalize_hierarchy_keys.py
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.audit_d1 import retry_wrangler, push_snapshot, _guard_against_ci_writers  # noqa: E402

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"
# (table, extra-WHERE prefix). Only the catalog-displayed statements are normalised —
# matching loader._NORMALIZE_HIER. off_balance keeps its dotted convention (~24k rows,
# 19 banks, not UI-keyed); oci/cash_flow aren't keyed by the UI either.
TABLES = (
    ("bank_audit_balance_sheet", "statement IN ('assets', 'liabilities') AND "),
    ("bank_audit_profit_loss", ""),
)
# A multi-level NUMERIC code ending in a dot ("1.1.", "2.3.1.") — NOT Roman codes
# ("I.", "XVI."), single-level numerics ("1.") or synthetic suffixes ("1.1.ecl").
# Mirrors loader._canon_hier in pure SQL.
DOT = "hierarchy GLOB '*[0-9].[0-9]*' AND hierarchy LIKE '%.'"
SET = "hierarchy = substr(hierarchy, 1, length(hierarchy) - 1)"


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not dry:
        _guard_against_ci_writers()
    r2_storage.download_to(SNAP, str(GZ))
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[nh] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    total = 0
    with sqlite3.connect(str(DB)) as conn:
        for t, extra in TABLES:
            where = f"{extra}{DOT}"
            n = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {where}").fetchone()[0]
            banks = sorted({r[0] for r in conn.execute(
                f"SELECT DISTINCT bank_ticker FROM {t} WHERE {where}")})
            print(f"[nh] {t}: {n} rows to normalize ({', '.join(banks) or 'none'})")
            total += n
            if not dry and n:
                conn.execute(f"UPDATE {t} SET {SET} WHERE {where}")
        conn.commit()

    if dry:
        print(f"[nh] dry-run — {total} rows would normalize; no D1/snapshot write")
        return 0
    if total == 0:
        print("[nh] nothing to normalize")
        return 0

    sql = ";\n".join(f"UPDATE {t} SET {SET} WHERE {extra}{DOT}" for t, extra in TABLES) + ";\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        sql_path = Path(f.name)
    try:
        retry_wrangler(sql_path, "D1 hierarchy-key normalize")
    finally:
        sql_path.unlink(missing_ok=True)
    print("[nh] D1 normalized")

    push_snapshot(DB)
    print("[nh] uploaded snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
