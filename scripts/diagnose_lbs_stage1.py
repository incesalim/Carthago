"""Diagnose loans_by_sector stage1_amount coverage per partition.

Read-only query over the local bank_audit.db (or a supplied --db path).
Produces:
  1. A per-partition table: rows, S1 non-null, S2/S3/ECL non-null.
  2. The list of partitions that would gain S1 data if re-extracted.
  3. A before/after SQL template for Steward verification.

Usage:
  python scripts/diagnose_lbs_stage1.py
  python scripts/diagnose_lbs_stage1.py --db data/bank_audit.db
  python scripts/diagnose_lbs_stage1.py --json   # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_DEFAULT = REPO / "data" / "bank_audit.db"

SQL_BEFORE = """\
-- BEFORE snapshot: stage1 coverage per loans_by_sector partition
SELECT
    bank_ticker, period, kind,
    COUNT(*)                                                AS total_rows,
    SUM(CASE WHEN stage1_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s1_nonnull,
    SUM(CASE WHEN stage2_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s2_nonnull,
    SUM(CASE WHEN stage3_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s3_nonnull,
    SUM(CASE WHEN ecl_amount   IS NOT NULL THEN 1 ELSE 0 END)   AS ecl_nonnull
FROM bank_audit_loans_by_sector
GROUP BY bank_ticker, period, kind
ORDER BY bank_ticker, period, kind;"""

SQL_AFTER = """\
-- AFTER re-extraction: partitions that now carry stage1
-- (compare s1_nonnull against the BEFORE snapshot)
SELECT
    bank_ticker, period, kind,
    COUNT(*)                                                AS total_rows,
    SUM(CASE WHEN stage1_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s1_nonnull,
    SUM(CASE WHEN stage2_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s2_nonnull,
    SUM(CASE WHEN stage3_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s3_nonnull,
    SUM(CASE WHEN ecl_amount   IS NOT NULL THEN 1 ELSE 0 END)   AS ecl_nonnull
FROM bank_audit_loans_by_sector
GROUP BY bank_ticker, period, kind
ORDER BY bank_ticker, period, kind;"""

SQL_GAINED = """\
-- Partitions that would gain S1: currently all NULL for stage1_amount
-- but have data in stage2/stage3/ecl (proven 3-col partitions).
SELECT
    bank_ticker, period, kind,
    COUNT(*)                                         AS total_rows,
    SUM(CASE WHEN stage1_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s1_nonnull,
    SUM(CASE WHEN stage2_amount IS NOT NULL THEN 1 ELSE 0 END)  AS s2_nonnull
FROM bank_audit_loans_by_sector
GROUP BY bank_ticker, period, kind
HAVING s1_nonnull = 0 AND s2_nonnull > 0
ORDER BY bank_ticker, period, kind;"""

COLS_FOUR = ("stage1_amount", "stage2_amount", "stage3_amount", "ecl_amount")


def _query(conn: sqlite3.Connection, db_path: Path) -> list[dict]:
    if not db_path.exists():
        print(f"[diag] DB not found: {db_path}", file=sys.stderr)
        return []
    try:
        rows = conn.execute(
            "SELECT bank_ticker, period, kind, "
            "COUNT(*) AS total_rows, "
            "SUM(CASE WHEN stage1_amount IS NOT NULL THEN 1 ELSE 0 END) AS s1, "
            "SUM(CASE WHEN stage2_amount IS NOT NULL THEN 1 ELSE 0 END) AS s2, "
            "SUM(CASE WHEN stage3_amount IS NOT NULL THEN 1 ELSE 0 END) AS s3, "
            "SUM(CASE WHEN ecl_amount   IS NOT NULL THEN 1 ELSE 0 END) AS ecl "
            "FROM bank_audit_loans_by_sector "
            "GROUP BY bank_ticker, period, kind "
            "ORDER BY bank_ticker, period, kind"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such column: stage1_amount" in str(exc):
            print("[diag] stage1_amount column missing — run migration 0052 first",
                  file=sys.stderr)
            return []
        raise
    return [
        {"bank": r[0], "period": r[1], "kind": r[2],
         "rows": r[3], "s1": r[4], "s2": r[5], "s3": r[6], "ecl": r[7]}
        for r in rows
    ]


def _print_table(data: list[dict]) -> None:
    if not data:
        print("[diag] no loans_by_sector partitions found")
        return
    hdr = f"{'bank':<10} {'period':<10} {'kind':<15} {'rows':>5} {'s1':>5} {'s2':>5} {'s3':>5} {'ecl':>5}"
    print(hdr)
    print("-" * len(hdr))
    for d in data:
        print(f"{d['bank']:<10} {d['period']:<10} {d['kind']:<15} "
              f"{d['rows']:>5} {d['s1']:>5} {d['s2']:>5} {d['s3']:>5} {d['ecl']:>5}")
    print()
    total_partitions = len(data)
    s1_present = sum(1 for d in data if d["s1"] > 0)
    s1_absent = total_partitions - s1_present
    print(f"[diag] {total_partitions} partitions total; "
          f"{s1_present} already have S1; {s1_absent} would gain S1")


def _print_sql_template() -> None:
    print("-- ─── SQL verification template ───")
    print()
    print("-- Step 1: BEFORE (run before re-extraction)")
    print(SQL_BEFORE)
    print()
    print("-- Step 2: AFTER (run after re-extraction)")
    print(SQL_AFTER)
    print()
    print("-- Step 3: Partitions that gained S1")
    print(SQL_GAINED)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_DEFAULT,
                    help="Path to bank_audit.db")
    ap.add_argument("--json", action="store_true",
                    help="Output as JSON instead of a table")
    ap.add_argument("--sql", action="store_true",
                    help="Print the before/after SQL template and exit")
    args = ap.parse_args()

    if args.sql:
        _print_sql_template()
        return 0

    conn = sqlite3.connect(str(args.db))
    data = _query(conn, args.db)
    conn.close()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        _print_table(data)
        print()
        _print_sql_template()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
