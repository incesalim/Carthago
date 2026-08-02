#!/usr/bin/env python3
"""ONE text page where the deterministic extractor FAILED. One model. One row.

The earlier one-PDF test used a page regex already handles perfectly, so it
showed capability and no value. This uses the opposite: KUVEYT 2025Q1
unconsolidated off-balance, row `B. EMANET VE REHİNLİ KIYMETLER (IV+V+VI)`,
which needed a hand correction.

Why the anchors lost it — visible in the word coordinates:

    line 1   B.                             '11,476,247,28'   x=366
    line 2   EMANET VE REHİNLİ KIYMETLER    4,727,468,981 x=281
                                            6,748,778,307 x=323
                                            '8'           x=397

The row spans two physical lines AND its total is split into two tokens on
different lines. Column-index logic cannot survive that. The geometry can: a
well-formed row on the same page puts current TP at x~285, YP at x~323, Toplam
at x~366, so every fragment has an unambiguous home.

⚠️ The point being tested is the REPRESENTATION, not the model. The previous
bench joined cells with " | ", which discards x entirely — a shifted row and a
clean row look identical after that. Here the page is rendered x-ALIGNED, so a
gap is visible as a gap. If that is what makes the difference, the useful
component is the renderer, and plain code may beat the model on it too.

One API call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.audit_reports import r2_storage  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
CACHE = ROOT / "data" / "_bench"
SCALE = 0.42          # pdf points -> monospace columns

SYSTEM = (
    "You read ONE row from a Turkish bank's BRSA off-balance-sheet statement.\n"
    "The page is given X-ALIGNED: horizontal position is preserved, so figures "
    "in the same column line up vertically down the page. Use that alignment to "
    "decide which column a figure belongs to.\n"
    "Columns, left to right: label, then CURRENT period TP / YP / Toplam, then "
    "PRIOR period TP / YP / Toplam.\n"
    "⚠️ A row may WRAP onto two lines, and a single figure may be SPLIT across "
    "them — e.g. '11,476,247,28' on one line with its final '8' on the next, at "
    "the same column position. Rejoin such fragments by column.\n"
    "'.' and ',' are thousands separators. A dash '-' means ZERO.\n"
    'Reply with STRICT JSON only: {"tl": <int>, "fc": <int>, "total": <int>}\n'
    "Report the CURRENT period. Copy what is printed; never compute a figure."
)

SCHEMA = {
    "name": "row", "strict": True,
    "schema": {"type": "object", "properties": {
        "tl": {"type": "number"}, "fc": {"type": "number"},
        "total": {"type": "number"}},
        "required": ["tl", "fc", "total"], "additionalProperties": False}}


def x_aligned(pdf: Path, page_1: int) -> str:
    """The page as monospace text with every token at its true x position."""
    from src.audit_reports.extractor import _fitz_visual_rows

    lines = []
    for row in _fitz_visual_rows(str(pdf), page_1 - 1):
        buf = ""
        for x0, _x1, tok in row:
            col = int(x0 * SCALE)
            if col < len(buf):
                col = len(buf) + 1
            buf += " " * (col - len(buf)) + tok
        if buf.strip():
            lines.append(buf.rstrip())
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="KUVEYT")
    ap.add_argument("--period", default="2025Q1")
    ap.add_argument("--kind", default="unconsolidated")
    ap.add_argument("--label", default="EMANET VE REHİNLİ KIYMETLER (IV+V+VI)")
    ap.add_argument("--hier", default="B.")
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash-0731")
    ap.add_argument("--flat", action="store_true",
                    help="use the ' | ' join instead, to show the difference")
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPEN_ROUTER_API not set — secrets are CI-only."); return 1

    stem = f"{args.bank}_{args.period}_{args.kind}"
    pdf = CACHE / f"{stem}.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        r2_storage.download_to(f"{args.bank.lower()}/{stem}.pdf", pdf)

    from src.audit_reports.extractor import _fitz_visual_rows, _locate_pages
    page = _locate_pages(str(pdf)).get("off_bs")
    if not page:
        print("off-balance page not located"); return 1

    if args.flat:
        rows = []
        for row in _fitz_visual_rows(str(pdf), page - 1):
            cells, prev = [], None
            for x0, x1, tok in row:
                if prev is not None and x0 - prev > 6.0:
                    cells.append(tok)
                elif cells:
                    cells[-1] = f"{cells[-1]} {tok}"
                else:
                    cells.append(tok)
                prev = x1
            if cells:
                rows.append(" | ".join(c.strip() for c in cells))
        rendered = "\n".join(rows)
    else:
        rendered = x_aligned(pdf, page)

    print(f"=== {stem} | off_balance p{page} | {args.model}")
    print(f"representation: {'FLAT (\" | \" join)' if args.flat else 'X-ALIGNED'}"
          f"  ({len(rendered):,} chars)\n")
    print("--- the target row as the model sees it ---")
    keep = [ln for ln in rendered.splitlines()
            if "EMANET" in ln or ln.strip().startswith("B.")]
    for ln in keep[:4]:
        print("   ", ln[:150])

    body = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                f"ROW: {args.hier} {args.label}\n\n--- PAGE ---\n{rendered[:100000]}"},
        ],
        "temperature": 0, "seed": 7, "max_tokens": 2000,
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }
    r = requests.post(f"{BASE}/chat/completions", timeout=300,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json",
                               "HTTP-Referer": "https://carthago.app",
                               "X-Title": "carthago"}, json=body)
    if r.status_code != 200:
        print(f"\nHTTP {r.status_code}: {r.text[:250]}"); return 1
    d = r.json()
    if not d.get("choices"):
        print(f"\nno choices: {json.dumps(d)[:250]}"); return 1
    ch = d["choices"][0]
    try:
        got = json.loads(ch["message"]["content"])
    except (json.JSONDecodeError, TypeError):
        print(f"\nunparseable: {(ch['message']['content'] or '')[:250]}"); return 1

    ov = json.loads((ROOT / "data/audit_overrides.json").read_text(
        encoding="utf-8"))["overrides"]
    want = next(x for x in ov if x["bank_ticker"] == args.bank
                and x["period"] == args.period and x.get("hierarchy") == args.hier
                and x.get("statement") == "off_balance")

    u = d.get("usage") or {}
    print(f"\ntokens: {u.get('prompt_tokens', 0):,} in / "
          f"{u.get('completion_tokens', 0):,} out\n")
    print(f"{'':8s} {'human (correct)':>18s} {'model':>18s}   ok")
    print("-" * 56)
    allok = True
    for f, k in (("amount_tl", "tl"), ("amount_fc", "fc"), ("amount_total", "total")):
        w, g = int(want[f]), int(got.get(k) or 0)
        allok &= w == g
        print(f"{k:8s} {w:>18,} {g:>18,}   {'OK' if w == g else '<<'}")
    print("-" * 56)
    print("ALL THREE CORRECT" if allok else "MISMATCH")
    print(f"\nwhat the extractor stored before the fix: {want.get('note', '')[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
