"""Read-only serving-schema checks. Only versioned migrations write D1 DDL."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "web" / "migrations"


class SchemaMismatch(ValueError):
    pass


def query_remote(sql: str) -> list[dict]:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ.get("R2_ACCOUNT_ID")
    if not account:
        raise SchemaMismatch("CLOUDFLARE_ACCOUNT_ID or R2_ACCOUNT_ID is required for schema preflight")
    config = (ROOT / "web" / "wrangler.jsonc").read_text(encoding="utf-8")
    database = re.search(r'"database_id"\s*:\s*"([^"]+)"', config)[1]
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query",
        data=json.dumps({"sql": sql}).encode(),
        headers={"Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"],
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = json.load(response)
    if not payload.get("success") or not payload.get("result") or not payload["result"][0].get("success", True):
        raise SchemaMismatch("D1 schema query failed; publication refused")
    return payload["result"][0]["results"]


def migrated_schema() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for path in sorted(MIGRATIONS.glob("*.sql")):
        conn.executescript(path.read_text(encoding="utf-8"))
    return conn


def columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
        raise SchemaMismatch(f"invalid table name: {table}")
    return {r[1]: dict(name=r[1], type=r[2].upper(), notnull=r[3], default=r[4], pk=r[5])
            for r in conn.execute(f"PRAGMA table_info({table})")}


def remote_schema(tables: set[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for row in query_remote("SELECT name,tbl_name,sql FROM sqlite_master "
                            "WHERE type IN ('table','index') ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"):
        if row["tbl_name"] in tables and row["sql"]:
            conn.executescript(row["sql"])
    return conn


def affinity(typ: str) -> str:
    typ = typ.upper()
    if "INT" in typ:
        return "INTEGER"
    if any(t in typ for t in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in typ or not typ:
        return "BLOB"
    if any(t in typ for t in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def unique_keys(conn: sqlite3.Connection, table: str) -> set[tuple]:
    return {(tuple(row[0] for row in conn.execute(
        "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (idx[1],))), idx[4])
        for idx in conn.execute(f"PRAGMA index_list({table})") if idx[2]}


def compare_schema(expected: sqlite3.Connection, actual: sqlite3.Connection,
                   tables: set[str], *, staging: bool = False) -> list[str]:
    errors = []
    for table in sorted(tables):
        want, have = columns(expected, table), columns(actual, table)
        if not want:
            errors.append(f"{table}: absent from versioned migrations")
            continue
        if not have:
            errors.append(f"{table}: missing table")
            continue
        if unique_keys(expected, table) != unique_keys(actual, table):
            errors.append(f"{table}: incompatible unique/natural keys")
        for name, column in want.items():
            if staging and name not in have and column["notnull"] and column["default"] is None:
                errors.append(f"{table}.{name}: required serving column absent from staging")
        # A staging DB may omit D1-only metadata, but every emitted column must
        # exist remotely. Serving preflight requires every migration column.
        for name in (have if staging else want):
            if name not in want or name not in have:
                errors.append(f"{table}.{name}: missing column")
                continue
            a, b = want[name], have[name]
            # Historical SQLite timestamp columns use TEXT/TIMESTAMP interchangeably.
            # Both store ISO strings; limit this allowance to the two stamp fields.
            timestamp_alias = (name in {"extracted_at", "downloaded_at"}
                               and {a["type"], b["type"]} <= {"TEXT", "TIMESTAMP"})
            if (affinity(a["type"]) != affinity(b["type"]) and not timestamp_alias) or a["pk"] != b["pk"]:
                errors.append(f"{table}.{name}: incompatible type/key")
            if (not staging and a["notnull"] != b["notnull"]) or (staging and a["notnull"] and not b["notnull"]):
                errors.append(f"{table}.{name}: incompatible nullability")
        # Defaults may differ in historical snapshots: publishers name every
        # emitted column. Default equality is enforced separately when adopting
        # a migration, where it is part of that migration's complete effect.
    return errors


def assert_remote_schema(tables: set[str]) -> None:
    expected, actual = migrated_schema(), remote_schema(tables)
    try:
        errors = compare_schema(expected, actual, tables)
        if errors:
            raise SchemaMismatch("Schema mismatch; apply versioned migrations before publishing: " + "; ".join(errors))
    finally:
        expected.close()
        actual.close()


def assert_staging_schema(db: Path, tables: set[str]) -> None:
    """Reject local columns that the SQL emitter would send outside the contract."""
    expected = migrated_schema()
    actual = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        present = {r[0] for r in actual.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        errors = compare_schema(expected, actual, tables & present, staging=True)
        if errors:
            raise SchemaMismatch("Staging schema mismatch: " + "; ".join(errors))
    finally:
        expected.close()
        actual.close()
