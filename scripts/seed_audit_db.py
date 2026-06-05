"""Copy the bank_audit_* tables from one SQLite DB into a standalone audit DB.

Bootstraps `data/bank_audit.db` from the legacy combined snapshot
(`data/bddk_data.db`) the first time `refresh-audit.yml` runs — so the audit
pipeline doesn't have to re-extract all ~949 PDFs from R2 just to populate a
fresh standalone snapshot. After this seed, audit data lives in its own DB
(and its own R2 snapshot `state/bank_audit.db.gz`), fully decoupled from the
BDDK-bulletin DB.

Idempotent: INSERT OR REPLACE keyed on each table's primary key, so re-running
overwrites rather than duplicates. Only columns present in BOTH databases are
copied, so a schema-drifted source can't break the copy.

Usage:
    python scripts/seed_audit_db.py [--from data/bddk_data.db] [--to data/bank_audit.db]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.audit_reports.schema import init_schema  # noqa: E402

# The full bank_audit_* surface — must match src/audit_reports/schema.py DDL
# and the audit subset of scripts/push_to_d1.py SYNC_TABLES.
AUDIT_TABLES = [
    "bank_audit_extractions",
    "bank_audit_balance_sheet",
    "bank_audit_profit_loss",
    "bank_audit_credit_quality",
    "bank_audit_profile",
    "bank_audit_loans_by_sector",
    "bank_audit_npl_movement",
    "bank_audit_stages",
]


def seed(src: Path, dst: Path) -> int:
    if not src.exists():
        print(f"ERROR: source {src} not found", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dst))
    conn.execute("PRAGMA foreign_keys = OFF")
    init_schema(conn)  # create the bank_audit_* tables in the target

    conn.execute("ATTACH DATABASE ? AS src", (str(src),))
    src_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM src.sqlite_master WHERE type='table'"
        )
    }

    total = 0
    for table in AUDIT_TABLES:
        if table not in src_tables:
            print(f"  {table:<30} not in source — skipped")
            continue
        # Intersect columns so a source missing a newer column (e.g. an old
        # snapshot pre-dating rows_credit_quality) still copies cleanly.
        tgt_cols = [c[1] for c in conn.execute(f"PRAGMA main.table_info({table})")]
        src_cols = {c[1] for c in conn.execute(f"PRAGMA src.table_info({table})")}
        cols = [c for c in tgt_cols if c in src_cols]
        col_list = ",".join(cols)
        conn.execute(
            f"INSERT OR REPLACE INTO main.{table}({col_list}) "
            f"SELECT {col_list} FROM src.{table}"
        )
        n = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        print(f"  {table:<30} {n} rows")
        total += n

    conn.commit()
    conn.execute("DETACH DATABASE src")
    conn.close()
    print(f"seeded {dst} ({total} audit rows total)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", default=str(ROOT / "data" / "bddk_data.db"),
                    help="source DB holding the existing bank_audit_* tables")
    ap.add_argument("--to", dest="dst", default=str(ROOT / "data" / "bank_audit.db"),
                    help="target standalone audit DB to create / fill")
    args = ap.parse_args()
    return seed(Path(args.src), Path(args.dst))


if __name__ == "__main__":
    sys.exit(main())
