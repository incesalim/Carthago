"""Adopt only reviewed additive migrations whose complete effects already exist.

Default is a read-only plan. --apply is restricted to Actions and executes the
missing reviewed ALTERs plus ledger records in one D1 file import. No figures
are updated, defaults removed, or duplicate-column errors swallowed.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipeline.schema import (  # noqa: E402
    MIGRATIONS, SchemaMismatch, columns, migrated_schema, query_remote, remote_schema,
)

# Exact effects, never a generic permission to adopt any ALTER in the repository.
ADOPTIONS = {
    "0045_capital_deductions.sql": [("bank_audit_capital", "capital_deductions", "REAL")],
    "0046_npl_accrual_movement.sql": [("bank_audit_npl_movement", "accrual_movement", "REAL")],
    "0047_audit_extraction_counters.sql": [
        ("bank_audit_extractions", "rows_fx_position", "INTEGER"),
        ("bank_audit_extractions", "rows_repricing", "INTEGER"),
    ],
}


def adoption_plan(actual: sqlite3.Connection, applied: set[str]) -> list[str]:
    expected = migrated_schema()
    planned = []
    known = set(applied)
    try:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name not in ADOPTIONS:
                if path.name not in known:
                    # Fresh/incomplete installs go through Wrangler in order.
                    break
                continue
            effects = ADOPTIONS[path.name]
            statements = [f"ALTER TABLE {table} ADD COLUMN {name} {typ};" for table, name, typ in effects]
            authored = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
            if " ".join(authored.split()) != " ".join(" ".join(statements).split()):
                raise SchemaMismatch(f"{path.name}: effects changed; review the adoption allowlist")
            missing = []
            for (table, name, _), statement in zip(effects, statements):
                want, have = columns(expected, table)[name], columns(actual, table)
                if not have:
                    raise SchemaMismatch(f"{path.name}: required table {table} is absent")
                if name in have and have[name] != want:
                    raise SchemaMismatch(f"{table}.{name}: existing definition differs from migration")
                if name not in have:
                    if path.name in applied:
                        raise SchemaMismatch(f"{path.name}: recorded as applied but {name} is absent")
                    missing.append(statement)
            if path.name not in applied:
                planned.extend(missing)
                planned.append(f"INSERT INTO d1_migrations(name) VALUES ('{path.name}');")
                known.add(path.name)
        return planned
    finally:
        expected.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply and os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Schema publication runs in GitHub Actions; omit --apply for a read-only plan")
    names = {r["name"] for r in query_remote("SELECT name FROM sqlite_master WHERE type='table'")}
    if "d1_migrations" not in names:
        print("Fresh database: Wrangler will apply the complete migration chain")
        return
    applied = {r["name"] for r in query_remote("SELECT name FROM d1_migrations")}
    tables = {t for effects in ADOPTIONS.values() for t, _, _ in effects}
    actual = remote_schema(tables)
    try:
        plan = adoption_plan(actual, applied)
    finally:
        actual.close()
    print("\n".join(plan) if plan else "Schema adoption already complete")
    if not args.apply or not plan:
        return
    with tempfile.TemporaryDirectory(prefix="carthago-schema-") as directory:
        path = Path(directory) / "adoption.sql"
        path.write_text("\n".join(plan), encoding="utf-8")
        subprocess.run(["npx", "--yes", "wrangler", "d1", "execute", "bddk-data", "--remote", f"--file={path}"],
                       cwd=ROOT / "web", shell=os.name == "nt", check=True)
    # Lost responses are not retried blindly. A repeat first checks the ledger.
    actual = remote_schema(tables)
    try:
        remaining = adoption_plan(actual, {r["name"] for r in query_remote("SELECT name FROM d1_migrations")})
        if remaining:
            raise SchemaMismatch("Adoption did not persist its complete schema/ledger effects")
    finally:
        actual.close()


if __name__ == "__main__":
    main()
