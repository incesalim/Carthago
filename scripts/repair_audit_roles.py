"""Restore missing/stale D1 P&L roles without re-extracting any financial row.

Run via repair-audit-roles.yml against a freshly pulled audit snapshot. The
default is read-only: compare the derived role map with D1, then require that
every affected partition's stored P&L agrees with D1 before proposing a write.
Only differing role partitions are replaced; a repeat run writes nothing.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_d1 import _wrangler_json, push_snapshot  # noqa: E402
from src.audit_reports.validator import pl_roles, upsert_pl_roles  # noqa: E402

Part = tuple[str, str, str]


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur]


def _remote(sql: str) -> list[dict]:
    result = _wrangler_json(" ".join(sql.split()), "P&L role repair read")
    if len(result) != 1 or not result[0].get("success"):
        raise RuntimeError("D1 did not return one successful read; refusing repair")
    return result[0]["results"]


def _partition(row: dict) -> Part:
    return row["bank_ticker"], row["period"], row["kind"]


def plan_repairs(source: list[dict], remote_roles: list[dict]) -> dict[Part, list[dict]]:
    """Only role differences; timestamps and unrelated D1 partitions are ignored."""
    grouped: dict[Part, list[dict]] = {}
    actual: dict[Part, dict[str, str]] = {}
    for row in source:
        grouped.setdefault(_partition(row), []).append(row)
    for row in remote_roles:
        actual.setdefault(_partition(row), {})[row["hierarchy"]] = row["role"]
    repairs = {}
    for part, rows in grouped.items():
        wanted = pl_roles(rows)
        if wanted and wanted != actual.get(part, {}):
            repairs[part] = rows
    return repairs


def verify_sources(repairs: dict[Part, list[dict]], remote_source: list[dict]) -> None:
    """Never ship aliases for a different version of the underlying statement."""
    fields = ("item_order", "hierarchy", "item_name", "amount")

    def values(rows: list[dict]) -> list[tuple]:
        return sorted((tuple(r.get(k) for k in fields) for r in rows),
                      key=lambda r: r[0])

    actual: dict[Part, list[dict]] = {}
    for row in remote_source:
        actual.setdefault(_partition(row), []).append(row)
    for part, rows in repairs.items():
        if values(rows) != values(actual.get(part, [])):
            raise ValueError(f"Snapshot/D1 P&L mismatch for {'|'.join(part)}; nothing written")


def _tokens(raw: str, pattern: str, name: str) -> list[str]:
    tokens = sorted(set(s.strip().upper() for s in raw.split(",") if s.strip()))
    if not tokens or any(re.fullmatch(pattern, s) is None for s in tokens):
        raise ValueError(f"Invalid {name}: use an explicit comma-separated list")
    return tokens


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "bank_audit.db")
    ap.add_argument("--banks", required=True, help="Explicit tickers; ALL is not accepted")
    ap.add_argument("--periods", default="", help="YYYYQn list; empty selects all stored quarters")
    ap.add_argument("--kind", choices=["unconsolidated", "consolidated"], default="unconsolidated")
    ap.add_argument("--apply", action="store_true", help="Replace only differing D1 role partitions")
    args = ap.parse_args()
    banks = _tokens(args.banks, r"[A-Z]{2,12}", "banks")
    if "ALL" in banks:
        ap.error("Supply the affected bank tickers explicitly")
    periods = _tokens(args.periods, r"\d{4}Q[1-4]", "periods") if args.periods.strip() else []
    if args.apply and os.environ.get("GITHUB_ACTIONS") != "true":
        ap.error("Apply repairs through repair-audit-roles.yml, not this machine")
    if not args.db.is_file():
        ap.error("Audit snapshot does not exist")
    scope = "bank_ticker IN (" + ",".join(f"'{b}'" for b in banks) + ")"
    scope += f" AND kind='{args.kind}'"
    if periods:
        scope += " AND period IN (" + ",".join(f"'{p}'" for p in periods) + ")"
    source_sql = ("SELECT bank_ticker,period,kind,item_order,hierarchy,item_name,amount "
                  f"FROM bank_audit_profit_loss WHERE {scope} ORDER BY item_order")
    role_sql = f"SELECT bank_ticker,period,kind,hierarchy,role FROM bank_audit_pl_roles WHERE {scope}"
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        source = _rows(conn, source_sql)
        local_repairs = plan_repairs(source, _rows(conn, role_sql))
    if not source:
        raise ValueError("No P&L rows in the snapshot for the selected scope; nothing written")
    repairs = plan_repairs(source, _remote(role_sql))
    if not repairs and not local_repairs:
        print("P&L roles already match D1 — no D1 or snapshot writes")
        return 0
    # Also heal a stale snapshot after a previous D1 success followed by an
    # upload failure. Correct D1 roles alone do not prove both stores agree.
    verify_sources(repairs | local_repairs, _remote(source_sql))
    for part, rows in sorted(repairs.items()):
        print(f"{'|'.join(part)}: restore {len(pl_roles(rows))} roles")
    print(f"{len(repairs)} differing partitions; financial figures remain untouched")
    print(f"{len(local_repairs)} snapshot role maps need rebuilding")
    if not args.apply:
        print("Dry run — no D1 or snapshot writes")
        return 0
    with sqlite3.connect(args.db) as conn:
        for part, rows in local_repairs.items():
            upsert_pl_roles(conn, *part, rows)
    with tempfile.TemporaryDirectory(prefix="audit-role-repair-") as td:
        listing = Path(td) / "partitions.txt"
        listing.write_text("".join("|".join(p) + "\n" for p in sorted(repairs)), encoding="utf-8")
        # Explicit replacement resends these partitions despite old timestamps
        # or matching local digests. The live comparison owns idempotence here:
        # a local digest cannot detect a role map subsequently erased from D1.
        if repairs:
            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "push_to_d1.py"),
                "--db", str(args.db), "--only-tables", "bank_audit_pl_roles",
                "--replace-partitions", str(listing),
            ], check=True)
    if plan_repairs(source, _remote(role_sql)):
        raise RuntimeError("D1 role verification failed; snapshot was not uploaded")
    push_snapshot(args.db)
    print("Verified D1 roles and saved the snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
