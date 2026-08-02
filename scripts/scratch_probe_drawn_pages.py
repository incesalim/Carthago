#!/usr/bin/env python3
"""How much of the audit corpus is DRAWN rather than typed?

A drawn page reads perfectly to a human and returns nothing from
`page.get_text()`, so the deterministic extractor is blind to it and a text LLM
is equally blind. It is the confirmed cause behind:

  * the 59 hand-transcribed statements in data/manual_statements.json
  * FIBA 2022Q1 note-5.9.2, whose override note says the movement table
    "IS PRINTED but is invisible to fitz's get_text()"
  * most of what the npl_movement repair bench could not reach

⚠️ TWO mechanisms produce it and only one involves an image. FIBA 2025Q1 p11
carries 368 embedded images; FIBA 2022Q1 pp10-16 carry ZERO images and
848-1,775 vector DRAWINGS — every glyph a path. Counting `get_images()` alone
reports the second as healthy, which is why this counts marks of either kind
against a low text length.

Read-only, no API. Uses PDFs already cached in data/_bench; --pull fetches more.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from src.audit_reports import r2_storage  # noqa: E402

CACHE = ROOT / "data" / "_bench"
CACHE.mkdir(parents=True, exist_ok=True)

TEXT_FLOOR = 400   # chars: below this a full statement page has nothing usable
MARK_FLOOR = 200   # drawings + images: above this the page is rendering content


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", type=int, default=0,
                    help="download up to N more audit PDFs from R2")
    args = ap.parse_args()

    if args.pull:
        have = {p.stem for p in CACHE.glob("*.pdf")}
        for ticker, period, kind, key in r2_storage.list_audit_pdfs():
            if len(have) >= len(list(CACHE.glob("*.pdf"))) + args.pull:
                break
            stem = f"{ticker}_{period}_{kind}"
            if stem in have:
                continue
            r2_storage.download_to(key, CACHE / f"{stem}.pdf")
            have.add(stem)

    pdfs = sorted(CACHE.glob("*.pdf"))
    print(f"{len(pdfs)} cached PDFs\n")

    per_pdf: list[tuple[str, int, int]] = []
    tot_pages = tot_drawn = 0
    by_bank: collections.Counter = collections.Counter()
    for p in pdfs:
        doc = fitz.open(p)
        drawn = 0
        for i in range(doc.page_count):
            pg = doc[i]
            marks = len(pg.get_drawings()) + len(pg.get_images())
            if len(pg.get_text().strip()) < TEXT_FLOOR and marks > MARK_FLOOR:
                drawn += 1
        tot_pages += doc.page_count
        tot_drawn += drawn
        if drawn:
            per_pdf.append((p.stem, drawn, doc.page_count))
            by_bank[p.stem.split("_")[0]] += drawn
        doc.close()

    print(f"pages scanned:      {tot_pages:,}")
    print(f"drawn (unreadable): {tot_drawn:,}  ({100.0 * tot_drawn / max(1, tot_pages):.2f}%)")
    print(f"filings affected:   {len(per_pdf)}/{len(pdfs)} "
          f"({100.0 * len(per_pdf) / max(1, len(pdfs)):.0f}%)")
    if by_bank:
        print(f"\nby bank: {by_bank.most_common(12)}")
    if per_pdf:
        print("\nworst filings:")
        for stem, d, n in sorted(per_pdf, key=lambda x: -x[1])[:12]:
            print(f"  {stem:38s} {d:3d}/{n} pages drawn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
