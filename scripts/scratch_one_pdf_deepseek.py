#!/usr/bin/env python3
"""ONE text-based PDF, ONE model, every row checked against what we store.

The aggregates were not answering the question. This does the opposite: a single
page, transcribed in full, printed row by row next to the stored value, so the
failures can be looked at rather than summarised.

Default: AKBNK 2026Q1 unconsolidated, balance-sheet liabilities — 10,005
characters of real text, 49 images that are decoration rather than content, and
47 stored rows that already pass every identity check.

The page is given as COORDINATE-RECONSTRUCTED ROWS, not raw get_text(). That is
the fix the earlier benching never tested: get_text() linearises the table into
orphaned lines, so the model has to guess which figure is the current column.

Costs one API call.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.audit_reports import r2_storage  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
CACHE = ROOT / "data" / "_bench"

SYSTEM = (
    "You transcribe a Turkish bank's BRSA balance sheet from reconstructed table "
    "rows. Each row is: hierarchy marker | label | current TP | current YP | "
    "current Toplam | prior TP | prior YP | prior Toplam. Column counts vary; "
    "the FIRST three figures on a row are the CURRENT period.\n"
    "A dash '-' means ZERO. '.' is the thousands separator: 68.752.573 is "
    "68752573. Parentheses mean negative.\n"
    'Reply with STRICT JSON: {"rows": [{"h": "I.", "name": "MEVDUAT", '
    '"tl": 0, "fc": 0, "total": 0}, ...]}\n'
    "Transcribe EVERY row in order including the final total. Copy what is "
    "printed; never compute."
)

SCHEMA = {
    "name": "statement_rows", "strict": True,
    "schema": {"type": "object", "properties": {"rows": {"type": "array", "items": {
        "type": "object", "properties": {
            "h": {"type": "string"}, "name": {"type": "string"},
            "tl": {"type": "number"}, "fc": {"type": "number"},
            "total": {"type": "number"}},
        "required": ["h", "name", "tl", "fc", "total"],
        "additionalProperties": False}}},
        "required": ["rows"], "additionalProperties": False}}


def table_text(pdf: Path, page_1: int) -> str:
    from src.audit_reports.extractor import _fitz_visual_rows

    out = []
    for row in _fitz_visual_rows(str(pdf), page_1 - 1):
        cells, prev = [], None
        for x0, x1, tok in row:
            if prev is not None and x0 - prev > 6.0:
                cells.append(tok)
            elif cells:
                cells[-1] = f"{cells[-1]} {tok}"
            else:
                cells.append(tok)
            prev = x1
        line = " | ".join(c.strip() for c in cells if c.strip())
        if line:
            out.append(line)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="AKBNK")
    ap.add_argument("--period", default="2026Q1")
    ap.add_argument("--kind", default="unconsolidated")
    ap.add_argument("--statement", default="liabilities",
                    choices=["assets", "liabilities"])
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash-0731")
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPEN_ROUTER_API not set — secrets are CI-only."); return 1

    stem = f"{args.bank}_{args.period}_{args.kind}"
    pdf = CACHE / f"{stem}.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        r2_storage.download_to(
            f"{args.bank.lower()}/{stem}.pdf", pdf)

    from src.audit_reports.extractor import _locate_pages
    loc = _locate_pages(str(pdf))
    page = loc.get("bs_assets") if args.statement == "assets" else loc.get("bs_liab")
    if not page:
        print(f"could not locate {args.statement} ({loc})"); return 1

    tbl = table_text(pdf, page)
    print(f"=== {stem} | {args.statement} | page {page} | model {args.model}")
    print(f"reconstructed table: {len(tbl.splitlines())} rows, {len(tbl):,} chars\n")
    print("--- first 6 reconstructed rows, as the model sees them ---")
    for ln in tbl.splitlines()[:6]:
        print("   ", ln[:120])

    body = {
        "model": args.model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": tbl[:120000]}],
        "temperature": 0, "seed": 7, "max_tokens": 16000,
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }
    r = requests.post(f"{BASE}/chat/completions", timeout=600,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json",
                               "HTTP-Referer": "https://carthago.app",
                               "X-Title": "carthago"}, json=body)
    if r.status_code != 200:
        print(f"\nHTTP {r.status_code}: {r.text[:300]}"); return 1
    d = r.json()
    if not d.get("choices"):
        print(f"\nno choices: {json.dumps(d)[:300]}"); return 1
    ch = d["choices"][0]
    usage = d.get("usage") or {}
    try:
        got = json.loads(ch["message"]["content"]).get("rows", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        print(f"\nunparseable (finish={ch.get('finish_reason')}): "
              f"{(ch['message']['content'] or '')[:300]}")
        return 1

    db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    stored = db.execute(
        "SELECT item_order, hierarchy, item_name, amount_tl, amount_fc, amount_total "
        "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? AND kind=? "
        "AND statement=? ORDER BY item_order",
        (args.bank, args.period, args.kind, args.statement)).fetchall()
    db.close()

    print(f"\nmodel returned {len(got)} rows; stored has {len(stored)}")
    print(f"tokens: {usage.get('prompt_tokens', 0):,} in / "
          f"{usage.get('completion_tokens', 0):,} out\n")

    print(f"{'#':>3} {'hier':8s} {'stored name':32s} {'stored total':>16s} "
          f"{'model total':>16s}  ok")
    print("-" * 92)
    ok = bad = 0
    for i, s in enumerate(stored):
        g = got[i] if i < len(got) else {}
        s_tot = int(s[5] or 0)
        g_tot = int(g.get("total") or 0)
        good = s_tot == g_tot
        ok += good
        bad += not good
        mark = "OK" if good else "<<"
        print(f"{i:>3} {str(s[1] or '')[:8]:8s} {str(s[2] or '')[:32]:32s} "
              f"{s_tot:>16,} {g_tot:>16,}  {mark}")
    print("-" * 92)
    print(f"exact on TOTAL column: {ok}/{len(stored)}   wrong: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
