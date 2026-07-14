"""Copy the bank_audit_* statement tables from one SQLite DB into a standalone audit DB.

Bootstraps `data/bank_audit.db` from the legacy combined snapshot
(`data/bddk_data.db`) when `state/bank_audit.db.gz` is absent — i.e. on the very
first `refresh-audit.yml` run, and thereafter only as disaster recovery. The
seeded rows keep the dashboard populated while extraction catches up.

It seeds statement rows ONLY, never `bank_audit_extractions`: the extraction log
is what tells the scraper a partition is done, so copying it would make a restore
skip the re-extraction it exists to trigger. The R2 PDFs remain the durable
source of truth.

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

from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

# Every audit table EXCEPT the extraction log, derived from the registry so a new
# statement type is seeded without editing this file.
#
# bank_audit_extractions is deliberately NOT copied. sync_audit_reports skips any
# (bank, period, kind) already logged with success=1, so seeding the log would
# make a disaster-recovery restore permanently SKIP re-extraction: the ~1,000
# historical partitions would never be re-read, and every table added after the
# source snapshot was taken would stay empty for the whole corpus. (The old
# hand-written list here dated from 2026-06-05 and named the 8 tables that
# existed then; capital, liquidity, oci, cash_flow, equity_change, fx_position,
# repricing and validation all landed later and were never added.) The R2 PDFs
# are the durable source of truth — after a restore we re-extract them all, and
# the statement rows seeded below just keep the dashboard populated meanwhile.
SEED_TABLES = [t for t in AUDIT_TABLES if t != "bank_audit_extractions"]


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
    for table in SEED_TABLES:
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
