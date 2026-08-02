#!/usr/bin/env python3
"""Which hand corrections are now OBSOLETE — already fixed by the extractor?

TEB 2022Q4 off-balance `III.` was corrected by hand because the stored row read
`'TÜREV FİNANSAL ARAÇLAR ( I I I - 2 ) 141 , 986 , 717'` — a letter-spaced
cross-reference swallowed by the label, losing the TL column. Re-run today the
extractor produces `'TÜREV FİNANSAL ARAÇLAR'` with 141,986,717 / 188,416,628 /
330,403,345: exactly the human's values. The pdfplumber -> fitz migration
(2026-07-15) fixed the class; the override is papering over data extracted
before it.

So the question is how much of the backlog is stale rather than broken. Two
groups by the humans' own notes:

  cross-ref garbling   ~97   ALNTF 89, TEB 8
  column slip           68

For each, re-extract the lane from the PDF in R2 and compare against the human's
corrected value:

  STALE   extractor now reproduces the correction  -> the override is obsolete
  BROKEN  extractor still differs                  -> a real, live defect

Local. Pulls PDFs from R2 into data/_bench; no API, no D1, no writes.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.audit_reports import r2_storage  # noqa: E402

CACHE = ROOT / "data" / "_bench"
CACHE.mkdir(parents=True, exist_ok=True)

# Lanes this probe can re-extract and compare row-wise.
ROW_LANES = {"off_balance": "off_balance", "assets": "bs_assets",
             "liabilities": "bs_liabilities", "profit_loss": "profit_loss"}


def group_of(note: str) -> str | None:
    n = " ".join((note or "").split()).lower()
    if "cross-ref" in n:
        return "cross-ref"
    if "column" in n or "slip" in n or "shift" in n:
        return "column-slip"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="both",
                    choices=["cross-ref", "column-slip", "both"])
    ap.add_argument("--max-pdfs", type=int, default=200)
    args = ap.parse_args()

    from src.audit_reports.extractor import extract

    ov = json.loads(
        (ROOT / "data/audit_overrides.json").read_text(encoding="utf-8"))["overrides"]

    todo: dict[tuple, list] = collections.defaultdict(list)
    skipped_lane: collections.Counter = collections.Counter()
    for x in ov:
        g = group_of(x.get("note", ""))
        if not g or (args.group != "both" and g != args.group):
            continue
        st = x.get("statement")
        if st not in ROW_LANES:
            skipped_lane[f"{g}:{st}"] += 1
            continue
        if x.get("amount_total") is None and x.get("amount") is None:
            skipped_lane[f"{g}:{st}:no-amount"] += 1
            continue
        todo[(x["bank_ticker"], x["period"], x["kind"])].append((g, x))

    n_cells = sum(len(v) for v in todo.values())
    print(f"{len(todo)} partitions, {n_cells} comparable cells")
    if skipped_lane:
        print(f"not row-comparable (different shape): {dict(skipped_lane)}")
    print()

    res: collections.Counter = collections.Counter()
    per_group: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    broken: list[str] = []

    for i, (key, items) in enumerate(sorted(todo.items())):
        if i >= args.max_pdfs:
            res["not tested"] += len(items)
            continue
        bank, period, kind = key
        pdf = CACHE / f"{bank}_{period}_{kind}.pdf"
        if not pdf.exists():
            r2key = f"{bank.lower()}/{bank}_{period}_{kind}.pdf"
            if not r2_storage.exists(r2key):
                res["no pdf"] += len(items)
                continue
            r2_storage.download_to(r2key, pdf)

        want_lanes = {ROW_LANES[x["statement"]] for _g, x in items}
        try:
            rep = extract(pdf, only=want_lanes)
        except Exception as e:  # noqa: BLE001
            print(f"  {bank} {period} {kind[:5]}: extract failed {type(e).__name__}")
            res["extract failed"] += len(items)
            continue

        for g, x in items:
            attr = ROW_LANES[x["statement"]]
            rows = getattr(rep, attr, []) or []
            h = (x.get("hierarchy") or "").strip()
            row = next((r for r in rows if (r.hierarchy or "").strip() == h), None)
            if row is None:
                res["row not found"] += 1
                per_group[g]["row not found"] += 1
                continue

            if x.get("amount_total") is not None:      # three-column lanes
                got = (int(row.cur_tl or 0), int(row.cur_fc or 0),
                       int(row.cur_total or 0))
                exp = (int(x.get("amount_tl") or 0), int(x.get("amount_fc") or 0),
                       int(x["amount_total"]))
            else:                                       # single-amount lanes
                got = (int(row.cur_amount or 0),)
                exp = (int(x["amount"]),)

            verdict = "STALE" if got == exp else "BROKEN"
            res[verdict] += 1
            per_group[g][verdict] += 1
            if verdict == "BROKEN" and len(broken) < 20:
                broken.append(f"{bank} {period} {kind[:5]} {x['statement']} {h}: "
                              f"got {got} want {exp}")

    print(f"{'verdict':16s} {'n':>6s}")
    print("-" * 26)
    for k in ("STALE", "BROKEN", "row not found", "no pdf", "extract failed",
              "not tested"):
        if res[k]:
            print(f"{k:16s} {res[k]:6d}")
    print("-" * 26)
    print(f"{'TOTAL':16s} {sum(res.values()):6d}")

    print(f"\n{'group':14s} {'STALE':>7s} {'BROKEN':>7s} {'not found':>10s}")
    for g, c in sorted(per_group.items()):
        print(f"{g:14s} {c['STALE']:7d} {c['BROKEN']:7d} {c['row not found']:10d}")

    if broken:
        print("\nstill broken:")
        for b in broken:
            print("  -", b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
