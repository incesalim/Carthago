"""Re-extract specific banks from the R2 PDFs and backfill D1 + the snapshot.

Used after an extractor fix to correct already-ingested banks (the cron skips
PDFs already extracted with success=1, so it won't self-heal). It:

  1. pulls state/bank_audit.db.gz from R2 → data/bank_audit.db
  2. deletes the named banks' bank_audit_extractions rows (forces re-extract)
  3. re-extracts those banks from their R2 PDFs with the current extractor
  4. rebuilds bank_audit_stages
  5. clears the re-extracted (bank, period) partitions in D1, then pushes the
     fresh rows. The push (push_to_d1) is INSERT OR REPLACE — upsert-only, never
     DELETEs — so without this clear an old, larger extraction would leave
     orphan rows at item_orders the fresh extract no longer produces.
  6. re-uploads the snapshot (with a dated history backup)

Requires R2_* and CLOUDFLARE_API_TOKEN env vars.

  python scripts/backfill_extraction.py --banks EXIM,ZIRAAT
  python scripts/backfill_extraction.py --banks EXIM --dry-run
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.push_to_d1 import run_wrangler  # noqa: E402
from scripts.sync_audit_reports import extract_from_r2  # noqa: E402

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"
AUDIT_TABLES = [
    "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_credit_quality",
    "bank_audit_profile", "bank_audit_loans_by_sector", "bank_audit_npl_movement",
    "bank_audit_stages", "bank_audit_capital", "bank_audit_liquidity",
    "bank_audit_validation", "bank_audit_extractions",
]
# Window passed to push_to_d1; the D1 partition-clear below derives the same
# (bank, period) set the push will re-insert, so keep these two in lock-step.
PUSH_WINDOW_HOURS = 24

# D1 occasionally drops a remote execute with a service-side transient
# ("D1_RESET_DO" / "import polling failed" / fetch failed) — seen during the
# Phase-3 batch run right after a heavy partition clear. Imports are
# transactional, so retrying is safe; without it a transient strands a batch
# with cleared-but-unpushed partitions.
D1_RETRIES = 3
D1_RETRY_WAIT_S = 90


def _guard_against_ci_writers() -> None:
    """Abort if a CI audit workflow is queued/running. The R2 snapshot is
    last-writer-wins and the bddk-audit concurrency group does NOT serialize
    against local runs — a CI chunk backfill clobbered the 2026-06-10
    ALBRK/BURGAN repair exactly this way. Requires gh CLI; degrades to a
    warning when gh is unavailable."""
    import json as _json
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
                print(f"[backfill] WARNING: cannot check CI writers ({e}) — "
                      "make sure no audit workflow is running", flush=True)
                return
    if busy:
        sys.exit("[backfill] ABORT: CI audit workflow(s) active — "
                 + ", ".join(busy)
                 + ". A concurrent run would clobber the R2 snapshot "
                 "(last-writer-wins). Re-run when CI is idle.")


def _retry_wrangler(sql_path: Path, what: str) -> None:
    for attempt in range(1, D1_RETRIES + 1):
        if run_wrangler(sql_path) == 0:
            return
        if attempt < D1_RETRIES:
            print(f"[backfill] {what} failed (attempt {attempt}/{D1_RETRIES}) — "
                  f"retrying in {D1_RETRY_WAIT_S}s", flush=True)
            time.sleep(D1_RETRY_WAIT_S)
    sys.exit(f"[backfill] {what} failed after {D1_RETRIES} attempts")


def _partition_delete_sql(parts: list[tuple[str, str]]) -> str:
    """DELETE statements for every re-extracted (bank, period, kind) across all
    audit tables — run against D1 before the upsert-only push so stale rows from
    a bigger old extraction don't survive as orphans. Kind-scoped so a skipped
    kind (e.g. an unextractable no-text-layer PDF protected via --skip) keeps
    its D1 rows while its sibling kind is repaired."""
    stmts = []
    for tbl in AUDIT_TABLES:
        for bank, period, kind in parts:
            if any("'" in s for s in (bank, period, kind)):  # alnum; guard anyway
                raise ValueError(f"unexpected quote in partition {bank!r} {period!r} {kind!r}")
            stmts.append(f"DELETE FROM {tbl} WHERE bank_ticker='{bank}' "
                         f"AND period='{period}' AND kind='{kind}';")
    return "\n".join(stmts) + "\n"


def _ensure_d1_schema() -> None:
    """Create any missing bank_audit_* tables in remote D1 before the clear/push.

    push_to_d1 only emits INSERT OR REPLACE — it never CREATEs — so a newly-added
    table (e.g. bank_audit_capital / bank_audit_liquidity) won't exist in D1, and
    the partition-clear's `DELETE FROM <missing>` would error mid-batch, risking a
    partial delete with no re-push (data loss). The schema DDL is all
    CREATE TABLE/INDEX IF NOT EXISTS, so applying it here is idempotent and makes
    the backfill self-healing for D1 schema."""
    from src.audit_reports.schema import DDL
    sql_path = Path(tempfile.gettempdir()) / "d1_audit_schema.sql"
    sql_path.write_text(DDL, encoding="utf-8")
    print("[backfill] ensuring bank_audit_* schema exists in D1")
    _retry_wrangler(sql_path, "D1 schema ensure")


def _clear_d1_partitions(db_path: Path, window_hours: int) -> None:
    """Clear the just-re-extracted partitions in remote D1 so the subsequent
    push lands in clean partitions (no orphan rows). The (bank, period, kind)
    set is derived from the fresh bank_audit_extractions rows — the same set
    push_to_d1 re-inserts within the same window."""
    with sqlite3.connect(str(db_path)) as conn:
        parts = conn.execute(
            "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_extractions "
            f"WHERE extracted_at >= datetime('now', '-{window_hours} hours')"
        ).fetchall()
    if not parts:
        print("[backfill] no freshly-extracted partitions to clear in D1")
        return
    sql_path = Path(tempfile.gettempdir()) / "d1_backfill_deletes.sql"
    sql_path.write_text(_partition_delete_sql(parts), encoding="utf-8")
    print(f"[backfill] clearing {len(parts)} partitions × {len(AUDIT_TABLES)} tables in D1")
    _retry_wrangler(sql_path, "D1 partition delete")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", required=True,
                    help="comma-separated tickers, or ALL for every bank in the config")
    ap.add_argument("--latest-period", action="store_true",
                    help="only re-extract each bank's most recent period (fast, bounded)")
    ap.add_argument("--dry-run", action="store_true", help="re-extract locally; skip D1 push + snapshot upload")
    ap.add_argument("--skip", type=str, default="",
                    help="comma-separated BANK:PERIOD:KIND triples to leave untouched "
                         "(not re-extracted, not cleared in D1 — e.g. an unextractable "
                         "no-text-layer PDF whose old rows must survive: "
                         "ISCTR:2025Q1:consolidated)")
    ap.add_argument("--window-hours", type=int, default=PUSH_WINDOW_HOURS,
                    help="freshness window for the D1 clear+push set (smaller for "
                         "batched runs so batches don't re-push each other)")
    args = ap.parse_args()
    if args.banks.strip().upper() == "ALL":
        cfg = json.loads((REPO / "data" / "banks" / "audit_report_urls.json").read_text(encoding="utf-8"))
        banks = {t.upper() for t in cfg["banks"]}
    else:
        banks = {b.strip().upper() for b in args.banks.split(",") if b.strip()}
    print(f"[backfill] banks: {len(banks)}{' (latest period only)' if args.latest_period else ''}")

    DB.parent.mkdir(parents=True, exist_ok=True)
    if not args.dry_run and os.environ.get("GITHUB_ACTIONS") != "true":
        _guard_against_ci_writers()
    if not r2_storage.exists(SNAP):
        sys.exit(f"no snapshot at R2 {SNAP}")
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[backfill] pulled snapshot → {DB.stat().st_size/1e6:.1f} MB")

    skips = [tuple(s.strip().split(":")) for s in args.skip.split(",") if s.strip()]
    if any(len(t) != 3 for t in skips):
        sys.exit(f"--skip entries must be BANK:PERIOD:KIND, got {args.skip!r}")

    # Force re-extraction by clearing the extraction log. With --latest-period
    # only the newest period per bank is cleared (and re-extracted). --skip
    # triples keep their success=1 log row, so extract_from_r2 leaves them
    # alone and their local + D1 rows survive untouched.
    ph = ",".join("?" * len(banks))
    with sqlite3.connect(str(DB)) as conn:
        where = f"bank_ticker IN ({ph})"
        params: tuple = tuple(banks)
        if args.latest_period:
            where += (" AND (bank_ticker, period) IN (SELECT bank_ticker, MAX(period) "
                      f"FROM bank_audit_extractions WHERE bank_ticker IN ({ph}) GROUP BY bank_ticker)")
            params = tuple(banks) * 2
        for bank, period, kind in skips:
            where += " AND NOT (bank_ticker=? AND period=? AND kind=?)"
            params += (bank.upper(), period.upper(), kind.lower())
        before = conn.execute(
            f"SELECT COUNT(*) FROM bank_audit_extractions WHERE {where}", params).fetchone()[0]
        conn.execute(f"DELETE FROM bank_audit_extractions WHERE {where}", params)
        conn.commit()
    print(f"[backfill] cleared {before} extraction records → will re-extract"
          + (f" (skipping {len(skips)})" if skips else ""))

    counts = extract_from_r2(workers=8, db_path=DB, only=banks, latest_period=args.latest_period)
    print(f"[backfill] re-extract: {counts}")

    subprocess.run([sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
                    "--db", str(DB)], check=True)

    if args.dry_run:
        print("[backfill] dry-run: skipping D1 clear + push + snapshot upload")
        return

    _ensure_d1_schema()   # create any missing bank_audit_* tables before clear/push
    _clear_d1_partitions(DB, args.window_hours)

    push_cmd = [sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                "--db", str(DB), "--hours", str(args.window_hours),
                "--only-tables", ",".join(AUDIT_TABLES)]
    for attempt in range(1, D1_RETRIES + 1):
        if subprocess.run(push_cmd).returncode == 0:
            break
        if attempt == D1_RETRIES:
            sys.exit(f"[backfill] D1 push failed after {D1_RETRIES} attempts "
                     "— partitions are cleared but unpushed; re-run this backfill "
                     "for the same banks to recover")
        print(f"[backfill] D1 push failed (attempt {attempt}/{D1_RETRIES}) — "
              f"retrying in {D1_RETRY_WAIT_S}s", flush=True)
        time.sleep(D1_RETRY_WAIT_S)

    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[backfill] uploaded snapshot ({size/1e6:.1f} MB) → R2 {SNAP}")
    print("[backfill] done")


if __name__ == "__main__":
    main()
