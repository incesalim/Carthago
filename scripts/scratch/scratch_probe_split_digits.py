#!/usr/bin/env python3
"""How widespread is digit-splitting in the audit text layer?

`capital_adequacy.py` documents it as a local quirk — "Toplam Özkaynak
1 1,372,338 1 0,094,760" is 11,372,338 and 10,094,760, the glyphs separated by
stray spaces in the text layer even though the page reads correctly. It was
found again while diagnosing why an LLM could not locate npl_movement values
that were sitting on the page it was shown.

Nobody has measured how common it is, so this does. Method, over STORED and
already-validated rows (not overrides), for each value on its `source_page`:

  exact   the value appears formatted as printed        -> clean
  split   it appears only once every non-digit is       -> DIGIT-SPLIT
          stripped from the page
  absent  neither                                       -> elsewhere/drawn/derived

`split` is the defect: the figure is on the page and legible to a human, but no
exact-string match — ours or a model's — can find it.

RESULT (2026-08-02, 424 stored cells over 60 PDFs): **0 split cases**. The
squish `capital_adequacy.py` documents is real but RARE, not a corpus-wide
defect, and a claim that it explained npl_movement's low score does not survive
this. That claim came from a digits-only match over a whole page, which
concatenates every digit on it — a 5-6 digit value collides by chance. Match
per-value against the formatted string, never against a flattened page.

What the run DID show: 143 of 424 stored values (34%) are not on their recorded
`source_page` at all. `source_page` marks where the SECTION starts, so the value
is frequently pages later — the same thing the retrieval-ceiling probe measures
per lane.

Read-only. Uses whatever PDFs are already cached in data/_bench; pass --pull to
fetch more from R2.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from src.audit_reports import r2_storage  # noqa: E402

CACHE = ROOT / "data" / "_bench"
CACHE.mkdir(parents=True, exist_ok=True)

LANES = {
    "capital": ("bank_audit_capital",
                ["cet1_capital", "tier1_capital", "tier2_capital",
                 "total_capital", "total_rwa"]),
    "npl_movement": ("bank_audit_npl_movement",
                     ["opening_balance", "additions", "collections",
                      "closing_balance", "provision"]),
    "credit_quality": ("bank_audit_credit_quality",
                       ["stage1_amount", "stage2_amount", "stage3_amount",
                        "total_amount"]),
    "fx_position": ("bank_audit_fx_position",
                    ["on_bs_assets", "on_bs_liab", "net_position"]),
    "repricing": ("bank_audit_repricing",
                  ["rate_sensitive_assets", "rate_sensitive_liab"]),
}


def variants(v: float) -> list[str]:
    n = abs(int(round(v)))
    s = f"{n:,}"
    return [s, s.replace(",", "."), str(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", type=int, default=40)
    ap.add_argument("--pull", action="store_true",
                    help="download missing PDFs from R2 instead of skipping")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    cells: list[tuple] = []
    for lane, (table, fields) in LANES.items():
        cols = {c[1] for c in db.execute(f"pragma table_info({table})")}
        if "source_page" not in cols:
            continue
        for r in db.execute(
                f"SELECT * FROM {table} WHERE source_page IS NOT NULL "
                f"AND source_page > 0 LIMIT 3000"):
            for f in fields:
                if f not in cols:
                    continue
                v = r[f]
                # Small values collide with page numbers and footnote refs.
                if v is None or abs(v) < 1000:
                    continue
                cells.append((r["bank_ticker"], r["period"], r["kind"], lane,
                              f, float(v), r["source_page"]))
    db.close()

    order = collections.OrderedDict()
    for c in cells:
        order.setdefault((c[0], c[1], c[2]), None)
    use = list(order)[:args.pdfs]
    print(f"{len(cells)} stored cells; checking {len(use)} PDFs\n")

    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    examples: list[str] = []
    for bank, period, kind in use:
        pdf = CACHE / f"{bank}_{period}_{kind}.pdf"
        if not pdf.exists():
            if not args.pull:
                continue
            key = f"{bank.lower()}/{bank}_{period}_{kind}.pdf"
            if not r2_storage.exists(key):
                continue
            r2_storage.download_to(key, pdf)
        doc = fitz.open(pdf)
        raw: dict[int, str] = {}
        flat: dict[int, str] = {}
        for c in cells:
            if (c[0], c[1], c[2]) != (bank, period, kind):
                continue
            _, _, _, lane, f, v, page = c
            if not (1 <= page <= doc.page_count):
                continue
            if page not in raw:
                t = doc[page - 1].get_text()
                raw[page] = re.sub(r"\s+", " ", t)
                flat[page] = re.sub(r"[^\d]", "", t)
            if any(s in raw[page] for s in variants(v)):
                out[lane]["exact"] += 1
            elif str(abs(int(round(v)))) in flat[page]:
                out[lane]["split"] += 1
                if len(examples) < 6:
                    m = re.search(
                        r".{0,34}" + r"[^\d]?".join(str(abs(int(round(v))))[:9])
                        + r".{0,14}", raw[page])
                    examples.append(
                        f"{bank} {period} {kind[:5]} {lane}.{f} = {int(v):,}"
                        + (f"\n        printed as: {m.group(0).strip()!r}" if m else ""))
            else:
                out[lane]["absent"] += 1
        doc.close()

    print(f"{'lane':16s} {'n':>5s} {'exact':>7s} {'SPLIT':>7s} {'absent':>7s}   split%")
    print("-" * 60)
    tot: collections.Counter = collections.Counter()
    for lane, c in sorted(out.items()):
        n = sum(c.values())
        tot.update(c)
        print(f"{lane:16s} {n:5d} {c['exact']:7d} {c['split']:7d} {c['absent']:7d}"
              f"   {100.0 * c['split'] / max(1, n):5.1f}%")
    n = sum(tot.values())
    print("-" * 60)
    print(f"{'ALL':16s} {n:5d} {tot['exact']:7d} {tot['split']:7d} {tot['absent']:7d}"
          f"   {100.0 * tot['split'] / max(1, n):5.1f}%")
    if examples:
        print("\nsplit examples (value is on the page, but not as a matchable string):")
        for e in examples:
            print("  -", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
