#!/usr/bin/env python3
"""Scratch bench: can a text LLM recover the cells a human had to correct?

`data/audit_overrides.json` holds 457 hand-made per-cell corrections. 416 of
them are OUTSIDE the balance sheet — off_balance 105, credit_quality 100,
capital 58 — and unlike the hand-transcribed statements, these pages DO have a
text layer. `fitz` read them fine; the anchor logic put the number in the wrong
place. So the model is re-reading text we already have, not doing OCR, which is
a far easier problem than the vision bench and the reason it is worth trying.

Balance-sheet lanes (assets/liabilities) are excluded on purpose: the regex path
is fine there and does not need help.

Two sets, because a repair rate on its own is not interpretable:

  REPAIR   cells the deterministic extractor got WRONG and a human fixed.
           Ground truth = the human's corrected value. This is the bar: succeed
           exactly where the anchors failed.
  CONTROL  cells already stored and validated, no override. Ground truth = the
           stored value. A model that "fixes" 60% of the broken cells while
           quietly breaking the good ones is worse than useless, and only the
           control set can show that.

⚠️ The model is asked for figures, which AGENTS.md forbids in production. This
is a bench: nothing it returns is written to D1, R2 or the local snapshot.
Scratch by design.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.audit_reports import r2_storage  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
HEADERS_EXTRA = {"HTTP-Referer": "https://carthago.app", "X-Title": "carthago"}
ROOT = Path(__file__).resolve().parents[1]
DELAY = float(os.environ.get("BENCH_DELAY", "2"))

# Lanes with an unambiguous (row -> amount) shape. Balance sheet deliberately
# absent: regex is fine there.
THREE_COL = {"off_balance"}                      # amount_tl / amount_fc / amount_total
ONE_COL = {"profit_loss", "cash_flow", "oci"}    # amount
TABLE_FOR = {
    "off_balance": ("bank_audit_balance_sheet", "statement='off_balance'"),
    "profit_loss": ("bank_audit_profit_loss", "1=1"),
    "cash_flow": ("bank_audit_cash_flow", "1=1"),
    "oci": ("bank_audit_oci", "1=1"),
}

SYSTEM_3 = (
    "You read one row out of a Turkish bank's BRSA financial statement page.\n"
    "You are given the page text and a row label. Report that row's three "
    "current-period amounts: TP (Turkish lira), YP (foreign currency), Toplam "
    "(total). Use the CURRENT period columns, not the prior period.\n"
    "A dash '-' means ZERO. '.' is the thousands separator: 4.727.468.981 is "
    "4727468981. Parentheses mean negative.\n"
    'Reply with STRICT JSON only: {"tl": <int>, "fc": <int>, "total": <int>, '
    '"found": true|false}\n'
    "Set found=false if the row is not on this page. Never compute or infer a "
    "figure — copy what is printed."
)
SYSTEM_1 = (
    "You read one row out of a Turkish bank's BRSA financial statement page.\n"
    "You are given the page text and a row label. Report that row's CURRENT "
    "period amount (the first/left amount column), not the prior period.\n"
    "A dash '-' means ZERO. '.' is the thousands separator: 46.257.158 is "
    "46257158. Parentheses mean negative.\n"
    'Reply with STRICT JSON only: {"amount": <int>, "found": true|false}\n'
    "Set found=false if the row is not on this page. Never compute or infer a "
    "figure — copy what is printed."
)

SCHEMA_3 = {
    "name": "row_three", "strict": True,
    "schema": {"type": "object", "properties": {
        "tl": {"type": "number"}, "fc": {"type": "number"},
        "total": {"type": "number"}, "found": {"type": "boolean"}},
        "required": ["tl", "fc", "total", "found"], "additionalProperties": False}}
SCHEMA_1 = {
    "name": "row_one", "strict": True,
    "schema": {"type": "object", "properties": {
        "amount": {"type": "number"}, "found": {"type": "boolean"}},
        "required": ["amount", "found"], "additionalProperties": False}}


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
            **HEADERS_EXTRA}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def find_page(pdf: Path, item_name: str, hint: int | None) -> tuple[int, str] | None:
    """The page whose text best contains this row label.

    A retrieval step, not a guess: the label is printed on the page it belongs
    to. `hint` is the override's own source_page where it recorded one.
    """
    import fitz

    doc = fitz.open(pdf)
    try:
        target = _norm(item_name)[:40]
        if not target:
            return None
        order = ([hint] if hint else []) + [i + 1 for i in range(doc.page_count)]
        best = None
        for p in order:
            if not (1 <= p <= doc.page_count):
                continue
            txt = doc[p - 1].get_text()
            if target and target in _norm(txt):
                return p, txt
            # Fall back to a generous prefix so a wrapped label still matches.
            if best is None and target[:22] and target[:22] in _norm(txt):
                best = (p, txt)
        return best
    finally:
        doc.close()


def ask(key: str, model: str, page_text: str, label: str, three: bool) -> tuple[dict, str]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_3 if three else SYSTEM_1},
            {"role": "user", "content":
                f"ROW LABEL: {label}\n\n--- PAGE TEXT ---\n{page_text[:24000]}"},
        ],
        "temperature": 0, "seed": 7, "max_tokens": 3000,
        # The round-2 finding: reasoning tokens otherwise eat the budget and the
        # JSON comes back truncated, which scores as a wrong answer.
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema",
                            "json_schema": SCHEMA_3 if three else SCHEMA_1},
    }
    for attempt in range(4):
        r = requests.post(f"{BASE}/chat/completions", headers=_auth(key),
                          json=body, timeout=180)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1)); continue
        if "Upstream idle timeout" in r.text:
            time.sleep(5 * (attempt + 1)); continue
        break
    if r.status_code != 200:
        return {}, f"HTTP {r.status_code}"
    d = r.json()
    if not d.get("choices"):
        return {}, f"NO_CHOICES {json.dumps(d)[:120]}"
    ch = d["choices"][0]
    try:
        return json.loads((ch["message"]["content"] or "").strip()), ""
    except (json.JSONDecodeError, AttributeError):
        return {}, ("TRUNCATED" if ch.get("finish_reason") == "length" else "UNPARSEABLE")


def pdf_for(bank: str, period: str, kind: str) -> Path | None:
    key = f"{bank.lower()}/{bank}_{period}_{kind}.pdf"
    dest = Path("data/_bench") / f"{bank}_{period}_{kind}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    if not r2_storage.exists(key):
        return None
    r2_storage.download_to(key, dest)
    return dest


def build_repair(limit: int, seed: int) -> list[dict]:
    ov = json.loads(
        (ROOT / "data/audit_overrides.json").read_text(encoding="utf-8"))["overrides"]
    out = []
    for x in ov:
        st = x.get("statement")
        if st not in THREE_COL and st not in ONE_COL:
            continue
        if not x.get("item_name"):
            continue
        if st in THREE_COL:
            if x.get("amount_total") is None:
                continue
            want = {"tl": x.get("amount_tl"), "fc": x.get("amount_fc"),
                    "total": x.get("amount_total")}
        else:
            if x.get("amount") is None:
                continue
            want = {"amount": x.get("amount")}
        out.append({"set": "repair", "bank": x["bank_ticker"], "period": x["period"],
                    "kind": x["kind"], "statement": st, "label": x["item_name"],
                    "want": want, "hint": x.get("source_page")})
    random.Random(seed).shuffle(out)
    return out[:limit]


def build_control(limit: int, seed: int, repair: list[dict]) -> list[dict]:
    """Stored, validated cells with no override — the 'does it break what
    already works' half. Drawn from the same partitions as the repair set so the
    two are comparable."""
    db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    parts = {(r["bank"], r["period"], r["kind"], r["statement"]) for r in repair}
    banned = {(r["bank"], r["period"], r["kind"], _norm(r["label"])) for r in repair}
    out = []
    try:
        for bank, period, kind, st in parts:
            table, where = TABLE_FOR[st]
            cols = ("hierarchy,item_name,amount_tl,amount_fc,amount_total"
                    if st in THREE_COL else "hierarchy,item_name,amount")
            rows = db.execute(
                f"SELECT {cols} FROM {table} WHERE bank_ticker=? AND period=? "
                f"AND kind=? AND {where} AND item_name<>'' "
                f"AND COALESCE(amount{'_total' if st in THREE_COL else ''},0)<>0",
                (bank, period, kind)).fetchall()
            for r in rows:
                if (bank, period, kind, _norm(r[1])) in banned:
                    continue
                want = ({"tl": r[2], "fc": r[3], "total": r[4]} if st in THREE_COL
                        else {"amount": r[2]})
                out.append({"set": "control", "bank": bank, "period": period,
                            "kind": kind, "statement": st, "label": r[1],
                            "want": want, "hint": None})
    finally:
        db.close()
    random.Random(seed + 1).shuffle(out)
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/nemotron-3-ultra-550b-a55b:free")
    ap.add_argument("--repair", type=int, default=20)
    ap.add_argument("--control", type=int, default=20)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPEN_ROUTER_API not set — secrets are CI-only."); return 1

    repair = build_repair(args.repair, args.seed)
    control = build_control(args.control, args.seed, repair)
    print(f"model: {args.model}")
    print(f"repair set: {len(repair)}  control set: {len(control)}  "
          f"(balance sheet excluded by design)\n")

    results = []
    for item in repair + control:
        tag = (f"{item['set']:7s} {item['bank']:7s} {item['period']} "
               f"{item['kind'][:5]:5s} {item['statement']:12s}")
        pdf = pdf_for(item["bank"], item["period"], item["kind"])
        if not pdf:
            print(f"  {tag} PDF missing"); continue
        hit = find_page(pdf, item["label"], item.get("hint"))
        if not hit:
            print(f"  {tag} label not found on any page: {item['label'][:40]!r}")
            results.append({**{k: item[k] for k in ('set', 'bank', 'period', 'statement')},
                            "outcome": "page_not_found"})
            continue
        page, text = hit

        three = item["statement"] in THREE_COL
        time.sleep(DELAY)
        got, err = ask(key, args.model, text, item["label"], three)
        if err:
            print(f"  {tag} p{page} ERR {err}")
            results.append({**{k: item[k] for k in ('set', 'bank', 'period', 'statement')},
                            "outcome": err})
            continue

        want = item["want"]
        keys = ("tl", "fc", "total") if three else ("amount",)
        ok = bool(got.get("found")) and all(
            int(want.get(k) or 0) == int(got.get(k) or 0) for k in keys)
        w = "/".join(str(int(want.get(k) or 0)) for k in keys)
        g = "/".join(str(int(got.get(k) or 0)) for k in keys)
        print(f"  {tag} p{page} {'MATCH ' if ok else 'DIFFER'} want={w} got={g}"
              f"{'' if got.get('found') else ' (found=false)'}")
        results.append({**{k: item[k] for k in ('set', 'bank', 'period', 'statement')},
                        "outcome": "match" if ok else "differ",
                        "want": w, "got": g, "page": page})

    print()
    for name in ("repair", "control"):
        s = [r for r in results if r["set"] == name]
        if not s:
            continue
        m = sum(1 for r in s if r["outcome"] == "match")
        d = sum(1 for r in s if r["outcome"] == "differ")
        other = len(s) - m - d
        print(f"  {name:8s} {m}/{len(s)} match, {d} differ, {other} no-answer "
              f"({100.0 * m / len(s):.0f}%)")
    Path("bench_text_cells.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote bench_text_cells.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
