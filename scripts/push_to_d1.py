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

sys.path.insert(0, str(ROOT))
from src.audit_reports.schema import init_schema as _init_audit_schema  # noqa: E402
from src.kap.schema import init_schema as _init_kap_schema              # noqa: E402
from src.news._htmltext import fix_mojibake                            # noqa: E402
from src.news.schema import init_schema as _init_news_schema            # noqa: E402
from src.tefas.schema import init_schema as _init_tefas_schema          # noqa: E402

# Tables whose text values get a final mojibake repair before D1 (Turkish text
# from scrapers / LLM; "Ã/Å/Ä" only ever appear there as mis-encoding).
_MOJIBAKE_TABLES = {"news_items", "regulation_briefings"}

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
    "bank_audit_balance_sheet",
    "bank_audit_profit_loss",
    "bank_audit_oci",
    "bank_audit_credit_quality",
    "bank_audit_profile",
    "bank_audit_loans_by_sector",
    "bank_audit_npl_movement",
    "bank_audit_stages",
    "bank_audit_capital",
    "bank_audit_liquidity",
    "bank_audit_validation",
    "bank_audit_extractions",
    "evds_series",
    "news_items",
    "regulation_briefings",
    "tbb_digital_stats",
    "kap_ownership",
    "tefas_manager_daily",
    "tefas_category_daily",
    "tefas_allocation_daily",
    "tefas_top_funds",
    "bank_audit_expected",
    "bank_audit_statement_types",
    "bank_audit_coverage",
]

# Precomputed rollups with no per-row timestamp: scripts/sync_audit_expected.py
# rebuilds them wholesale, so the push clears the D1 table and re-inserts every
# row (a `--hours` window doesn't apply). Pushed only when named in --only-tables.
_FULL_REBUILD = {
    "bank_audit_expected",
    "bank_audit_statement_types",
    "bank_audit_coverage",
}

BATCH_SIZE = 100  # rows per INSERT statement (default for skinny tables)
# news_items can carry multi-KB body_text per row — batch much smaller so a
# single INSERT statement stays under D1's SQLITE_TOOBIG limit (~1 MB).
BATCH_SIZE_PER_TABLE = {
    "news_items": 10,
    "regulation_briefings": 1,  # categories_json + raw_response are large per row
}

# Stand-in for newline chars in generated SQL literals (see fetch_recent).
# Must be a string that never occurs in real source text.
_NL_SENTINEL = "__D1_NL__"


def fetch_recent(conn: sqlite3.Connection, table: str, hours: int) -> list[str]:
    """Return SQL statements (INSERT OR REPLACE) for rows updated in last `hours`.

    Tables with a `downloaded_at` column are filtered by it.
    bank_audit_* tables don't have one — they're filtered by extracted_at
    in bank_audit_extractions (the parent log table).
    """
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    col_list = ",".join(cols)

    # Full-rebuild rollups: push every row, prefixed by a DELETE so D1 can't keep
    # rows for partitions that are no longer expected (idempotent re-sync).
    full_rebuild = table in _FULL_REBUILD
    if full_rebuild:
        where = ""
    elif "downloaded_at" in cols:
        where = f"WHERE downloaded_at >= datetime('now', '-{hours} hours')"
    elif table == "news_items":
        where = f"WHERE fetched_at >= datetime('now', '-{hours} hours')"
    elif table == "regulation_briefings":
        where = f"WHERE fetched_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_extractions":
        where = f"WHERE extracted_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_validation":
        where = f"WHERE validated_at >= datetime('now', '-{hours} hours')"
    elif table in (
        "bank_audit_credit_quality",
        "bank_audit_profile",
        "bank_audit_loans_by_sector",
        "bank_audit_npl_movement",
        "bank_audit_stages",
        "bank_audit_capital",
        "bank_audit_liquidity",
    ):
        # These tables have their own extracted_at column (the
        # corresponding extractor writes here without touching
        # bank_audit_extractions). Filter on the local timestamp directly.
        where = f"WHERE extracted_at >= datetime('now', '-{hours} hours')"
    elif table in ("bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_oci"):
        # Pull rows whose (bank_ticker, period, kind) was extracted recently
        where = (
            "WHERE (bank_ticker, period, kind) IN ("
            f"  SELECT bank_ticker, period, kind FROM bank_audit_extractions "
            f"  WHERE extracted_at >= datetime('now', '-{hours} hours'))"
        )
    else:
        return [f"-- {table}: no time column, skipped"]

    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    if n == 0 and not full_rebuild:
        return [f"-- {table}: no rows in last {hours}h"]

    if full_rebuild:
        out: list[str] = [f"-- {table}: full rebuild, {n} rows", f"DELETE FROM {table};"]
    else:
        out = [f"-- {table}: {n} rows from last {hours}h"]
    batch: list[str] = []
    batch_size = BATCH_SIZE_PER_TABLE.get(table, BATCH_SIZE)
    repair = table in _MOJIBAKE_TABLES
    rows_iter = conn.execute(f"SELECT {col_list} FROM {table} {where}")
    for r in rows_iter:
        vals = []
        for v in r:
            if v is None:
                vals.append("NULL")
                continue
            if isinstance(v, (int, float)):
                vals.append(str(v))
                continue
            s = fix_mojibake(str(v)) if repair else str(v)
            if "\n" in s or "\r" in s:
                # Don't embed raw newlines in the generated SQL: wrangler's
                # --file parser collapses consecutive blank lines, so '\n\n'
                # in a body (the blank line between a paragraph and a Markdown
                # table) would reach D1 as a single '\n' and the UI could no
                # longer tell blocks apart. Replace newlines with a sentinel
                # (keeps the literal single-line, so nothing collapses) and
                # rebuild them with ONE replace() call — char(10) concatenation
                # would instead blow past SQLite's 100-deep expression limit.
                s = s.replace("\r\n", "\n").replace("\r", "\n")
                s = s.replace("'", "''").replace("\n", _NL_SENTINEL)
                vals.append(f"replace('{s}', '{_NL_SENTINEL}', char(10))")
            else:
                vals.append("'" + s.replace("'", "''") + "'")
        batch.append("(" + ",".join(vals) + ")")
        if len(batch) >= batch_size:
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
    parser.add_argument("--only-tables", type=str, default=None,
                        help="Comma-separated table allow-list. "
                             "E.g. --only-tables=bank_audit_balance_sheet,bank_audit_extractions "
                             "to push just BS data when other tables (e.g. credit_quality) need a migration first.")
    parser.add_argument("--db", type=str, default=str(DB),
                        help="SQLite staging DB to push from (default data/bddk_data.db). "
                             "The audit pipeline passes data/bank_audit.db so it can sync "
                             "the bank_audit_* tables from its own standalone snapshot.")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: {db} not found", file=sys.stderr)
        return 1
    if not (WEB / "wrangler.jsonc").exists():
        print(f"ERROR: {WEB}/wrangler.jsonc not found", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = OFF")
    # The R2 snapshot may predate recent schema additions (new bank_audit_*
    # tables, regulation_briefings). The daily news / EVDS workflows don't
    # run any extractor that would call init_schema, so without this they
    # crash when SYNC_TABLES lists a table that's not in the snapshot. All
    # DDL is `CREATE … IF NOT EXISTS`, so it's a no-op once snapshot is current.
    _init_audit_schema(conn)
    _init_news_schema(conn)
    _init_kap_schema(conn)
    _init_tefas_schema(conn)

    allowed_tables = (
        {t.strip() for t in args.only_tables.split(",") if t.strip()}
        if args.only_tables else None
    )
    lines: list[str] = ["-- incremental D1 push", f"-- window: last {args.hours} hours", ""]
    if allowed_tables:
        lines.append(f"-- table filter: {sorted(allowed_tables)}")
        lines.append("")

    # Replay queued partition-shrink deletes (d1_pending_deletes outbox —
    # written by lanes whose runs replace whole partitions, e.g. KAP
    # ownership) BEFORE the inserts, so D1 can't keep orphan rows that the
    # INSERT OR REPLACE sync would never touch.
    pending = conn.execute(
        "SELECT rowid, sql FROM d1_pending_deletes ORDER BY rowid"
    ).fetchall()
    if pending:
        lines.append(f"-- d1_pending_deletes outbox: {len(pending)} statements")
        lines.extend(stmt for _, stmt in pending)
        lines.append("")

    total_inserts = 0
    for tbl in SYNC_TABLES:
        if allowed_tables is not None and tbl not in allowed_tables:
            continue
        block = fetch_recent(conn, tbl, args.hours)
        lines.extend(block)
        lines.append("")
        total_inserts += sum(1 for ln in block if ln.startswith("INSERT"))

    if total_inserts == 0 and not pending:
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
    if pending:
        conn.executemany(
            "DELETE FROM d1_pending_deletes WHERE rowid = ?",
            [(rid,) for rid, _ in pending],
        )
        conn.commit()
        print(f"cleared {len(pending)} replayed outbox deletes")
    print("D1 push complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
