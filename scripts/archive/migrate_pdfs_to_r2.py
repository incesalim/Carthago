"""One-shot migration: upload all local audit-report PDFs to R2.

Run once after enabling R2 + creating the bucket + setting env vars:
    R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY

Idempotent: skips files that already exist in R2 at the same key.

Usage:
    python scripts/migrate_pdfs_to_r2.py [--workers 8] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402

LOCAL_ROOT = REPO_ROOT / "data" / "audit_reports"
STD_PAT = re.compile(r"^([A-Z]+)_(\d{4}Q\d)_(consolidated|unconsolidated)\.pdf$", re.I)


def discover_local_pdfs() -> list[tuple[str, str, str, Path]]:
    """Return [(ticker, period, kind, path), ...] for all matching local PDFs."""
    out: list[tuple[str, str, str, Path]] = []
    if not LOCAL_ROOT.exists():
        return out
    for folder in sorted(LOCAL_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        for pdf in sorted(folder.glob("*.pdf")):
            m = STD_PAT.match(pdf.name)
            if not m:
                continue
            tkr, period, kind = m.group(1).upper(), m.group(2).upper(), m.group(3).lower()
            out.append((tkr, period, kind, pdf))
    return out


def upload_one(args: tuple[str, str, str, Path, bool]) -> tuple[str, str, str, str, int]:
    ticker, period, kind, path, dry = args
    key = r2_storage.make_key(ticker, period, kind)
    try:
        if r2_storage.exists(key):
            return (ticker, period, kind, "skip", path.stat().st_size)
        if dry:
            return (ticker, period, kind, "would-upload", path.stat().st_size)
        size = r2_storage.upload_file(path, key)
        return (ticker, period, kind, "uploaded", size)
    except Exception as e:
        return (ticker, period, kind, f"err:{type(e).__name__}:{str(e)[:80]}", 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be uploaded without actually uploading.")
    args = ap.parse_args()

    pdfs = discover_local_pdfs()
    print(f"discovered {len(pdfs)} local PDFs under {LOCAL_ROOT}")
    if not pdfs:
        print("nothing to migrate")
        return

    total_bytes = sum(p.stat().st_size for *_, p in pdfs)
    print(f"total {total_bytes / 1024 / 1024:.1f} MB local")
    print(f"target bucket: {r2_storage._bucket()}")
    print(f"using {args.workers} workers" + (" (DRY RUN)" if args.dry_run else ""))
    print()

    work = [(tkr, period, kind, path, args.dry_run) for tkr, period, kind, path in pdfs]
    t0 = time.time()
    counts = {"uploaded": 0, "skip": 0, "would-upload": 0, "err": 0}
    bytes_uploaded = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(upload_one, w) for w in work]
        for i, fut in enumerate(as_completed(futures), 1):
            tkr, period, kind, status, size = fut.result()
            if status.startswith("err"):
                counts["err"] += 1
                print(f"  [FAIL] {tkr:<8} {period} {kind:<14} {status}")
            elif status == "uploaded":
                counts["uploaded"] += 1
                bytes_uploaded += size
                if counts["uploaded"] % 20 == 1 or counts["uploaded"] <= 10:
                    print(f"  [{i:>4}/{len(work)}] uploaded {tkr:<8} {period} {kind:<14} ({size/1024/1024:.1f} MB)")
            elif status == "skip":
                counts["skip"] += 1
            elif status == "would-upload":
                counts["would-upload"] += 1
                if counts["would-upload"] <= 20:
                    print(f"  would upload: {tkr:<8} {period} {kind:<14} ({size/1024/1024:.1f} MB)")

    elapsed = time.time() - t0
    print()
    print(f"done in {elapsed/60:.1f} min")
    print(f"  uploaded:     {counts['uploaded']}  ({bytes_uploaded/1024/1024:.1f} MB)")
    print(f"  skipped:      {counts['skip']}")
    if counts["would-upload"]:
        print(f"  would-upload: {counts['would-upload']}  (re-run without --dry-run)")
    print(f"  errors:       {counts['err']}")


if __name__ == "__main__":
    main()
