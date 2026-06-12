"""Backfill the FULL Stage-3 / NPL history for the banks fixed by the FC-only
extractor patch (see PROJECT_STATE → "Stage-3 NPL understated by FC-only
sub-table").

`backfill_extraction.py --banks ALL --latest-period` already corrected 2026Q1.
This corrects the historical interim quarters too, so the /cross-bank Over-time
view has no fake cliff. The affected banks' interim quarters all read the
foreign-currency-only NPL sub-table; re-extracting with the fixed parser pulls
the total III/IV/V classification instead. (Year-end quarters that used the
inline `loans_amounts` row re-extract identically — idempotent.)

Why this isn't just `backfill_extraction.py --banks <list>`: a single
upsert push of N banks × all periods is hundreds of thousands of rows, past
D1's per-`execute` limit, and the clear-then-push isn't atomic — an oversized
push that fails would leave cleared-but-empty partitions. So we re-extract
everything locally ONCE, then push PER PERIOD (each ≈ the proven weekly
latest-period size), each chunk self-contained (DELETE + INSERT OR REPLACE for
that period's partitions in one file).

Requires R2_* and CLOUDFLARE_API_TOKEN env vars.

  python scripts/backfill_npl_history.py            # all affected banks, all periods
  python scripts/backfill_npl_history.py --dry-run  # re-extract locally; skip D1 + upload
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.push_to_d1 import run_wrangler  # noqa: E402
from scripts.sync_audit_reports import extract_from_r2  # noqa: E402
from scripts.audit_d1 import AUDIT_TABLES, DB, GZ, SNAP  # noqa: E402

# Banks whose templates grabbed the FC-only NPL sub-table (the set that changed
# in the 2026Q1 latest-period backfill). Their full history needs re-extraction.
AFFECTED_BANKS = [
    "AKBNK", "AKTIF", "DENIZ", "FIBA", "ICBCT", "ISCTR",
    "KUVEYT", "ODEA", "TEB", "YKBNK", "ZIRAAT",
]
BATCH = 100  # rows per INSERT OR REPLACE statement (audit rows are skinny)


def _esc(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    # Audit text columns (heading_snippet, item_name) are short single-line
    # snippets — simple quote-doubling is sufficient (no embedded newlines).
    return "'" + str(v).replace("'", "''") + "'"


def _period_chunk_sql(conn: sqlite3.Connection, banks: list[str], period: str) -> str:
    """DELETE + INSERT OR REPLACE for one period's partitions across all audit
    tables, scoped to `banks`. Self-contained so each wrangler execute is
    independent and bounded."""
    bank_list = ",".join("'" + b + "'" for b in banks)
    parts: list[str] = [f"-- {period}: {len(banks)} banks"]
    for tbl in AUDIT_TABLES:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})")]
        col_list = ",".join(cols)
        parts.append(
            f"DELETE FROM {tbl} WHERE bank_ticker IN ({bank_list}) AND period='{period}';"
        )
        rows = conn.execute(
            f"SELECT {col_list} FROM {tbl} "
            f"WHERE bank_ticker IN ({bank_list}) AND period=?",
            (period,),
        ).fetchall()
        for i in range(0, len(rows), BATCH):
            values = ",\n".join(
                "(" + ",".join(_esc(v) for v in r) + ")" for r in rows[i:i + BATCH]
            )
            parts.append(f"INSERT OR REPLACE INTO {tbl}({col_list}) VALUES\n{values};")
    return "\n".join(parts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", default=",".join(AFFECTED_BANKS),
                    help="comma-separated tickers (default: the FC-only-affected set)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="re-extract locally + rebuild stages; skip D1 push + snapshot upload")
    args = ap.parse_args()
    banks = [b.strip().upper() for b in args.banks.split(",") if b.strip()]
    print(f"[npl-history] banks: {banks}")

    DB.parent.mkdir(parents=True, exist_ok=True)
    if not r2_storage.exists(SNAP):
        sys.exit(f"no snapshot at R2 {SNAP}")
    r2_storage.download_to(SNAP, GZ)
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[npl-history] pulled snapshot → {DB.stat().st_size / 1e6:.1f} MB")

    # Force re-extraction of every period for these banks.
    ph = ",".join("?" * len(banks))
    with sqlite3.connect(str(DB)) as conn:
        before = conn.execute(
            f"SELECT COUNT(*) FROM bank_audit_extractions WHERE bank_ticker IN ({ph})",
            tuple(banks)).fetchone()[0]
        conn.execute(
            f"DELETE FROM bank_audit_extractions WHERE bank_ticker IN ({ph})", tuple(banks))
        conn.commit()
    print(f"[npl-history] cleared {before} extraction records → re-extracting all periods")

    counts = extract_from_r2(workers=args.workers, db_path=DB, only=set(banks))
    print(f"[npl-history] re-extract: {counts}")

    subprocess.run([sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
                    "--db", str(DB)], check=True)

    # Periods to push (oldest first), derived from the freshly-extracted log.
    with sqlite3.connect(str(DB)) as conn:
        periods = [r[0] for r in conn.execute(
            f"SELECT DISTINCT period FROM bank_audit_extractions "
            f"WHERE bank_ticker IN ({ph}) ORDER BY period", tuple(banks))]
    print(f"[npl-history] {len(periods)} periods to push: {periods}")

    sql_path = Path(tempfile.gettempdir()) / "d1_npl_history_chunk.sql"
    with sqlite3.connect(str(DB)) as conn:
        for i, period in enumerate(periods, 1):
            sql_path.write_text(_period_chunk_sql(conn, banks, period), encoding="utf-8")
            mb = sql_path.stat().st_size / 1e6
            verb = "would push" if args.dry_run else "push"
            print(f"[npl-history] {verb} {i}/{len(periods)} {period} ({mb:.1f} MB)", flush=True)
            if args.dry_run:
                continue
            rc = run_wrangler(sql_path)
            if rc != 0:
                sys.exit(f"[npl-history] D1 push failed for {period} (rc={rc})")

    if args.dry_run:
        print("[npl-history] dry-run: skipped D1 push + snapshot upload")
        return

    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[npl-history] uploaded snapshot ({size / 1e6:.1f} MB) → R2 {SNAP}")
    print("[npl-history] done")


if __name__ == "__main__":
    main()
