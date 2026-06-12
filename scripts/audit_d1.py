"""Shared D1 + R2-snapshot operations for the audit lane.

Every audit repair/sync tool does the same dance: pull the snapshot, mutate the
local ``bank_audit.db``, clear the touched partitions in D1, push (upsert-only),
re-upload the snapshot — guarded against concurrent CI writers and D1 transients.
This module is the one place that logic lives, so the satellites
(``backfill_extraction``, ``audit_correct``, ``push_from_scratch``,
``backfills/backfill_npl_history``) share it instead of re-implementing it.

Lives at the scripts layer (not ``src/``) because it composes ``run_wrangler``
from ``scripts/push_to_d1.py`` — ``src/`` never imports ``scripts/``.

Requires R2_* + CLOUDFLARE_API_TOKEN env vars for the D1/R2 calls.
"""
from __future__ import annotations

import gzip
import json as _json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import r2_storage  # noqa: E402
from scripts.push_to_d1 import run_wrangler  # noqa: E402

# --- audit-lane constants -------------------------------------------------
DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"
AUDIT_TABLES = [
    "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_oci",
    "bank_audit_cash_flow", "bank_audit_equity_change",
    "bank_audit_credit_quality",
    "bank_audit_profile", "bank_audit_loans_by_sector", "bank_audit_npl_movement",
    "bank_audit_stages", "bank_audit_capital", "bank_audit_liquidity",
    "bank_audit_validation", "bank_audit_extractions",
]
# Window passed to push_to_d1; the D1 partition-clear derives the same
# (bank, period) set the push will re-insert, so keep these two in lock-step.
PUSH_WINDOW_HOURS = 24

# D1 occasionally drops a remote execute with a service-side transient
# ("D1_RESET_DO" / "import polling failed" / fetch failed) — seen during a
# Phase-3 batch run right after a heavy partition clear. Imports are
# transactional, so retrying is safe; without it a transient strands a batch
# with cleared-but-unpushed partitions.
D1_RETRIES = 3
D1_RETRY_WAIT_S = 90


# --- CI guard + wrangler retry --------------------------------------------
def guard_against_ci_writers() -> None:
    """Abort if a CI audit workflow is queued/running. The R2 snapshot is
    last-writer-wins and the bddk-audit concurrency group does NOT serialize
    against local runs — a CI chunk backfill clobbered the 2026-06-10
    ALBRK/BURGAN repair exactly this way. Requires gh CLI; degrades to a
    warning when gh is unavailable."""
    busy = []
    for wf in ("backfill-audit.yml", "refresh-audit.yml"):
        for status in ("in_progress", "queued"):
            try:
                out = subprocess.run(
                    ["gh", "run", "list", "--workflow", wf, "--status", status,
                     "--json", "databaseId", "--limit", "1"],
                    capture_output=True, text=True, timeout=30)
                if out.returncode == 0 and _json.loads(out.stdout or "[]"):
                    busy.append(f"{wf} ({status})")
            except Exception as e:  # noqa: BLE001
                print(f"[d1] WARNING: cannot check CI writers ({e}) — "
                      "make sure no audit workflow is running", flush=True)
                return
    if busy:
        sys.exit("[d1] ABORT: CI audit workflow(s) active — "
                 + ", ".join(busy)
                 + ". A concurrent run would clobber the R2 snapshot "
                 "(last-writer-wins). Re-run when CI is idle.")


def retry_wrangler(sql_path: Path, what: str) -> None:
    for attempt in range(1, D1_RETRIES + 1):
        if run_wrangler(sql_path) == 0:
            return
        if attempt < D1_RETRIES:
            print(f"[d1] {what} failed (attempt {attempt}/{D1_RETRIES}) — "
                  f"retrying in {D1_RETRY_WAIT_S}s", flush=True)
            time.sleep(D1_RETRY_WAIT_S)
    sys.exit(f"[d1] {what} failed after {D1_RETRIES} attempts")


# --- D1 schema + partition clear ------------------------------------------
def partition_delete_sql(parts: list[tuple[str, str, str]],
                         tables: list[str] = AUDIT_TABLES) -> str:
    """DELETE statements for every (bank, period, kind) across the given tables —
    run against D1 before the upsert-only push so stale rows from a bigger old
    extraction don't survive as orphans. Kind-scoped so a skipped kind keeps its
    D1 rows while its sibling kind is repaired."""
    stmts = []
    for tbl in tables:
        for bank, period, kind in parts:
            if any("'" in s for s in (bank, period, kind)):  # alnum; guard anyway
                raise ValueError(f"unexpected quote in partition {bank!r} {period!r} {kind!r}")
            stmts.append(f"DELETE FROM {tbl} WHERE bank_ticker='{bank}' "
                         f"AND period='{period}' AND kind='{kind}';")
    return "\n".join(stmts) + "\n"


def ensure_d1_schema() -> None:
    """Create any missing bank_audit_* tables in remote D1 before clear/push.
    push_to_d1 only emits INSERT OR REPLACE — never CREATE — so a newly-added
    table won't exist in D1 and the partition-clear's `DELETE FROM <missing>`
    would error mid-batch (partial delete, no re-push = data loss). The schema
    DDL is all CREATE ... IF NOT EXISTS, so applying it here is idempotent."""
    from src.audit_reports.schema import DDL
    sql_path = Path(tempfile.gettempdir()) / "d1_audit_schema.sql"
    sql_path.write_text(DDL, encoding="utf-8")
    print("[d1] ensuring bank_audit_* schema exists in D1")
    retry_wrangler(sql_path, "D1 schema ensure")


def clear_d1_partitions(db_path: Path, window_hours: int,
                        tables: list[str] = AUDIT_TABLES) -> None:
    """Clear the just-re-extracted partitions in remote D1 so the subsequent push
    lands in clean partitions. The (bank, period, kind) set is derived from the
    fresh bank_audit_extractions rows — the same set push_to_d1 re-inserts within
    the same window."""
    with sqlite3.connect(str(db_path)) as conn:
        parts = conn.execute(
            "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_extractions "
            f"WHERE extracted_at >= datetime('now', '-{window_hours} hours')"
        ).fetchall()
    if not parts:
        print("[d1] no freshly-extracted partitions to clear in D1")
        return
    sql_path = Path(tempfile.gettempdir()) / "d1_partition_deletes.sql"
    sql_path.write_text(partition_delete_sql(parts, tables), encoding="utf-8")
    print(f"[d1] clearing {len(parts)} partitions × {len(tables)} tables in D1")
    retry_wrangler(sql_path, "D1 partition delete")


# --- snapshot pull / push (the bookends of every repair) ------------------
def pull_snapshot(guard: bool = True) -> Path:
    """Download + decompress state/bank_audit.db.gz → data/bank_audit.db.
    When guard, abort if a CI audit workflow is active (snapshot clobber)."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    if guard:
        guard_against_ci_writers()
    if not r2_storage.exists(SNAP):
        sys.exit(f"[d1] no snapshot at R2 {SNAP}")
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[d1] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")
    return DB


def push_snapshot(db_path: Path = DB) -> None:
    """VACUUM + gzip the local DB and upload it to R2 (with a dated backup)."""
    with sqlite3.connect(str(db_path)) as c:
        c.execute("VACUUM")
    with open(db_path, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[d1] uploaded snapshot ({size / 1e6:.1f} MB) → R2 {SNAP}")


def push_to_d1(db_path: Path = DB, window_hours: int = PUSH_WINDOW_HOURS,
               tables: list[str] = AUDIT_TABLES) -> None:
    """Run scripts/push_to_d1.py for the audit tables within the window, with the
    same retry/backoff as the D1 schema/clear calls."""
    cmd = [sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
           "--db", str(db_path), "--hours", str(window_hours),
           "--only-tables", ",".join(tables)]
    for attempt in range(1, D1_RETRIES + 1):
        if subprocess.run(cmd).returncode == 0:
            return
        if attempt == D1_RETRIES:
            sys.exit(f"[d1] push failed after {D1_RETRIES} attempts — partitions "
                     "may be cleared but unpushed; re-run for the same banks to recover")
        print(f"[d1] push failed (attempt {attempt}/{D1_RETRIES}) — "
              f"retrying in {D1_RETRY_WAIT_S}s", flush=True)
        time.sleep(D1_RETRY_WAIT_S)


def push_partitions(parts: list[tuple[str, str, str]], db_path: Path = DB,
                    window_hours: int = 1, tables: list[str] = AUDIT_TABLES) -> None:
    """Ensure schema, clear the explicit (bank, period, kind) partitions, then push
    the fresh rows within the window. Used by the targeted manual-correction tools
    (overlay-statement / override-cells / reextract-pl), which touch a known set of
    partitions rather than deriving them from the extracted_at window."""
    ensure_d1_schema()
    sql_path = Path(tempfile.gettempdir()) / "d1_targeted_deletes.sql"
    sql_path.write_text(partition_delete_sql(parts, tables), encoding="utf-8")
    print(f"[d1] clearing {len(parts)} partition(s) × {len(tables)} tables in D1")
    retry_wrangler(sql_path, "D1 targeted partition delete")
    push_to_d1(db_path, window_hours, tables)


# --- backward-compat aliases (old underscore names; importers migrating) --
_guard_against_ci_writers = guard_against_ci_writers
_retry_wrangler = retry_wrangler
_partition_delete_sql = partition_delete_sql
_ensure_d1_schema = ensure_d1_schema
_clear_d1_partitions = clear_d1_partitions
