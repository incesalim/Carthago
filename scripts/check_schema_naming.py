#!/usr/bin/env python3
"""Guard: new D1 migrations follow docs/SCHEMA_CONVENTIONS.md naming rules.

The schema grew lane-by-lane, so the bank identifier ended up spelled three ways
(`bank_ticker` / `ticker` / `symbol`), the fx leg three ways (`amount_fc` /
`amount_fx` / `amount_yp`), and so on. SQLite/D1 enforces none of this, so drift
is invisible until a cross-lane join or the text-to-SQL bot picks the wrong
column. This check moves that cost forward to PR time.

Existing tables are GRANDFATHERED — retrofitting live tables is churn. Enforcement
applies only to migrations numbered >= FIRST_ENFORCED; earlier ones are scanned
only for the informational drift report. Run standalone
(`python scripts/check_schema_naming.py`) — exits non-zero on a violation in the
enforced range — or via pytest (tests/test_schema_naming.py). Pure stdlib.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "web" / "migrations"

# Migrations with a number >= this are held to the conventions. Everything before
# it predates SCHEMA_CONVENTIONS.md and is grandfathered (see the doc's Exceptions).
FIRST_ENFORCED = 22

# The one duplicate migration number that already exists (0007_tefas_funds.sql +
# 0007_kap_ownership_subsidiaries.sql). Grandfathered; any NEW dup fails.
GRANDFATHERED_DUP_NUMBERS = {"0007"}

# The canonical `banks` dimension keys on the bare `ticker` (== the value stored
# as bank_ticker in fact tables); it's the one table exempt from the synonym rule.
DIMENSION_TABLES = {"banks"}

# concept -> the exact column spellings that are NOT the canonical one.
BANK_ID_SYNONYMS = {"ticker", "symbol", "bank_id", "bank_code", "bankid"}  # -> bank_ticker
FX_LEG_BANNED = {"amount_fx"}  # -> amount_fc

# SQLite keywords that read like plausible column names — avoid (need quoting).
SQLITE_RESERVED = frozenset({
    "add", "all", "alter", "and", "as", "begin", "between", "by", "case", "cast",
    "check", "collate", "column", "commit", "constraint", "create", "cross",
    "current_date", "current_time", "current_timestamp", "default", "delete",
    "distinct", "drop", "else", "end", "escape", "except", "exists", "filter",
    "foreign", "from", "full", "glob", "group", "having", "in", "index", "inner",
    "insert", "intersect", "into", "is", "join", "key", "left", "like", "limit",
    "natural", "not", "null", "offset", "on", "or", "order", "outer", "over",
    "partition", "primary", "range", "references", "right", "rollback", "row",
    "select", "set", "table", "then", "transaction", "trigger", "union", "unique",
    "update", "using", "values", "view", "when", "where", "window",
})

IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_CONSTRAINT_STARTS = {"primary", "unique", "foreign", "check", "constraint", "key"}
_CREATE_TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\[`]?(\w+)["\]`]?\s*\(', re.I
)
_ALTER_ADD_RE = re.compile(
    r'ALTER\s+TABLE\s+["\[`]?(\w+)["\]`]?\s+ADD\s+(?:COLUMN\s+)?["\[`]?(\w+)', re.I
)


def _matching_paren(sql: str, open_idx: int) -> int:
    """Index of the ')' matching the '(' at open_idx."""
    depth = 0
    for i in range(open_idx, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(sql)


def _split_top_level(body: str) -> list[str]:
    """Split a CREATE TABLE body on commas that are not inside parens
    (so DECIMAL(20, 2) / CHECK(...) don't get split)."""
    parts: list[str] = []
    depth, cur = 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _strip_ident(tok: str) -> str:
    return tok.strip().strip('"').strip("`").strip("[").strip("]").strip()


def iter_tables(sql: str):
    """Yield (table_name, [column, ...]) for each CREATE TABLE (views excluded).
    Identifiers keep their original case so the snake_case rule can see camelCase;
    membership checks (reserved/synonym) lower-case at comparison time."""
    for m in _CREATE_TABLE_RE.finditer(sql):
        open_idx = m.end() - 1
        body = sql[open_idx + 1 : _matching_paren(sql, open_idx)]
        cols = []
        for seg in _split_top_level(body):
            seg = seg.strip()
            if not seg:
                continue
            ident = _strip_ident(seg.split()[0])
            if ident.lower() in _CONSTRAINT_STARTS:
                continue
            cols.append(ident)
        yield m.group(1), cols


def iter_alter_adds(sql: str):
    """Yield (table, added_column) for each ALTER TABLE ... ADD COLUMN."""
    for m in _ALTER_ADD_RE.finditer(sql):
        yield m.group(1), m.group(2)


def migration_number(name: str) -> str:
    return name[:4]


def find_duplicate_numbers(names) -> dict[str, list[str]]:
    by_num: dict[str, list[str]] = defaultdict(list)
    for name in names:
        by_num[migration_number(name)].append(name)
    return {
        num: sorted(files)
        for num, files in by_num.items()
        if len(files) > 1 and num not in GRANDFATHERED_DUP_NUMBERS
    }


def _column_violations(table: str, col: str) -> list[str]:
    out = []
    low = col.lower()
    if not IDENT_RE.match(col):
        out.append(f"`{table}.{col}`: not snake_case (^[a-z][a-z0-9_]*$)")
    if low in SQLITE_RESERVED:
        out.append(f"`{table}.{col}`: SQLite reserved word - rename")
    if low in BANK_ID_SYNONYMS and table.lower() not in DIMENSION_TABLES:
        out.append(f"`{table}.{col}`: bank id must be `bank_ticker` (or `bist_symbol`)")
    if low in FX_LEG_BANNED:
        out.append(f"`{table}.{col}`: canonical fx leg is `amount_fc`")
    return out


def lint(migrations: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (errors, notes). errors fail CI; notes are the drift report."""
    errors: list[str] = []
    dupes = find_duplicate_numbers(migrations.keys())
    for num, files in sorted(dupes.items()):
        errors.append(f"duplicate migration number {num}: {', '.join(files)}")

    # Enforced structural checks, only for the enforced range.
    bank_id_spellings: dict[str, set[str]] = defaultdict(set)
    fx_spellings: dict[str, set[str]] = defaultdict(set)
    for name in sorted(migrations):
        try:
            enforced = int(migration_number(name)) >= FIRST_ENFORCED
        except ValueError:
            continue
        sql = migrations[name]
        pairs = [(t, c) for t, cols in iter_tables(sql) for c in cols]
        pairs += list(iter_alter_adds(sql))
        for table, col in pairs:
            low = col.lower()
            # Drift report accounting (all migrations).
            if table.lower() not in DIMENSION_TABLES:
                if low in {"bank_ticker", "ticker", "symbol"}:
                    bank_id_spellings[low].add(table)
                if low in {"amount_fc", "amount_fx", "amount_yp", "amount_tp"}:
                    fx_spellings[low].add(table)
            if enforced:
                if not IDENT_RE.match(table):
                    errors.append(f"`{table}`: table not snake_case")
                if table.lower() in SQLITE_RESERVED:
                    errors.append(f"`{table}`: SQLite reserved word - rename")
                errors.extend(f"{name}: {v}" for v in _column_violations(table, col))

    notes: list[str] = []
    if len(bank_id_spellings) > 1:
        detail = "; ".join(
            f"{col} ({len(tbls)})" for col, tbls in sorted(bank_id_spellings.items())
        )
        notes.append(f"bank-id column spelled {len(bank_id_spellings)} ways: {detail} -> new tables must use `bank_ticker`")
    if len(fx_spellings) > 1:
        notes.append("fx-leg column spelled: " + ", ".join(sorted(fx_spellings)) + " -> new tables use `amount_fc`")
    return sorted(set(errors)), notes


def load_migrations() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in MIGRATIONS_DIR.glob("*.sql")
    }


def check() -> tuple[list[str], list[str]]:
    return lint(load_migrations())


def main() -> int:
    if not MIGRATIONS_DIR.is_dir():
        print(f"migrations dir not found: {MIGRATIONS_DIR}", file=sys.stderr)
        return 1
    migrations = load_migrations()
    errors, notes = lint(migrations)
    for note in notes:
        print(f"  note: {note}")
    if errors:
        print(
            f"\nschema naming violations (enforced for migrations >= {FIRST_ENFORCED:04d}):",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nSee docs/SCHEMA_CONVENTIONS.md.", file=sys.stderr)
        return 1
    print(f"schema naming OK ({len(migrations)} migrations; enforced >= {FIRST_ENFORCED:04d}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
