"""One-time roman-hierarchy normalization — companion to loader._canon_hier.

A few banks' source PDFs print a top-level ROMAN code WITHOUT its trailing dot
("XI" Personnel Expenses, "I" Financial Assets, "V" Dividend Income) where the BRSA
standard is "XI." / "I." / "V.". Consumers that key on the exact code — the per-bank
Financials table and the cross-bank heatmap — then can't match those rows, so the
numbers silently vanish from the UI. Worst case: a dotless asset roman ("I" =
Financial Assets, ALNTF) drops out of the SUMMED total assets, so the bank reads
~40-50% smaller in every affected quarter (a fake q/q crater on /banks).

`loader._canon_hier` now ADDS the dot on every WRITE so it can't recur. This script
fixes the EXISTING data — the R2 snapshot (master) AND the live D1 — for the two
catalog-displayed statement tables. Values are never touched, only the key string.

Two classes of row are DELIBERATELY skipped, both mis-extracted CONTENT (not dot)
bugs the dot-canonicalisation must not paper over:
  • a bank's post-merger line keyed "X" where a real "X." (Other Provisions) already
    exists for the same filing — dotting would duplicate the code (COLLISION GUARD:
    skip when a dotted twin already exists); and
  • TOMK 2023Q3 "XI" whose content is Other Operating Expenses (semantically XII.),
    not Personnel — dotting would mislabel it XI. (SEMANTIC GUARD on the item name).

Idempotent (already-dotted rows don't match). `--dry-run` reports scope, no write.

  python scripts/normalize_roman_hierarchy.py --dry-run
  python scripts/normalize_roman_hierarchy.py
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
from scripts.audit_d1 import (  # noqa: E402
    guard_against_ci_writers,
    push_snapshot,
    retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"

# A bare ROMAN-numeral code — roman letters only, no dot, no digits.
_ROMAN = "hierarchy GLOB '[IVXLCDM]*' AND NOT hierarchy GLOB '*[^IVXLCDM]*'"


def _where(table: str, has_statement: bool) -> str:
    """The predicate selecting bare-roman rows that are SAFE to dot: skip a code
    whose dotted twin already exists in the same filing (collision), and — in the
    P&L — skip an "XI" that is actually Other Operating Expenses (semantically XII.)."""
    stmt_pre = "statement IN ('assets', 'liabilities') AND " if has_statement else ""
    stmt_twin = f" AND q.statement = {table}.statement" if has_statement else ""
    w = (
        f"{stmt_pre}{_ROMAN} "
        f"AND NOT EXISTS (SELECT 1 FROM {table} q "
        f"WHERE q.bank_ticker = {table}.bank_ticker "
        f"AND q.period = {table}.period AND q.kind = {table}.kind{stmt_twin} "
        f"AND q.hierarchy = {table}.hierarchy || '.')"
    )
    if not has_statement:  # profit_loss: never dot the other-opex mislabel
        w += (
            " AND NOT (hierarchy = 'XI' AND "
            "(item_name LIKE '%OTHER OPERATING EXP%' OR item_name LIKE '%FAAL%YET G%DER%'))"
        )
    return w


# (table, has_statement-column)
TABLES = (
    ("bank_audit_balance_sheet", True),
    ("bank_audit_profit_loss", False),
)


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not dry:
        guard_against_ci_writers()
    r2_storage.download_to(SNAP, str(GZ))
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[nr] pulled snapshot -> {DB.stat().st_size / 1e6:.1f} MB")

    total = 0
    updates: list[str] = []
    with sqlite3.connect(str(DB)) as conn:
        for table, has_stmt in TABLES:
            where = _where(table, has_stmt)
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
            banks = sorted({r[0] for r in conn.execute(
                f"SELECT DISTINCT bank_ticker FROM {table} WHERE {where}")})
            print(f"[nr] {table}: {n} bare-roman rows to dot ({', '.join(banks) or 'none'})")
            total += n
            upd = f"UPDATE {table} SET hierarchy = hierarchy || '.' WHERE {where}"
            updates.append(upd)
            if not dry and n:
                conn.execute(upd)
        conn.commit()

    if dry:
        print(f"[nr] dry-run — {total} rows would be dotted; no D1/snapshot write")
        return 0
    if total == 0:
        print("[nr] nothing to normalize")
        return 0

    sql = ";\n".join(updates) + ";\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        sql_path = Path(f.name)
    try:
        retry_wrangler(sql_path, "D1 roman-hierarchy normalize")
    finally:
        sql_path.unlink(missing_ok=True)
    print("[nr] D1 normalized")

    push_snapshot(DB)
    print("[nr] uploaded snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
