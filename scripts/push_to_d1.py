"""Push recent rows from local SQLite to Cloudflare D1.

Runs after `refresh.py` (in GitHub Actions or locally). For each table we sync,
pulls rows whose `downloaded_at` is within the last N hours (default 48) and
INSERT OR REPLACEs them into D1 via `wrangler d1 execute --remote --file=...`.

INSERT OR REPLACE is idempotent — re-running is safe; existing rows get
overwritten with identical data.

Usage:
    python scripts/push_to_d1.py             # default window 48h
    python scripts/push_to_d1.py --hours 168 # one week back

Env:
    CLOUDFLARE_API_TOKEN   (required) — wrangler picks this up automatically
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"
WEB = ROOT / "web"

# Tables to sync. Each entry: (table_name, has_downloaded_at)
# We only sync tables that have a `downloaded_at` column for incremental
# filtering. Reference tables (bank_types, table_definitions) rarely change
# and were loaded by the initial migration.
SYNC_TABLES = [
    "balance_sheet",
    "income_statement",
    "loans",
    "deposits",
    "financial_ratios",
    "other_data",
    "weekly_series",
    "weekly_bulletin",
    "bank_audit_balance_sheet",
    "bank_audit_profit_loss",
    "bank_audit_extractions",
    "evds_series",
]

BATCH_SIZE = 100  # rows per INSERT statement


def fetch_recent(conn: sqlite3.Connection, table: str, hours: int) -> list[str]:
    """Return SQL statements (INSERT OR REPLACE) for rows updated in last `hours`.

    Tables with a `downloaded_at` column are filtered by it.
    bank_audit_* tables don't have one — they're filtered by extracted_at
    in bank_audit_extractions (the parent log table).
    """
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    col_list = ",".join(cols)

    if "downloaded_at" in cols:
        where = f"WHERE downloaded_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_extractions":
        where = f"WHERE extracted_at >= datetime('now', '-{hours} hours')"
    elif table in ("bank_audit_balance_sheet", "bank_audit_profit_loss"):
        # Pull rows whose (bank_ticker, period, kind) was extracted recently
        where = (
            "WHERE (bank_ticker, period, kind) IN ("
            f"  SELECT bank_ticker, period, kind FROM bank_audit_extractions "
            f"  WHERE extracted_at >= datetime('now', '-{hours} hours'))"
        )
    else:
        return [f"-- {table}: no time column, skipped"]

    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    if n == 0:
        return [f"-- {table}: no rows in last {hours}h"]

    out: list[str] = [f"-- {table}: {n} rows from last {hours}h"]
    batch: list[str] = []
    rows_iter = conn.execute(f"SELECT {col_list} FROM {table} {where}")
    for r in rows_iter:
        vals = []
        for v in r:
            if v is None:
                vals.append("NULL")
            elif isinstance(v, (int, float)):
                vals.append(str(v))
            else:
                s = str(v).replace("'", "''")
                vals.append(f"'{s}'")
        batch.append("(" + ",".join(vals) + ")")
        if len(batch) >= BATCH_SIZE:
            out.append(
                f"INSERT OR REPLACE INTO {table}({col_list}) VALUES\n"
                + ",\n".join(batch)
                + ";"
            )
            batch = []
    if batch:
        out.append(
            f"INSERT OR REPLACE INTO {table}({col_list}) VALUES\n"
            + ",\n".join(batch)
            + ";"
        )
    return out


def run_wrangler(sql_path: Path) -> int:
    """Execute the SQL file against the remote D1 database."""
    cmd = [
        "npx",
        "--yes",
        "wrangler",
        "d1",
        "execute",
        "bddk-data",
        "--remote",
        f"--file={sql_path}",
    ]
    print(f"$ {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=str(WEB), shell=os.name == "nt")
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=48,
                        help="Sync rows updated in the last N hours (default 48)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate SQL file but don't execute it")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: {DB} not found", file=sys.stderr)
        return 1
    if not (WEB / "wrangler.jsonc").exists():
        print(f"ERROR: {WEB}/wrangler.jsonc not found", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB))
    conn.execute("PRAGMA foreign_keys = OFF")

    lines: list[str] = ["-- incremental D1 push", f"-- window: last {args.hours} hours", ""]
    total_inserts = 0
    for tbl in SYNC_TABLES:
        block = fetch_recent(conn, tbl, args.hours)
        lines.extend(block)
        lines.append("")
        total_inserts += sum(1 for ln in block if ln.startswith("INSERT"))

    if total_inserts == 0:
        print(f"no new rows in last {args.hours}h — nothing to push")
        return 0

    sql_path = Path(tempfile.gettempdir()) / "d1_incremental.sql"
    sql_path.write_text("\n".join(lines), encoding="utf-8")
    size_mb = sql_path.stat().st_size / 1024 / 1024
    print(f"generated {sql_path} ({total_inserts} INSERT batches, {size_mb:.2f} MB)")

    if args.dry_run:
        print("dry-run — skipping wrangler execute")
        return 0

    rc = run_wrangler(sql_path)
    if rc != 0:
        print(f"wrangler failed with exit code {rc}", file=sys.stderr)
        return rc
    print("D1 push complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
