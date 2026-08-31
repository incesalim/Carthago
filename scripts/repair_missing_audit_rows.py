"""Repair narrowly proven D1 drift from the authoritative R2 audit snapshot.

Read-only by default; apply only through repair-missing-audit-rows.yml. Grouped
counts discover whole and partial losses. Every affected partition must be a
strict factual multiset subset of the snapshot before ANY table is written.
Equal-count partitions are outside this missing-row repair's scope, not a claim
that all their values have been audited. No PDF extraction or timestamp updates.

The opt-in remote-extra mode is stricter: it requires exact partition triples,
proves D1 is a factual multiset superset of the snapshot, and deletes only the
extra rows by their complete primary keys. Canonical rows are never re-stamped.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_d1 import _wrangler_json, push_snapshot, retry_wrangler  # noqa: E402

# Explicitly partitioned sync tables only. Never a full-rebuild rollup or a
# SQLite-only source-line table. Adding a new table requires code review.
ALLOWED_TABLES = (
    "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_oci",
    "bank_audit_cash_flow", "bank_audit_equity_change", "bank_audit_credit_quality",
    "bank_audit_profile", "bank_audit_loans_by_sector", "bank_audit_npl_movement",
    "bank_audit_opinion", "bank_audit_free_provision", "bank_audit_stages",
    "bank_audit_capital", "bank_audit_liquidity", "bank_audit_fx_position",
    "bank_audit_repricing", "bank_audit_pl_roles", "bank_audit_document_manifest",
    "bank_audit_capture_manifest", "bank_audit_validation", "bank_audit_extractions",
    "bank_audit_prose",
)
PART_COLUMNS = ("bank_ticker", "period", "kind")
# Only ingestion bookkeeping and surrogate IDs are excluded. source_page,
# item_order, provenance, null amounts, and every other shared column are facts.
IGNORED_COLUMNS = frozenset({
    "id", "extracted_at", "derived_at", "validated_at", "captured_at",
    "downloaded_at", "created_at", "updated_at",
})
BATCH_PARTITIONS = 12
Part = tuple[str, str, str]


@dataclass
class TableRepair:
    table: str
    columns: tuple[str, ...]
    source: dict[Part, list[dict]]
    missing_rows: int


@dataclass
class ExtraRepair:
    table: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    source: dict[Part, list[dict]]
    extras: dict[Part, list[dict]]


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cursor = conn.execute(sql)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor]


def _remote(sql: str) -> list[dict]:
    results = _wrangler_json(sql, "missing audit row recovery read")
    if (not isinstance(results, list) or len(results) != 1
            or results[0].get("success") is not True
            or not isinstance(results[0].get("results"), list)):
        raise RuntimeError("D1 did not return one complete successful read; refusing repair")
    return results[0]["results"]


def _part(row: dict) -> Part:
    values = tuple(row[k] for k in PART_COLUMNS)
    if (not all(isinstance(v, str) for v in values)
            or re.fullmatch(r"[A-Z0-9]{2,16}", values[0]) is None
            or re.fullmatch(r"\d{4}Q[1-4]", values[1]) is None
            or values[2] not in {"consolidated", "unconsolidated"}):
        raise ValueError(f"Invalid audit partition key: {values!r}")
    return values


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _part_scope(parts: list[Part]) -> str:
    values = ",".join("(" + ",".join(map(_literal, part)) + ")" for part in parts)
    return "(bank_ticker,period,kind) IN (VALUES " + values + ")"


def _affinity(declaration: str) -> str:
    declaration = declaration.upper()
    if "INT" in declaration:
        return "INTEGER"
    if any(token in declaration for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not declaration or "BLOB" in declaration:
        return "BLOB"
    if any(token in declaration for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def factual_columns(source_schema: list[dict], remote_schema: list[dict]) -> tuple[str, ...]:
    source = {r["name"] for r in source_schema}
    remote = {r["name"] for r in remote_schema}
    if not set(PART_COLUMNS) <= source or not set(PART_COLUMNS) <= remote:
        raise ValueError("Missing snapshot/D1 table or partition columns; nothing written")
    # A replacement must not discard remote-only facts or send columns absent
    # from D1. Even bookkeeping schema drift requires the normal migration path.
    if source != remote:
        raise ValueError(f"Snapshot/D1 schema differs: {sorted(source ^ remote)}; nothing written")
    if any(re.fullmatch(r"[a-z][a-z0-9_]*", name) is None for name in source):
        raise ValueError("Unexpected column identifier; nothing written")
    source_info = {row["name"]: row for row in source_schema}
    remote_info = {row["name"]: row for row in remote_schema}
    for name in source:
        left, right = source_info[name], remote_info[name]
        if left["pk"] != right["pk"]:
            raise ValueError(f"Snapshot/D1 primary key differs for {name}; nothing written")
        if name not in IGNORED_COLUMNS and (
                _affinity(left["type"]) != _affinity(right["type"])
                or left["notnull"] != right["notnull"]):
            raise ValueError(f"Snapshot/D1 factual column type/nullability differs for {name}; nothing written")
    return tuple(sorted(source - IGNORED_COLUMNS))


def primary_key_columns(schema: list[dict]) -> tuple[str, ...]:
    ordered = sorted((row["pk"], row["name"]) for row in schema if row["pk"])
    if not ordered or [position for position, _ in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("Table has no complete ordered primary key; nothing written")
    columns = tuple(name for _, name in ordered)
    if not set(PART_COLUMNS) <= set(columns):
        raise ValueError("Primary key does not contain the audit partition; nothing written")
    info = {row["name"]: row for row in schema}
    if any(not info[name]["notnull"] for name in columns):
        raise ValueError("Primary key permits nulls; nothing written")
    return columns


def factual_rows(rows: list[dict], columns: tuple[str, ...]) -> Counter:
    """A multiset, not a set: duplicate multiplicity and null versus zero matter."""
    return Counter(tuple(row[column] for column in columns) for row in rows)


def missing_rows(source: list[dict], remote: list[dict], columns: tuple[str, ...]) -> int:
    wanted, actual = factual_rows(source, columns), factual_rows(remote, columns)
    if actual - wanted:
        raise ValueError("D1 has differing or extra facts; snapshot is not a safe superset")
    return sum((wanted - actual).values())


def remote_extra_rows(source: list[dict], remote: list[dict],
                      columns: tuple[str, ...]) -> list[dict]:
    """Return only remote rows beyond an identical snapshot multiset."""
    wanted, actual = factual_rows(source, columns), factual_rows(remote, columns)
    if wanted - actual:
        raise ValueError("D1 is missing or differs from snapshot facts; refusing deletion")
    remaining = actual - wanted
    extras = []
    for row in remote:
        fact = tuple(row[column] for column in columns)
        if remaining[fact]:
            extras.append(row)
            remaining[fact] -= 1
    if any(remaining.values()):
        raise ValueError("Could not identify every remote-extra row; nothing written")
    return extras


def _counts(read, table: str, scope: str) -> dict[Part, int]:
    groups = read(f"SELECT bank_ticker,period,kind,COUNT(*) AS n FROM {table} "
                  f"WHERE {scope} GROUP BY bank_ticker,period,kind")
    totals = read(f"SELECT COUNT(*) AS n FROM {table} WHERE {scope}")
    counts: dict[Part, int] = {}
    for row in groups:
        part, count = _part(row), row["n"]
        if part in counts or type(count) is not int or count < 1:
            raise ValueError(f"Invalid grouped count from {table}; nothing written")
        counts[part] = count
    if (len(totals) != 1 or type(totals[0].get("n")) is not int
            or sum(counts.values()) != totals[0]["n"]):
        raise ValueError(f"Incomplete or changing grouped counts for {table}; nothing written")
    return counts


def _partition_rows(read, table: str, columns: tuple[str, ...], parts: list[Part],
                    expected_counts: dict[Part, int]) -> dict[Part, list[dict]]:
    grouped: dict[Part, list[dict]] = {part: [] for part in parts}
    for offset in range(0, len(parts), BATCH_PARTITIONS):
        batch = parts[offset:offset + BATCH_PARTITIONS]
        rows = read(f"SELECT {','.join(columns)} FROM {table} WHERE {_part_scope(batch)}")
        for row in rows:
            part = _part(row)
            if part not in batch:
                raise ValueError(f"D1 returned an unrequested partition for {table}")
            # Validate presence of every factual column, including nulls.
            tuple(row[c] for c in columns)
            grouped[part].append(row)
    for part, rows in grouped.items():
        if len(rows) != expected_counts.get(part, 0):
            raise ValueError(f"Incomplete or changing rows for {table} {'|'.join(part)}; nothing written")
    return grouped


def plan_repairs(conn: sqlite3.Connection, tables: list[str], scope: str) -> list[TableRepair]:
    """Finish every table's conflict preflight before the caller can mutate D1."""
    plans = []
    local = lambda sql: _rows(conn, sql)  # noqa: E731
    # Read all schemas first: a missing late table must never be auto-created by
    # the writer and mistaken for an intentionally empty authoritative source.
    columns_by_table = {}
    for table in tables:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Table is not allowlisted: {table}")
        columns_by_table[table] = factual_columns(
            local(f"PRAGMA table_info({table})"), _remote(f"PRAGMA table_info({table})"))
    for table in tables:
        columns = columns_by_table[table]
        source_counts = _counts(local, table, scope)
        remote_counts = _counts(_remote, table, scope)
        affected = sorted(p for p in source_counts.keys() | remote_counts.keys()
                          if source_counts.get(p, 0) != remote_counts.get(p, 0))
        if not affected:
            print(f"{table}: partition counts agree; no missing rows", flush=True)
            continue
        source = _partition_rows(local, table, columns, affected, source_counts)
        remote = _partition_rows(_remote, table, columns, affected, remote_counts)
        total = 0
        for part in affected:
            try:
                total += missing_rows(source[part], remote[part], columns)
            except ValueError as error:
                raise ValueError(f"{table} {'|'.join(part)}: {error}; nothing written") from error
        plans.append(TableRepair(table, columns, source, total))
        print(f"{table}: restore {total} missing rows in {len(affected)} partitions", flush=True)
    return plans


def verify_repairs(plans: list[TableRepair]) -> None:
    for plan in plans:
        counts = {part: len(rows) for part, rows in plan.source.items()}
        actual = _partition_rows(_remote, plan.table, plan.columns, sorted(plan.source), counts)
        for part, rows in plan.source.items():
            if factual_rows(rows, plan.columns) != factual_rows(actual[part], plan.columns):
                raise RuntimeError(f"Post-repair facts differ: {plan.table} {'|'.join(part)}")


def apply_repairs(db: Path, plans: list[TableRepair]) -> None:
    with tempfile.TemporaryDirectory(prefix="missing-audit-rows-") as td:
        for plan in plans:
            listing = Path(td) / f"{plan.table}.txt"
            listing.write_text("".join("|".join(p) + "\n" for p in sorted(plan.source)), encoding="utf-8")
            # One table's exact keys, never the Cartesian union of all plans.
            # Explicit replacement bypasses timestamp/digest selection, uses
            # full source rows, and leaves unrelated queued deletes untouched.
            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "push_to_d1.py"),
                "--db", str(db), "--only-tables", plan.table,
                "--replace-partitions", str(listing),
            ], check=True)


def plan_extra_repairs(conn: sqlite3.Connection, tables: list[str],
                       parts: list[Part]) -> list[ExtraRepair]:
    """Preflight every exact partition before permitting any remote deletion."""
    plans = []
    local = lambda sql: _rows(conn, sql)  # noqa: E731
    scope = _part_scope(parts)
    schemas = {}
    for table in tables:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Table is not allowlisted: {table}")
        source_schema = local(f"PRAGMA table_info({table})")
        remote_schema = _remote(f"PRAGMA table_info({table})")
        columns = factual_columns(source_schema, remote_schema)
        schemas[table] = (columns, primary_key_columns(source_schema))
    for table in tables:
        columns, primary_key = schemas[table]
        if not set(primary_key) <= set(columns):
            raise ValueError(f"{table} primary key includes ignored bookkeeping columns; nothing written")
        source_counts = _counts(local, table, scope)
        remote_counts = _counts(_remote, table, scope)
        absent = [part for part in parts if source_counts.get(part, 0) < 1]
        if absent:
            raise ValueError(f"{table} has no authoritative rows for "
                             f"{','.join('|'.join(p) for p in absent)}; nothing written")
        source = _partition_rows(local, table, columns, parts, source_counts)
        remote = _partition_rows(_remote, table, columns, parts, remote_counts)
        extras_by_part = {}
        for part in parts:
            for side, rows in (("snapshot", source[part]), ("D1", remote[part])):
                keys = [tuple(row[column] for column in primary_key) for row in rows]
                if len(keys) != len(set(keys)):
                    raise ValueError(f"{table} {'|'.join(part)} has duplicate {side} primary keys; "
                                     "nothing written")
            try:
                extras = remote_extra_rows(source[part], remote[part], columns)
            except ValueError as error:
                raise ValueError(f"{table} {'|'.join(part)}: {error}; nothing written") from error
            if extras:
                extras_by_part[part] = extras
        if extras_by_part:
            # A row delete must identify one and only one remote row. The factual
            # comparison above already rejects a changed canonical row; this
            # catches malformed schemas/responses before SQL is generated.
            keys = [tuple(row[column] for column in primary_key)
                    for rows in extras_by_part.values() for row in rows]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{table} remote extras have duplicate primary keys; nothing written")
            plans.append(ExtraRepair(table, columns, primary_key, source, extras_by_part))
            print(f"{table}: remove {len(keys)} remote-extra rows in "
                  f"{len(extras_by_part)} exact partitions", flush=True)
        else:
            print(f"{table}: exact partitions already match; no remote extras", flush=True)
    return plans


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return _literal(value)
    if type(value) is int:
        return str(value)
    if type(value) is float and math.isfinite(value):
        return repr(value)
    raise ValueError(f"Unsupported factual value {value!r}; nothing written")


def apply_extra_repairs(plans: list[ExtraRepair]) -> None:
    statements = ["-- delete only preflight-proven remote-extra audit rows"]
    for plan in plans:
        for part in sorted(plan.extras):
            for row in plan.extras[part]:
                # Compare-and-delete the entire preflight row. The workflow's
                # concurrency group prevents sanctioned writer races, but a
                # manual D1 edit between read and import must still turn this
                # into a no-op that postverification catches, never a deletion
                # of facts we did not actually inspect.
                where = " AND ".join(
                    f"{column} IS {_sql_literal(row[column])}" for column in plan.columns)
                statements.append(f"DELETE FROM {plan.table} WHERE {where};")
    with tempfile.TemporaryDirectory(prefix="extra-audit-rows-") as td:
        sql_path = Path(td) / "delete_remote_extras.sql"
        sql_path.write_text("\n".join(statements) + "\n", encoding="utf-8")
        retry_wrangler(sql_path, "remote-extra audit row cleanup")


def verify_extra_repairs(plans: list[ExtraRepair]) -> None:
    for plan in plans:
        parts = sorted(plan.source)
        counts = {part: len(rows) for part, rows in plan.source.items()}
        actual = _partition_rows(_remote, plan.table, plan.columns, parts, counts)
        for part, rows in plan.source.items():
            if factual_rows(rows, plan.columns) != factual_rows(actual[part], plan.columns):
                raise RuntimeError(f"Post-cleanup facts differ: {plan.table} {'|'.join(part)}")


def _tokens(raw: str, pattern: str, name: str) -> list[str]:
    values = sorted(set(v.strip().upper() for v in raw.split(",") if v.strip()))
    if not values or any(re.fullmatch(pattern, v) is None or v == "ALL" for v in values):
        raise ValueError(f"Invalid {name}: supply explicit comma-separated values")
    return values


def _parts(raw: str) -> list[Part]:
    parts = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values = token.upper().split(":")
        if len(values) != 3:
            raise ValueError(f"Invalid exact partition: {token!r}")
        part = (values[0], values[1], values[2].lower())
        _part(dict(zip(PART_COLUMNS, part)))
        parts.append(part)
    if not parts or len(parts) != len(set(parts)):
        raise ValueError("Supply unique BANK:YYYYQn:kind exact partitions")
    return sorted(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "bank_audit.db")
    ap.add_argument("--tables", required=True, help="Explicit comma-separated allowlisted audit tables")
    ap.add_argument("--banks", default="", help="Optional explicit tickers; blank selects all")
    ap.add_argument("--periods", default="", help="Optional YYYYQn list; blank selects all")
    ap.add_argument("--kind", choices=["both", "consolidated", "unconsolidated"], default="both")
    ap.add_argument("--partitions", default="",
                    help="Exact BANK:YYYYQn:kind triples (required for remote-extra deletion)")
    ap.add_argument("--remove-remote-extras", action="store_true",
                    help="Delete only D1 rows beyond an identical authoritative multiset")
    ap.add_argument("--apply", action="store_true", help="Actions-only application of proven repair")
    args = ap.parse_args(argv)
    tables = sorted(set(t.strip() for t in args.tables.split(",") if t.strip()))
    if not tables or set(tables) - set(ALLOWED_TABLES):
        ap.error("--tables must name only explicit allowlisted audit tables")
    if args.apply and os.environ.get("GITHUB_ACTIONS") != "true":
        ap.error("Apply through repair-missing-audit-rows.yml, not this machine")
    if not args.db.is_file():
        ap.error("Authoritative audit snapshot does not exist")
    try:
        exact_parts = _parts(args.partitions) if args.partitions.strip() else []
    except ValueError as error:
        ap.error(str(error))
    if args.remove_remote_extras:
        if not exact_parts:
            ap.error("--remove-remote-extras requires --partitions")
        if args.banks.strip() or args.periods.strip() or args.kind != "both":
            ap.error("Remote-extra cleanup is scoped only by --partitions")
        with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            plans = plan_extra_repairs(conn, tables, exact_parts)
        if not plans:
            print("No remote-extra rows — no D1 or snapshot writes")
            return 0
        total = sum(len(rows) for plan in plans for rows in plan.extras.values())
        print(f"Preflight complete: {total} remote-extra rows across "
              f"{sum(len(plan.extras) for plan in plans)} exact table partitions; "
              "all authoritative facts are present")
        if not args.apply:
            print("Dry run — no D1 or snapshot writes")
            return 0
        apply_extra_repairs(plans)
        verify_extra_repairs(plans)
        with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            if plan_extra_repairs(conn, tables, exact_parts):
                raise RuntimeError("Second comparison still finds remote-extra rows")
        print("Verified exact D1 equality and a no-op second comparison; snapshot unchanged")
        return 0
    filters = []
    if args.banks.strip():
        banks = _tokens(args.banks, r"[A-Z0-9]{2,16}", "banks")
        filters.append("bank_ticker IN (" + ",".join(map(_literal, banks)) + ")")
    if args.periods.strip():
        periods = _tokens(args.periods, r"\d{4}Q[1-4]", "periods")
        filters.append("period IN (" + ",".join(map(_literal, periods)) + ")")
    if args.kind != "both":
        filters.append("kind=" + _literal(args.kind))
    if exact_parts:
        filters.append(_part_scope(exact_parts))
    scope = " AND ".join(filters) or "1=1"
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        plans = plan_repairs(conn, tables, scope)
    if not plans:
        print("No missing rows — no D1 or snapshot writes")
        return 0
    print(f"Preflight complete: {sum(p.missing_rows for p in plans)} missing rows across "
          f"{sum(len(p.source) for p in plans)} table partitions; no conflicting facts")
    if not args.apply:
        print("Dry run — no D1 or snapshot writes")
        return 0
    apply_repairs(args.db, plans)
    verify_repairs(plans)
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        if plan_repairs(conn, tables, scope):
            raise RuntimeError("Second comparison still finds missing rows; snapshot was not uploaded")
    push_snapshot(args.db)  # persist the writer's updated partition digests
    print("Verified restored facts and a no-op second comparison; saved snapshot digests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
