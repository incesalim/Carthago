#!/usr/bin/env python3
"""Remove a (bank, period[, kind]) partition from the audit lane — everywhere.

Why this exists: an extraction can succeed, validate green, and still be wrong —
TEB's 2026Q2 filing switched its reporting unit from thousands to millions of TL,
so every figure landed 1000x too small while every INTERNAL identity still footed
(uniform scaling cancels on both sides of assets=liabilities). Until the extractor
learns to normalise the unit, the honest state for such a partition is *absent*:
the coverage cell reads `missing`, consumers fall back to the bank's prior
quarter, and nothing published is silently wrong.

Deleting from D1 alone is NOT enough and is the trap this script exists to avoid:
the R2 snapshot would keep the bad rows, and the next `push_to_d1` from any later
extraction run would put them straight back. So the order is fixed, and mirrors
the rest of the lane:

    pull snapshot -> delete locally -> delete in D1 -> re-upload snapshot

`--dry-run` here is genuinely read-only: it pulls the snapshot (a download changes
nothing) and prints the row counts it would remove, then exits before any D1
delete or snapshot upload. (Unlike apply_overrides.py, whose --dry-run is not.)
Re-running is safe: a purged partition simply reports 0.

Re-extracting afterwards restores the partition — this removes data, never PDFs.
The R2 PDF stays put, so the coverage cell shows `missing` WITH `pdf_present`,
which is exactly "acquired, awaiting extraction".
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.audit_d1 import (  # noqa: E402
    DB, partition_delete_sql, pull_snapshot, push_snapshot, retry_wrangler,
)
from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402

KINDS = ("consolidated", "unconsolidated")


def count_rows(conn: sqlite3.Connection, parts: list[tuple[str, str, str]],
               ) -> dict[str, int]:
    """{table: rows matching any of the partitions} — the read-only preview."""
    out: dict[str, int] = {}
    for tbl in AUDIT_TABLES:
        total = 0
        for bank, period, kind in parts:
            try:
                (n,) = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE bank_ticker = ? "
                    "AND period = ? AND kind = ?", (bank, period, kind)).fetchone()
            except sqlite3.OperationalError:
                # A snapshot predating a newly-registered table: nothing to purge.
                continue
            total += n
        if total:
            out[tbl] = total
    return out


def delete_local(conn: sqlite3.Connection,
                 parts: list[tuple[str, str, str]]) -> int:
    deleted = 0
    for tbl in AUDIT_TABLES:
        for bank, period, kind in parts:
            try:
                cur = conn.execute(
                    f"DELETE FROM {tbl} WHERE bank_ticker = ? AND period = ? "
                    "AND kind = ?", (bank, period, kind))
            except sqlite3.OperationalError:
                continue
            deleted += cur.rowcount
    conn.commit()
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", required=True, help="ticker, e.g. TEB")
    ap.add_argument("--period", required=True, help="quarter, e.g. 2026Q2")
    ap.add_argument("--kind", choices=KINDS, default=None,
                    help="restrict to one basis; default = both")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be removed and exit — READ-ONLY, "
                         "touches neither D1 nor the snapshot")
    ap.add_argument("--no-pull", action="store_true",
                    help="use the existing local data/bank_audit.db (tests/debug)")
    args = ap.parse_args()

    bank, period = args.bank.strip().upper(), args.period.strip().upper()
    kinds = [args.kind] if args.kind else list(KINDS)
    parts = [(bank, period, k) for k in kinds]

    # A dry run still PULLS: downloading the snapshot mutates nothing remote, and
    # on a fresh CI runner there is no local DB to inspect otherwise — refusing to
    # pull made --dry-run useless exactly where it is dispatched from. What
    # "read-only" promises is the other end: no D1 delete, no snapshot upload.
    # --no-pull is the escape hatch for a local run with a DB you want kept.
    if not args.no_pull:
        pull_snapshot(guard=True)
    if not DB.exists():
        return print(f"[purge] no local {DB} and --no-pull given — nothing to "
                     "inspect") or 1

    conn = sqlite3.connect(str(DB))
    counts = count_rows(conn, parts)
    total = sum(counts.values())
    label = f"{bank} {period} [{', '.join(kinds)}]"

    if not total:
        print(f"[purge] {label}: nothing stored — already absent")
        conn.close()
        return 0

    print(f"[purge] {label} — {total} row(s) across {len(counts)} table(s):")
    for tbl, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"          {n:>6}  {tbl}")

    if args.dry_run:
        print("[purge] dry-run — nothing written (D1, snapshot and R2 untouched)")
        conn.close()
        return 0

    deleted = delete_local(conn, parts)
    conn.close()
    print(f"[purge] deleted {deleted} row(s) from the local snapshot")

    sql_path = Path(tempfile.gettempdir()) / "d1_purge_partition.sql"
    sql_path.write_text(partition_delete_sql(parts), encoding="utf-8")
    retry_wrangler(sql_path, f"D1 purge {label}")
    print(f"[purge] cleared {label} in D1 across {len(AUDIT_TABLES)} tables")

    push_snapshot(DB)
    print("[purge] snapshot re-uploaded — the partition will NOT come back on the "
          "next push. Re-extract to restore it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
