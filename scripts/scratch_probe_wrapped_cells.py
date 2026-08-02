#!/usr/bin/env python3
"""How many hand corrections are the WRAPPED-CELL shape?

KUVEYT 2025Q1 off-balance `B.` needed a hand fix because 11,476,247,288 is
word-wrapped inside its table cell — it does not fit the column width, so the
final `8` drops to a second line within the same cell. `get_text()` emits two
tokens and discards the cell border, so the anchors read the truncated token and
re-group its digits into 1,147,624,728. A text LLM makes the identical mistake,
with or without x-positions preserved: position is not cell membership.

That failure is deterministically detectable, so the question is how much of the
457-override backlog it accounts for. If it is a large share, the fix is one
parser change rather than a new lane.

Signature: the corrected value's digits appear on the page as a PREFIX token
plus the remaining digits in a nearby token, while the full value appears
nowhere. Purely local, no API.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

CACHE = ROOT / "data" / "_bench"

# Statement lanes: the page comes from the locator. Field lanes carry source_page.
STMT_PAGE_KEY = {
    "assets": "bs_assets", "liabilities": "bs_liab",
    "off_balance": "off_bs", "profit_loss": "pl",
}
FIELD_TABLE = {
    "capital": "bank_audit_capital", "liquidity": "bank_audit_liquidity",
    "npl_movement": "bank_audit_npl_movement",
    "fx_position": "bank_audit_fx_position",
    "credit_quality": "bank_audit_credit_quality",
    "repricing": "bank_audit_repricing",
}


def digits(v: float) -> str:
    return str(abs(int(round(v))))


def formatted(v: float) -> list[str]:
    n = abs(int(round(v)))
    s = f"{n:,}"
    return [s, s.replace(",", "."), str(n)]


def classify(page, value: float) -> str:
    """exact | WRAPPED | absent, for one value on one page."""
    words = page.get_text("words")           # (x0,y0,x1,y1, text, ...)
    toks = [w[4] for w in words]
    text = " ".join(toks)
    if any(f in text for f in formatted(value)):
        return "exact"

    want = digits(value)
    if len(want) < 6:
        return "absent"                      # too short to judge safely
    for i, t in enumerate(toks):
        d = re.sub(r"\D", "", t)
        # a genuine prefix, missing at least one digit but most of them present
        if not d or len(d) >= len(want) or not want.startswith(d):
            continue
        if len(d) < len(want) - 3:
            continue
        rest = want[len(d):]
        # the remainder must appear in a token close by in reading order
        for j in range(i + 1, min(i + 6, len(toks))):
            if re.sub(r"\D", "", toks[j]) == rest:
                return "WRAPPED"
    return "absent"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = every cached filing")
    args = ap.parse_args()

    import sqlite3
    from src.audit_reports.extractor import _locate_pages

    ov = json.loads(
        (ROOT / "data/audit_overrides.json").read_text(encoding="utf-8"))["overrides"]
    db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    # (bank, period, kind) -> [(statement, value, source_page_or_None), ...]
    todo: dict[tuple, list] = collections.defaultdict(list)
    for x in ov:
        st = x.get("statement")
        key = (x["bank_ticker"], x["period"], x["kind"])
        vals: list[float] = []
        for f in ("amount_total", "amount", "amount_tl", "amount_fc"):
            v = x.get(f)
            if isinstance(v, (int, float)) and v:
                vals.append(float(v))
        if isinstance(x.get("fields"), dict):
            vals += [float(v) for k, v in x["fields"].items()
                     if k != "source_page" and isinstance(v, (int, float)) and v]
        if not vals:
            continue
        page = x.get("source_page") or (x.get("fields") or {}).get("source_page")
        if page is None and st in FIELD_TABLE:
            r = db.execute(
                f"SELECT source_page FROM {FIELD_TABLE[st]} WHERE bank_ticker=? "
                f"AND period=? AND kind=? LIMIT 1", key).fetchone()
            page = r["source_page"] if r else None
        todo[key].append((st, vals, page))
    db.close()

    have = {p.stem for p in CACHE.glob("*.pdf")}
    keys = [k for k in todo if f"{k[0]}_{k[1]}_{k[2]}" in have]
    if args.limit:
        keys = keys[:args.limit]
    print(f"{len(todo)} override partitions, {len(keys)} with a cached PDF\n")

    counts: collections.Counter = collections.Counter()
    by_lane: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    examples: list[str] = []

    for key in keys:
        pdf = CACHE / f"{key[0]}_{key[1]}_{key[2]}.pdf"
        doc = fitz.open(pdf)
        loc = None
        for st, vals, page in todo[key]:
            pno = page
            if pno is None and st in STMT_PAGE_KEY:
                if loc is None:
                    loc = _locate_pages(str(pdf))
                pno = loc.get(STMT_PAGE_KEY[st])
            if not pno or not (1 <= pno <= doc.page_count):
                counts["no page"] += len(vals)
                by_lane[st]["no page"] += len(vals)
                continue
            # the value may sit a page or two past the section anchor
            for v in vals:
                verdict = "absent"
                for off in range(0, 4):
                    p = pno + off
                    if not (1 <= p <= doc.page_count):
                        continue
                    verdict = classify(doc[p - 1], v)
                    if verdict != "absent":
                        break
                counts[verdict] += 1
                by_lane[st][verdict] += 1
                if verdict == "WRAPPED" and len(examples) < 10:
                    examples.append(
                        f"{key[0]} {key[1]} {key[2][:5]} {st}: {int(v):,}")
        doc.close()

    n = sum(counts.values())
    print(f"{'verdict':10s} {'n':>6s}   share")
    print("-" * 32)
    for k in ("WRAPPED", "exact", "absent", "no page"):
        if counts[k]:
            print(f"{k:10s} {counts[k]:6d}   {100.0 * counts[k] / max(1, n):5.1f}%")
    print("-" * 32)
    print(f"{'TOTAL':10s} {n:6d}")

    print(f"\n{'lane':16s} {'WRAPPED':>8s} {'exact':>7s} {'absent':>7s} {'no page':>8s}")
    for lane, c in sorted(by_lane.items(), key=lambda kv: -kv[1]["WRAPPED"]):
        print(f"{lane:16s} {c['WRAPPED']:8d} {c['exact']:7d} {c['absent']:7d} "
              f"{c['no page']:8d}")
    if examples:
        print("\nwrapped-cell examples:")
        for e in examples:
            print("  -", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
