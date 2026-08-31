#!/usr/bin/env python
"""Full-document table capture over the audit corpus.

Reads each filing's PDF once and records EVERY table it prints — rows, columns,
cells — plus the footnotes that qualify them, linked to the rows carrying their
marker. See src/audit_reports/document_capture.py for the extraction contract.

It never writes an analytical row, so it is safe over the settled balance-sheet
and P&L partitions: it only adds evidence beside them.

Destinations (see document_store.py for why they differ):
  data/bank_audit_capture.db     raw ledger  — local only, never D1
  data/audit_capture/*.jsonl     per-partition export — local only
  <audit db>.bank_audit_document_manifest   compact counts+hashes — reaches D1

Examples
--------
  # one partition from a local PDF, no DB writes
  python scripts/backfill_document_capture.py --pdf data/eye/AKBNK_2026Q1_consolidated.pdf --dry-run

  # every local PDF under data/eye, writing ledger + manifest + jsonl
  python scripts/backfill_document_capture.py --source-dir data/eye

  # pull from R2 instead (bounded), 40 partitions at a time
  python scripts/backfill_document_capture.py --from-r2 --limit 40
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.document_capture import capture_document  # noqa: E402
from src.audit_reports import document_store as store  # noqa: E402

NAME_RX = re.compile(r"^([A-Z0-9]+)_(\d{4}Q\d)_(consolidated|unconsolidated)\.pdf$", re.I)
DEFAULT_AUDIT_DB = REPO / "data" / "bank_audit.db"


def _parse_name(path: Path) -> tuple[str, str, str] | None:
    m = NAME_RX.match(path.name)
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper(), m.group(3).lower()


def _local_targets(args) -> list[tuple[str, str, str, Path]]:
    if args.pdf:
        out = []
        for raw in args.pdf:
            p = Path(raw)
            parsed = _parse_name(p)
            if not parsed:
                print(f"!! cannot parse bank/period/kind from {p.name}", file=sys.stderr)
                continue
            out.append((*parsed, p))
        return out
    src = Path(args.source_dir)
    out = []
    for p in sorted(src.glob("*.pdf")):
        parsed = _parse_name(p)
        if parsed:
            out.append((*parsed, p))
    return out


def _r2_targets() -> list[tuple[str, str, str, str]]:
    """Every audit PDF in R2 as (bank, period, kind, key). The object is fetched
    lazily per partition — the corpus is 3.3 GB, past what a runner should
    hold at once, so each PDF is downloaded, captured and deleted in turn."""
    from src.audit_reports import r2_storage

    return sorted(r2_storage.list_audit_pdfs())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--pdf", nargs="+", help="explicit PDF path(s)")
    src.add_argument("--source-dir", default="data/eye",
                     help="directory of <BANK>_<PERIOD>_<KIND>.pdf files (default: data/eye)")
    ap.add_argument("--pdf-dir",
                    help="with --from-r2, download into this directory and KEEP "
                         "the PDFs (skipping any already there) instead of "
                         "streaming to a temp file and deleting. The fleet is "
                         "3.3 GB; keeping it makes a re-capture a local read "
                         "rather than a re-fetch, which is what makes iterating "
                         "on the engine practical. Gitignored at "
                         "data/audit_pdfs/ — the data carries BDDK/KAP terms "
                         "and never enters the repo")
    ap.add_argument("--from-r2", action="store_true",
                    help="download each PDF from R2 into a temp dir instead of reading locally")
    ap.add_argument("--audit-db", default=str(DEFAULT_AUDIT_DB),
                    help="main audit DB that receives the compact manifest")
    ap.add_argument("--capture-db", default=str(REPO / store.CAPTURE_DB),
                    help="local-only raw ledger DB")
    ap.add_argument("--export-dir", default=str(REPO / store.EXPORT_DIR),
                    help="per-partition JSONL export directory")
    ap.add_argument("--no-ledger", action="store_true", help="skip the raw ledger writes")
    ap.add_argument("--no-jsonl", action="store_true", help="skip the JSONL export")
    ap.add_argument("--jsonl-gzip", action="store_true",
                    help="gzip each JSONL export (~85%% smaller; read with zgrep/zcat)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N partitions")
    ap.add_argument("--bank", help="only these comma-separated tickers")
    ap.add_argument("--period", help="only this period, e.g. 2026Q1")
    ap.add_argument("--recent-hours", type=int, default=0,
                    help="only partitions whose extraction row in the audit DB "
                         "was stamped within the last N hours — the incremental "
                         "form refresh-audit runs after each sync, so a new "
                         "filing's capture (and its reconcile anchor) lands the "
                         "same day it is extracted instead of waiting for the "
                         "next fleet backfill. Matching nothing is a quiet day, "
                         "not an error.")
    ap.add_argument("--pull-snapshot", action="store_true",
                    help="download the audit snapshot from R2 before capturing "
                         "(Actions; local runs normally already have it)")
    ap.add_argument("--push", action="store_true",
                    help="after capture, push ONLY bank_audit_document_manifest "
                         "to D1 and re-upload the audit snapshot")
    ap.add_argument("--upload-ledger", action="store_true",
                    help="gzip the raw capture DB and upload it to R2 "
                         "(state/bank_audit_capture.db.gz); never goes to D1")
    ap.add_argument("--dry-run", action="store_true",
                    help="capture and report, write nothing anywhere")
    args = ap.parse_args()
    if args.dry_run:
        args.push = args.upload_ledger = False

    targets = _r2_targets() if args.from_r2 else _local_targets(args)
    if args.bank:
        banks = {bank.strip().upper() for bank in args.bank.split(",") if bank.strip()}
        if not banks:
            ap.error("--bank must contain at least one ticker")
        targets = [t for t in targets if t[0] in banks]
    if args.period:
        targets = [t for t in targets if t[1] == args.period.upper()]
    if args.recent_hours:
        with sqlite3.connect(args.audit_db) as adb:
            recent = set(adb.execute(
                "SELECT bank_ticker, period, kind FROM bank_audit_extractions "
                "WHERE success=1 AND extracted_at >= datetime('now', ?)",
                (f"-{args.recent_hours} hours",)))
        targets = [t for t in targets if (t[0], t[1], t[2]) in recent]
    if args.limit:
        targets = targets[: args.limit]
    if not targets:
        print("no matching partitions", file=sys.stderr)
        return 0 if args.recent_hours else 1

    if args.pull_snapshot and not args.dry_run:
        from scripts.audit_d1 import pull_snapshot
        pull_snapshot(guard=True)

    ledger = manifest = None
    if not args.dry_run:
        if not args.no_ledger:
            Path(args.capture_db).parent.mkdir(parents=True, exist_ok=True)
            ledger = sqlite3.connect(args.capture_db)
            store.init_ledger(ledger)
        manifest = sqlite3.connect(args.audit_db)
        store.init_manifest(manifest)

    t0 = time.time()
    tot_lines = tot_cells = tot_notes = tot_linked = tot_blocks = 0
    changed = failed = 0
    keep_dir = Path(args.pdf_dir) if args.pdf_dir else None
    if keep_dir is not None:
        keep_dir.mkdir(parents=True, exist_ok=True)
    tmpctx = tempfile.TemporaryDirectory(prefix="doccap-")
    tmpdir = tmpctx.name
    try:
        for n, (bank, period, kind, source) in enumerate(targets, start=1):
            tmp: Path | None = None
            try:
                if args.from_r2:
                    from src.audit_reports import r2_storage
                    name = f"{bank}_{period}_{kind}.pdf"
                    if keep_dir is not None:
                        # Kept between runs, so a second capture over the same
                        # fleet re-reads from disk instead of re-fetching 3.3 GB.
                        path = keep_dir / name
                        if not path.exists() or path.stat().st_size == 0:
                            r2_storage.download_to(str(source), path)
                    else:
                        tmp = Path(tmpdir) / name
                        r2_storage.download_to(str(source), tmp)
                        path = tmp
                else:
                    path = source
                cap = capture_document(path)
            except Exception as e:  # a poison PDF must not sink the run
                failed += 1
                print(f"!! {bank} {period} {kind}: {type(e).__name__}: {e}",
                      file=sys.stderr)
                continue
            finally:
                # Delete as we go: the full corpus is 3.3 GB and a runner's disk
                # is not.
                if tmp is not None and tmp.exists():
                    tmp.unlink()
            linked = sum(1 for p in cap.pages for x in p.notes if x.linked_line_orders)
            tot_lines += cap.line_count
            tot_cells += cap.cell_count
            tot_notes += cap.note_count
            tot_linked += linked
            tot_blocks += cap.block_count
            if not args.dry_run:
                if ledger is not None:
                    store.upsert_ledger(ledger, bank, period, kind, cap)
                    ledger.commit()
                if store.upsert_manifest(manifest, bank, period, kind, cap):
                    changed += 1
                manifest.commit()
                if not args.no_jsonl:
                    store.export_jsonl(cap, bank, period, kind, args.export_dir,
                                       gzipped=args.jsonl_gzip)
            print(f"[{n}/{len(targets)}] {bank} {period} {kind}: "
                  f"{cap.page_count}p {cap.block_count}blk {cap.line_count}L "
                  f"{cap.cell_count}C {cap.note_count}N ({linked} linked) [{cap.status}]")
    finally:
        for c in (ledger, manifest):
            if c is not None:
                c.commit()
                c.close()
        tmpctx.cleanup()

    dt = time.time() - t0
    print(f"\n{len(targets) - failed}/{len(targets)} captured in {dt:.1f}s"
          f"{' (DRY RUN — nothing written)' if args.dry_run else ''}")
    print(f"  blocks {tot_blocks:,} | lines {tot_lines:,} | cells {tot_cells:,} | "
          f"notes {tot_notes:,} ({tot_linked:,} linked to rows)")
    if not args.dry_run:
        print(f"  manifest rows changed (D1-bound): {changed}")
        if ledger is not None:
            print(f"  ledger: {args.capture_db}")
        if not args.no_jsonl:
            print(f"  jsonl:  {args.export_dir}")

    if args.upload_ledger and ledger is not None:
        _upload_ledger(Path(args.capture_db))
    if args.push:
        # ONLY the manifest. The raw ledger lives in its own DB and its own R2
        # object; letting the default audit table-set run here would push
        # unrelated lanes that this job never touched.
        from scripts.audit_d1 import push_snapshot, push_to_d1
        push_to_d1(db_path=Path(args.audit_db),
                   tables=["bank_audit_document_manifest"])
        push_snapshot(Path(args.audit_db))
    return 1 if failed and failed == len(targets) else 0


def _upload_ledger(db_path: Path) -> None:
    """Ship the raw ledger to R2 as its own object — never into the audit
    snapshot, which every workflow downloads."""
    import gzip
    import shutil

    from src.audit_reports import r2_storage

    gz = db_path.with_suffix(db_path.suffix + ".gz")
    with open(db_path, "rb") as s, gzip.open(gz, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    key = "state/bank_audit_capture.db.gz"
    size = r2_storage.upload_file(gz, key, content_type="application/gzip")
    print(f"  ledger uploaded ({size / 1e6:.1f} MB) → R2 {key}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
