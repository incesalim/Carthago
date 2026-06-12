"""Generate one-off D1 DATA-SEED dumps from data/bddk_data.db.

NOTE: this is for *bulk data seeding only* (e.g. first-time hydration of a fresh
D1). The SCHEMA source of truth is the hand-authored, version-controlled
migrations in web/migrations/ (applied via `wrangler d1 migrations apply`).
Routine row updates go through scripts/push_to_d1.py — you rarely need this.

Output goes to web/seeds/ (gitignored, regenerable):
  0001_audit.sql         — bank_audit_* tables
  0002_monthly_core.sql  — balance_sheet, income_statement, loans, deposits,
                           financial_ratios + small reference tables
  0003_monthly_other.sql — other_data only
  0004_weekly.sql        — weekly_series + weekly_bulletin

Run from project root:
    python scripts/generate_d1_migrations.py

Then apply (after the schema migrations) with wrangler:
    cd web
    npx wrangler d1 execute bddk-data --remote --file=seeds/0001_audit.sql
    # …etc for the other seed files
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"
# Data seeds only — schema lives in web/migrations/ (hand-authored, tracked).
OUT = ROOT / "web" / "seeds"

GROUPS = {
    "0001_audit": [
        "bank_types",                    # referenced by FK in audit tables
        "bank_audit_extractions",
        "bank_audit_balance_sheet",
        "bank_audit_profit_loss",
    ],
    "0002_monthly_core": [
        "bank_types",                    # included again so this file is independent
        "table_definitions",
        "download_log",
        "balance_sheet",
        "income_statement",
        "loans",
        "deposits",
        "financial_ratios",
    ],
    "0003_monthly_other": [
        "other_data",
    ],
    "0004_weekly": [
        "weekly_bulletin",
        "weekly_series",
    ],
}

BATCH_SIZE = 100  # rows per INSERT statement


def _strip_foreign_keys(ddl: str) -> str:
    """Remove FOREIGN KEY clauses from a CREATE TABLE statement.

    D1 enforces FK constraints during migrations and DROPs, which makes
    cross-file imports brittle. We don't rely on FKs for analytical queries —
    the bank_type_code values still link logically by string equality.
    """
    # Remove lines like "FOREIGN KEY (bank_type_code) REFERENCES bank_types(code),"
    lines = []
    for ln in ddl.split("\n"):
        if re.search(r"\bFOREIGN\s+KEY\b", ln, re.I):
            continue
        lines.append(ln)
    cleaned = "\n".join(lines)
    # Clean up dangling commas before closing paren: ",\n)"  →  "\n)"
    cleaned = re.sub(r",\s*\n\s*\)", "\n)", cleaned)
    return cleaned


def dump_table(conn: sqlite3.Connection, name: str) -> list[str]:
    """Return SQL statements to recreate `name` and re-insert all its rows."""
    out: list[str] = []
    ddl_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    if ddl_row is None:
        return [f"-- table {name} not found, skipped"]
    out.append(f"DROP TABLE IF EXISTS {name};")
    out.append(_strip_foreign_keys(ddl_row[0]) + ";")

    # Indexes
    for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (name,),
    ):
        out.append(r[0] + ";")

    # Data
    cols = [c[0] for c in conn.execute(f"SELECT * FROM {name} LIMIT 0").description]
    col_list = ",".join(cols)
    n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    if n == 0:
        out.append(f"-- {name}: empty")
        return out

    batch: list[str] = []
    for r in conn.execute(f"SELECT {col_list} FROM {name}"):
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
                f"INSERT INTO {name}({col_list}) VALUES\n" + ",\n".join(batch) + ";"
            )
            batch = []
    if batch:
        out.append(
            f"INSERT INTO {name}({col_list}) VALUES\n" + ",\n".join(batch) + ";"
        )
    out.append(f"-- {name}: {n} rows")
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))

    # Wipe any old single-table migration left from the spike
    for f in OUT.glob("0001_balance_sheet.sql"):
        f.unlink()
        print(f"removed {f}")

    print(f"{'group':<24} {'tables':>3} {'rows':>10} {'size MB':>8}")
    print("-" * 56)
    for group_name, tables in GROUPS.items():
        lines: list[str] = [
            f"-- {group_name}",
            f"-- tables: {', '.join(tables)}",
            "",
        ]
        total_rows = 0
        for t in tables:
            lines.extend(dump_table(conn, t))
            lines.append("")
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            total_rows += n

        path = OUT / f"{group_name}.sql"
        path.write_text("\n".join(lines), encoding="utf-8")
        size_mb = path.stat().st_size / 1024 / 1024
        print(
            f"{group_name:<24} {len(tables):>3} {total_rows:>10,} {size_mb:>8.1f}"
        )
        if size_mb > 95:
            print(f"  ⚠ {group_name} is {size_mb:.0f} MB — close to D1's 100 MB import limit")

    print(f"\nwrote {len(GROUPS)} files to {OUT}")
    print("\nApply with (after `wrangler d1 migrations apply`):")
    for g in GROUPS:
        print(f"  npx wrangler d1 execute bddk-data --remote --file=seeds/{g}.sql")


if __name__ == "__main__":
    main()
