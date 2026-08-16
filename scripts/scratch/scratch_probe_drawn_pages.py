#!/usr/bin/env python3
"""How much of the audit corpus is DRAWN rather than typed?

A drawn page reads perfectly to a human and returns nothing from
`page.get_text()`, so the deterministic extractor is blind to it and a text LLM
is equally blind. It is the confirmed cause behind:

  * the 59 hand-transcribed statements in data/manual_statements.json
  * FIBA 2022Q1 note-5.9.2, whose override note says the movement table
    "IS PRINTED but is invisible to fitz's get_text()"
  * most of what the npl_movement repair bench could not reach

⚠️ THREE renderings produce it, and each earlier version of this probe caught
only some — see the notes on `unreadable()` and `harmful()` below. Detecting it
needs marks of EITHER kind against a low text length, INCLUDING the single
full-page image, and then a filter for whether a statement was supposed to be
on that page at all.

RESULT (2026-08-02, 12,875 pages over 123 cached filings):

  statement pages lost   55  (0.43%)
  filings affected        8/123
  by bank                 FIBA 50, ISCTR 5 — nobody else

Counting every unreadable page instead gives 119 across 29 filings and 8 banks,
but most of that is scanned COVER matter: PASHA's three are pp2-4 with no text
at all, and all five of its statements are stored complete. The 55 figure is the
one that corresponds to data we actually lose.

Read-only, no API. Uses PDFs already cached in data/_bench; --pull fetches more.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from src.audit_reports import r2_storage  # noqa: E402

CACHE = ROOT / "data" / "_bench"
CACHE.mkdir(parents=True, exist_ok=True)

TEXT_FLOOR = 400   # chars: below this a full statement page has nothing usable
MARK_FLOOR = 200   # vector paths: FIBA renders every glyph as a path

# ⚠️ THREE renderings produce an unreadable page, and a single threshold catches
# only one of them:
#   FIBA 2022Q1 pp10-16   0 images, 848-1,775 vector DRAWINGS   -> marks > 200
#   FIBA 2025Q1 p11       368 embedded images                   -> marks > 200
#   ISCTR 2025Q1 p11      0 drawings, ONE full-page image       -> marks == 1
# The first version of this probe required marks > 200 and therefore reported
# ISCTR as healthy, which produced a confident and wrong "it is only FIBA".
# On a page whose text is under the floor, a single image IS the statement.


def unreadable(pg) -> bool:
    if len(pg.get_text().strip()) >= TEXT_FLOOR:
        return False
    return len(pg.get_drawings()) + len(pg.get_images()) > MARK_FLOOR \
        or len(pg.get_images()) >= 1


# An unreadable page only COSTS us something if a statement was supposed to be
# on it. PASHA's three are pp2-4 with no text at all — a scanned cover and
# opinion letter — and all five of its statements are stored complete. Counting
# those as damage inflates the number and points at the wrong banks. A harmful
# page keeps its running header, so the residual text names the statement.
_STATEMENT_RX = re.compile(
    r"balance\s*sheet|bilan[çc]o|profit\s*or\s*loss|kar\s*ve[yz]a\s*zarar|"
    r"comprehensive\s*income|kapsaml[iı]\s*gelir|cash\s*flow|nakit\s*ak[iı][sş]|"
    r"shareholders.{0,3}\s*equity|[öo]zkaynak\s*de[ğg]i[şs]im|"
    r"off[-\s]*balance|naz[iı]m\s*hesap", re.I)


def harmful(pg) -> bool:
    """Unreadable AND the residual header says a statement belongs here."""
    return unreadable(pg) and bool(_STATEMENT_RX.search(pg.get_text()))


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
            if harmful(doc[i]):
                drawn += 1
        tot_pages += doc.page_count
        tot_drawn += drawn
        if drawn:
            per_pdf.append((p.stem, drawn, doc.page_count))
            by_bank[p.stem.split("_")[0]] += drawn
        doc.close()

    print(f"pages scanned:      {tot_pages:,}")
    print(f"statement pages lost: {tot_drawn:,}  ({100.0 * tot_drawn / max(1, tot_pages):.2f}%)")
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
