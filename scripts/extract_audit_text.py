"""Tier-1 prose lane: BRSA audit-report PDF → page-anchored text → R2.

The statement extractors each read the PDF, take the pages they care about, and
throw the rest away. Roughly 40% of a filing is prose (accounting policies, the
Pillar-3 narrative, ratings, subsequent events) that no lane has ever looked at,
and there is no way to ask "which banks mention X" because the text does not
exist anywhere outside the PDFs.

This lane materialises it once. No model, no D1 writes, no interpretation — it
is a transcription step whose output every later lane can read cheaply.

Three design choices worth stating, because each has a cheaper wrong version:

  * **Page-anchored JSONL, not one flat .txt.** Every consumer in this repo works
    in page coordinates — `source_page` columns, triage's page render, the
    extractors' page scan. A flat blob throws that away and cannot be rejoined
    to anything.
  * **It reuses `_fitz_page_text`, the extractors' own reader.** Calling
    `page.get_text()` here would be a one-line shortcut that silently diverges:
    the shared reader rebuilds lines from word coordinates and maps /Rotate 90
    pages through the rotation matrix. Text dumped by a *different* reader would
    disagree with what the extractors saw, and the disagreement would surface
    later as a phantom data bug.
  * **The manifest records text-layer health, not just sizes.** An empty
    `get_text()` is ambiguous — undisclosed, or a page drawn as vectors. Per-page
    image/drawing counts turn that ambiguity into a decidable flag, fleet-wide,
    for free.

Idempotent: a filing is skipped when its stored text already carries the current
PDF's sha256, so a re-run costs one R2 HEAD per filing.

Usage:
  # local single-PDF test — no R2, no network
  python scripts/extract_audit_text.py --pdf data/eye/AKBNK_2024Q1_unconsolidated.pdf \
      --out-dir build/audit_text

  # fleet, from R2 back to R2 (GitHub Actions)
  python scripts/extract_audit_text.py --workers 8
  python scripts/extract_audit_text.py --only-bank AKBNK,GARAN

Env vars (fleet mode only):
  R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY [R2_BUCKET]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF — the only PDF engine in this repo (see check_no_pdfplumber)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.extractor import _fitz_page_text  # noqa: E402

# Text objects sit under a `text/` prefix in the same bucket as the PDFs, so one
# R2 token and one lifecycle policy cover both.
TEXT_PREFIX = "text"
# A page whose text layer is thinner than this is treated as empty — a caption or
# a stray header can leave a handful of chars on a page that is really an image.
EMPTY_PAGE_CHARS = 40


def text_key(ticker: str, period: str, kind: str) -> str:
    """R2 key for a filing's extracted text. Mirrors r2_storage.make_key."""
    return (f"{TEXT_PREFIX}/{ticker.lower()}/"
            f"{ticker.upper()}_{period.upper()}_{kind.lower()}.jsonl.gz")


def extract_pages(pdf_path: str | Path) -> tuple[dict, list[dict]]:
    """Read one PDF into (manifest, page_records).

    The manifest is the filing-level header; page_records carry the text itself
    plus the per-page signals that make an empty text layer interpretable.
    """
    pdf_path = Path(pdf_path)
    raw = pdf_path.read_bytes()
    doc = fitz.open(stream=raw, filetype="pdf")

    pages: list[dict] = []
    for i in range(doc.page_count):
        page = doc[i]
        text = _fitz_page_text(str(pdf_path), i)
        pages.append({
            "page": i + 1,                       # 1-based, matches source_page
            "chars": len(text),
            "words": len(text.split()),
            "rotation": page.rotation,
            "images": len(page.get_images()),
            "drawings": len(page.get_drawings()),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "text": text,
        })
    page_count = doc.page_count
    doc.close()

    empty = [p["page"] for p in pages if p["chars"] < EMPTY_PAGE_CHARS]
    manifest = {
        "record": "manifest",
        "pdf_sha256": hashlib.sha256(raw).hexdigest(),
        "pdf_bytes": len(raw),
        "pages": page_count,
        "chars": sum(p["chars"] for p in pages),
        # Health signals. An empty page that carries drawings is a vector-rendered
        # table, not an undisclosed note — the distinction that "the text layer is
        # not the filing" exists to protect.
        "empty_pages": empty,
        "empty_but_drawn": [p["page"] for p in pages
                            if p["chars"] < EMPTY_PAGE_CHARS and p["drawings"] > 0],
        "rotated_pages": [p["page"] for p in pages if p["rotation"]],
        # Pinned in the record because a PyMuPDF upgrade can move the text layer;
        # a text object that cannot name its engine cannot be diffed against one.
        "engine": f"pymupdf-{fitz.__version__}",
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return manifest, pages


def to_jsonl_gz(manifest: dict, pages: list[dict]) -> bytes:
    """Serialise to gzipped JSONL — manifest first, then one record per page."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for rec in [manifest, *pages]:
            gz.write((json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
    return buf.getvalue()


def stored_pdf_sha(key: str) -> str | None:
    """The pdf_sha256 recorded in an existing text object, or None if absent.

    Reads only the first record: R2 range-GETs the opening bytes, so the check
    costs a fraction of the object rather than a full download.
    """
    try:
        client = r2_storage.get_client()
        obj = client.get_object(Bucket=r2_storage._bucket(), Key=key,
                                Range="bytes=0-4095")
        head = gzip.GzipFile(fileobj=io.BytesIO(obj["Body"].read())).readline()
        return json.loads(head).get("pdf_sha256")
    except Exception:
        return None


def process_one(ticker: str, period: str, kind: str, pdf_key: str,
                force: bool = False) -> dict:
    """Fleet path: R2 PDF → text object in R2. Returns a per-filing summary."""
    out_key = text_key(ticker, period, kind)
    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "f.pdf"
        r2_storage.download_to(pdf_key, local)
        pdf_sha = hashlib.sha256(local.read_bytes()).hexdigest()
        if not force and stored_pdf_sha(out_key) == pdf_sha:
            return {"key": out_key, "status": "skip", "pages": 0}
        manifest, pages = extract_pages(local)
        body = to_jsonl_gz(manifest, pages)
        r2_storage.upload_bytes(body, out_key, content_type="application/gzip")
    return {"key": out_key, "status": "written", "pages": manifest["pages"],
            "chars": manifest["chars"], "bytes": len(body)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", help="local PDF — test mode, skips R2 entirely")
    ap.add_argument("--out-dir", default="build/audit_text",
                    help="where --pdf writes its output")
    ap.add_argument("--only-bank", help="comma-separated tickers (fleet mode)")
    ap.add_argument("--limit", type=int, help="stop after N filings (fleet mode)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true",
                    help="re-extract even when the stored pdf_sha256 matches")
    args = ap.parse_args()

    if args.pdf:
        manifest, pages = extract_pages(args.pdf)
        body = to_jsonl_gz(manifest, pages)
        name = Path(args.pdf).stem
        out = Path(args.out_dir) / f"{name}.jsonl.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(body)
        print(f"{Path(args.pdf).name}")
        print(f"  pages         {manifest['pages']}")
        print(f"  chars         {manifest['chars']:,}")
        print(f"  empty pages   {len(manifest['empty_pages'])} "
              f"({len(manifest['empty_but_drawn'])} vector-drawn)")
        print(f"  rotated pages {len(manifest['rotated_pages'])}")
        print(f"  written       {out}  ({len(body):,} B gz, "
              f"{len(body) / max(manifest['chars'], 1):.2f} B/char)")
        print(f"  would upload  {text_key(*name.split('_'))}")
        return 0

    targets = r2_storage.list_audit_pdfs()
    if args.only_bank:
        want = {t.strip().upper() for t in args.only_bank.split(",")}
        targets = [t for t in targets if t[0] in want]
    if args.limit:
        targets = targets[:args.limit]
    print(f"{len(targets)} filings")

    written = skipped = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_one, *t, force=args.force): t for t in targets}
        for fut in as_completed(futs):
            ticker, period, kind, _ = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # one bad filing must not sink the run
                print(f"  FAIL {ticker} {period} {kind}: {e}")
                continue
            if res["status"] == "skip":
                skipped += 1
            else:
                written += 1
                print(f"  {ticker} {period} {kind}: {res['pages']}p "
                      f"{res['bytes']:,} B")
    print(f"\n{written} written, {skipped} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
