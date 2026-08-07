"""Backfill lossless source evidence without re-extracting normalized tables.

This is intentionally an Actions-scale job: it downloads existing audit PDFs
from R2, captures only the eight completeness-targeted disclosures, merges the
new source checks into stored validation, and writes no analytical fact table.
Raw lines remain in the R2 SQLite snapshot; only the compact manifest and any
changed validation rows are sent to D1.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from scripts.audit_d1 import DB, pull_snapshot, push_partitions, push_snapshot  # noqa: E402
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402
from scripts.sync_audit_reports import list_r2_pdfs  # noqa: E402
from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.source_capture import (  # noqa: E402
    TARGET_LANES,
    capture_and_upsert,
    load_manifest,
)
from src.audit_reports.validator import upsert_validation  # noqa: E402


def _csv(value: str, *, upper: bool = False) -> set[str] | None:
    values = {part.strip() for part in value.split(",") if part.strip()}
    if not values or values == {"ALL"}:
        return None
    return {part.upper() for part in values} if upper else values


def _pending_lanes(
    conn: sqlite3.Connection,
    bank: str,
    period: str,
    kind: str,
    lanes: tuple[str, ...],
    *,
    refresh_existing: bool,
) -> tuple[str, ...]:
    if refresh_existing:
        return lanes
    return tuple(
        lane for lane in lanes
        if (manifest := load_manifest(conn, bank, period, kind, lane)) is None
        or manifest.get("capture_status") != "captured"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--lanes", default="ALL",
                        help="ALL or comma-separated capture lanes")
    parser.add_argument("--banks", default="ALL",
                        help="ALL or comma-separated tickers")
    parser.add_argument("--periods", default="",
                        help="comma-separated YYYYQn; blank means all")
    parser.add_argument("--kind", default="",
                        choices=["", "consolidated", "unconsolidated"])
    parser.add_argument("--limit", type=int, default=0,
                        help="maximum PDFs after filters; 0 means all")
    parser.add_argument("--refresh-existing", action="store_true",
                        help="recompute existing manifests too (content-idempotent)")
    parser.add_argument("--dry-run", action="store_true",
                        help="update only the local DB; no D1 or R2 snapshot writes")
    parser.add_argument("--no-pull", action="store_true",
                        help="use the existing local DB instead of pulling R2")
    args = parser.parse_args()

    requested = _csv(args.lanes)
    lanes = tuple(TARGET_LANES if requested is None else requested)
    unknown = set(lanes) - set(TARGET_LANES)
    if unknown:
        parser.error(f"unknown capture lane(s): {','.join(sorted(unknown))}")
    banks = _csv(args.banks, upper=True)
    periods = _csv(args.periods, upper=True)

    db_path = Path(args.db)
    if not args.no_pull:
        pull_snapshot(guard=True)
        db_path = DB
    pdfs = list_r2_pdfs()
    if banks:
        pdfs = [row for row in pdfs if row[0].upper() in banks]
    if periods:
        pdfs = [row for row in pdfs if row[1].upper() in periods]
    if args.kind:
        pdfs = [row for row in pdfs if row[2] == args.kind]
    if args.limit > 0:
        pdfs = pdfs[:args.limit]

    manifest_touched: set[tuple[str, str, str]] = set()
    validation_touched: set[tuple[str, str, str]] = set()
    source_touched: set[tuple[str, str, str]] = set()
    scanned = skipped = failed = 0
    started = time.time()
    with sqlite3.connect(str(db_path)) as conn:
        init_schema(conn)
        with tempfile.TemporaryDirectory(prefix="audit_capture_") as tmp_dir:
            for index, (bank, period, kind, key) in enumerate(pdfs, 1):
                pending = _pending_lanes(
                    conn, bank, period, kind, lanes,
                    refresh_existing=args.refresh_existing,
                )
                if not pending:
                    skipped += 1
                    continue
                dest = Path(tmp_dir) / f"{bank}_{period}_{kind}.pdf"
                try:
                    r2_storage.download_to(key, dest)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"  [FAIL] {bank:<8} {period} {kind:<14} "
                          f"{type(exc).__name__}:{str(exc)[:100]}", flush=True)
                    continue
                conn.execute("SAVEPOINT source_capture_partition")
                try:
                    written = capture_and_upsert(
                        conn, bank, period, kind, dest, lanes=pending)
                    validation_changed = False
                    if written.manifest_changed_lanes:
                        results = revalidate_partition(conn, bank, period, kind)
                        validation_changed = upsert_validation(
                            conn, bank, period, kind, results)
                except Exception as exc:  # noqa: BLE001
                    conn.execute("ROLLBACK TO source_capture_partition")
                    conn.execute("RELEASE source_capture_partition")
                    failed += 1
                    print(f"  [FAIL] {bank:<8} {period} {kind:<14} "
                          f"{type(exc).__name__}:{str(exc)[:100]}", flush=True)
                    continue
                else:
                    conn.execute("RELEASE source_capture_partition")
                finally:
                    try:
                        dest.unlink()
                    except OSError:
                        pass

                scanned += 1
                part = (bank, period, kind)
                if written.source_changed_lanes:
                    source_touched.add(part)
                if written.manifest_changed_lanes:
                    manifest_touched.add(part)
                    if validation_changed:
                        validation_touched.add(part)
                if index % 25 == 0:
                    conn.commit()
                    print(f"  [{index}/{len(pdfs)}] scanned={scanned} "
                          f"manifest_changed={len(manifest_touched)}", flush=True)
            conn.commit()

    elapsed = time.time() - started
    print(
        f"[capture] pdfs={len(pdfs)} scanned={scanned} skipped={skipped} "
        f"failed={failed} source_changed={len(source_touched)} "
        f"manifest_changed={len(manifest_touched)} "
        f"validation_changed={len(validation_touched)} ({elapsed:.0f}s)",
        flush=True,
    )
    if args.dry_run:
        print("[capture] dry-run: local DB only; no D1/R2 writes", flush=True)
        return 0 if failed == 0 else 1
    touched = sorted(manifest_touched | validation_touched)
    if touched:
        # One atomic partition replacement keeps the backfill to one D1 call.
        push_partitions(
            touched, db_path=db_path, window_hours=24,
            tables=["bank_audit_capture_manifest", "bank_audit_validation"],
        )
    if source_touched or manifest_touched or validation_touched:
        push_snapshot(db_path)
    else:
        print("[capture] no changed evidence; no D1/R2 writes", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
