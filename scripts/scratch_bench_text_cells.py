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
# §4 / note lanes: a NAMED metric in a table, not a statement row. Different
# prompt shape, and they carry source_page so retrieval is exact rather than a
# label search — which is the weak link in the statement lanes above.
FIELD_LANES = {
    "capital": ("bank_audit_capital", ["cet1_capital", "tier1_capital",
                "tier2_capital", "total_capital", "total_rwa"]),
    "liquidity": ("bank_audit_liquidity", ["leverage_ratio", "lcr_total",
                  "lcr_fc", "nsfr"]),
    "npl_movement": ("bank_audit_npl_movement", ["opening_balance", "additions",
                     "collections", "closing_balance", "provision"]),
    "fx_position": ("bank_audit_fx_position", ["on_bs_assets", "on_bs_liab",
                    "net_on_balance", "net_off_balance", "net_position"]),
    "credit_quality": ("bank_audit_credit_quality", ["stage1_amount",
                       "stage2_amount", "stage3_amount", "total_amount"]),
    "repricing": ("bank_audit_repricing", ["rate_sensitive_assets",
                  "rate_sensitive_liab", "gap"]),
    "loans_by_sector": ("bank_audit_loans_by_sector", ["stage2_amount",
                        "stage3_amount", "ecl_amount"]),
}

# How many pages to read from source_page, PER LANE. Not a constant: widening
# from 1 to 3 pages took capital 0/5 -> 3/3 and liquidity 0/2 -> 1/1 (those
# tables span pages and source_page marks the section start), but it took
# fx_position 71% -> 55% and loans_by_sector 60% -> 33%. Those lanes repeat the
# same field names down a column of currencies / sectors, so extra pages supply
# more near-identical rows to pick the wrong one from. Wider retrieval is not
# monotonically better; it trades a missing answer for an ambiguous one.
WINDOW_FOR = {
    "capital": 3,
    "liquidity": 3,
    "repricing": 3,
    "credit_quality": 3,
    "fx_position": 1,
    "loans_by_sector": 1,
    "npl_movement": 1,
}

# Human-readable descriptions so the prompt names the quantity the way the
# filing does, not the way our schema does.
FIELD_DESC = {
    "cet1_capital": "Common Equity Tier 1 capital (Çekirdek Ana Sermaye)",
    "tier1_capital": "Tier 1 capital (Ana Sermaye)",
    "tier2_capital": "Tier 2 capital (Katkı Sermaye)",
    "total_capital": "Total capital / own funds (Toplam Özkaynak)",
    "total_rwa": "Total risk-weighted assets (Toplam Risk Ağırlıklı Tutar)",
    "leverage_ratio": "Leverage ratio %  (Kaldıraç Oranı)",
    "lcr_total": "Liquidity coverage ratio, total %  (Likidite Karşılama Oranı)",
    "lcr_fc": "Liquidity coverage ratio, FC %",
    "nsfr": "Net stable funding ratio %",
    "opening_balance": "opening balance (Önceki Dönem Sonu Bakiyesi)",
    "additions": "additions in the period (Dönem İçinde İntikal)",
    "collections": "collections (Tahsilatlar)",
    "closing_balance": "closing balance (Dönem Sonu Bakiyesi)",
    "provision": "provision (Özel Karşılık)",
    "on_bs_assets": "on-balance-sheet foreign currency assets",
    "on_bs_liab": "on-balance-sheet foreign currency liabilities",
    "net_on_balance": "net on-balance-sheet position",
    "net_off_balance": "net off-balance-sheet position",
    "net_position": "net foreign currency position",
    "stage1_amount": "Stage 1 amount", "stage2_amount": "Stage 2 amount",
    "stage3_amount": "Stage 3 amount", "total_amount": "total amount",
    "ecl_amount": "expected credit loss provision",
    "rate_sensitive_assets": "rate-sensitive assets for the bucket",
    "rate_sensitive_liab": "rate-sensitive liabilities for the bucket",
    "gap": "the repricing gap for the bucket",
}

SYSTEM_F = (
    "You read ONE named figure out of a table in a Turkish bank's BRSA audit "
    "report. You are given the page text, the table/row it belongs to, and which "
    "quantity to report.\n"
    "'.' is the thousands separator: 18.333.158 is 18333158. A ratio like "
    "'18,45' uses a comma decimal and is 18.45. A dash '-' means ZERO. "
    "Parentheses mean negative.\n"
    'Reply with STRICT JSON only: {"value": <number>, "found": true|false}\n'
    "⚠️ These tables repeat the SAME field names down a column — one block per "
    "currency (EUR, USD, other), per sector, per maturity bucket, and again for "
    "the prior period. Locate the block named in TABLE / ROW first, then read the "
    "quantity inside THAT block. A figure from the neighbouring block is the most "
    "common way to be wrong here.\n"
    "⚠️ Report the sign as printed. A net position is frequently negative; do not "
    "drop a minus sign and do not add one.\n"
    "Set found=false if it is not on this page. Never compute or infer — copy "
    "what is printed."
)
SCHEMA_F = {
    "name": "named_value", "strict": True,
    "schema": {"type": "object", "properties": {
        "value": {"type": "number"}, "found": {"type": "boolean"}},
        "required": ["value", "found"], "additionalProperties": False}}

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
    "⚠️ The SAME label can appear more than once under different parents. QNBFB "
    "prints 'Non-cash loans' under BOTH fees received (4.1.1 = 175,010) and fees "
    "paid (4.2.1 = 449). The hierarchy marker decides which row is meant — match "
    "it first, and use the label only to confirm.\n"
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
    "⚠️ The SAME label can appear more than once under different parents. QNBFB "
    "prints 'Non-cash loans' under BOTH fees received (4.1.1 = 175,010) and fees "
    "paid (4.2.1 = 449). The hierarchy marker decides which row is meant — match "
    "it first, and use the label only to confirm.\n"
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


def ask(key: str, model: str, page_text: str, label: str, three: bool,
        hier: str = "") -> tuple[dict, str]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_3 if three else SYSTEM_1},
            {"role": "user", "content":
                f"HIERARCHY MARKER: {hier or '(none)'}\nROW LABEL: {label}\n\n"
                f"--- PAGE TEXT ---\n{page_text[:60000]}"},
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
                    "h": x.get("hierarchy") or "",
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
                            "h": r[0] or "",
                            "want": want, "hint": None})
    finally:
        db.close()
    random.Random(seed + 1).shuffle(out)
    return out[:limit]


def _row_key(st: str, r: sqlite3.Row) -> str:
    """How the filing identifies the row: which table, which line."""
    if st == "npl_movement":
        return f"BRSA group {r['group_code']}, {r['period_type']} period"
    if st == "fx_position":
        return f"currency {r['currency']}, {r['period_type']} period"
    if st == "credit_quality":
        return f"section {r['section']}, {r['period_type']} period"
    if st == "repricing":
        return f"repricing bucket {r['bucket']}, {r['period_type']} period"
    if st == "loans_by_sector":
        return f"sector {r['sector']}, {r['period_type']} period"
    return f"{r['period_type']} period"


def build_fields(limit: int, seed: int, lanes: set[str]) -> list[dict]:
    """Named-metric cells from the §4 / note lanes.

    These carry `source_page`, so retrieval is exact — which also isolates the
    model from the label-search weakness that dominates the statement lanes.
    Ground truth is the stored, validated value; overrides are already applied
    to the snapshot, so a match means agreeing with the corrected figure.
    """
    db = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = []
    try:
        for st in sorted(lanes):
            table, fields = FIELD_LANES[st]
            cols = [r[1] for r in db.execute(f"pragma table_info({table})")]
            if "source_page" not in cols:
                continue
            rows = db.execute(
                f"SELECT * FROM {table} WHERE source_page IS NOT NULL "
                f"AND source_page > 0 LIMIT 4000").fetchall()
            for r in rows:
                for f in fields:
                    if f not in cols:
                        continue
                    val = r[f]
                    if val is None or val == 0:
                        continue
                    out.append({
                        "set": "fields", "bank": r["bank_ticker"],
                        "period": r["period"], "kind": r["kind"], "statement": st,
                        "field": f, "label": FIELD_DESC.get(f, f),
                        "where": _row_key(st, r), "want": {"value": val},
                        "hint": r["source_page"],
                    })
    finally:
        db.close()
    random.Random(seed + 2).shuffle(out)
    return out[:limit]


def ask_field(key: str, model: str, page_text: str, what: str,
              where: str) -> tuple[dict, str]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_F},
            {"role": "user", "content":
                f"TABLE / ROW: {where}\nQUANTITY: {what}\n\n"
                f"--- PAGE TEXT ---\n{page_text[:60000]}"},
        ],
        "temperature": 0, "seed": 7, "max_tokens": 3000,
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema", "json_schema": SCHEMA_F},
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


def page_text_at(pdf: Path, page_1: int, window: int = 3) -> str | None:
    """Text of source_page and the pages after it.

    `source_page` marks where the SECTION starts (`rep.source_page = start + 1`
    in capital_adequacy.py), not where the row sits, and these §4 tables span
    pages. VAKBN 2025Q2's capital section starts on p41 while "Toplam Risk
    Ağırlıklı Tutarlar 2,483,897,695" is on p42 — a single-page fetch handed the
    model a page that did not contain the answer at all, which is most of why
    capital scored 0/5.
    """
    import fitz

    doc = fitz.open(pdf)
    try:
        if not (1 <= page_1 <= doc.page_count):
            return None
        parts = []
        for p in range(page_1, min(page_1 + window, doc.page_count + 1)):
            parts.append(f"--- page {p} ---\n{doc[p - 1].get_text()}")
        return "\n".join(parts)
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/nemotron-3-ultra-550b-a55b:free")
    ap.add_argument("--repair", type=int, default=20)
    ap.add_argument("--control", type=int, default=20)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--fields", type=int, default=0,
                    help="also sample N named-metric cells from the §4/note lanes")
    ap.add_argument("--field-lanes", default=",".join(FIELD_LANES))
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPEN_ROUTER_API not set — secrets are CI-only."); return 1

    repair = build_repair(args.repair, args.seed)
    control = build_control(args.control, args.seed, repair)
    lanes = {x.strip() for x in args.field_lanes.split(",") if x.strip()}
    fields = build_fields(args.fields, args.seed, lanes & set(FIELD_LANES))         if args.fields else []
    print(f"model: {args.model}")
    print(f"repair set: {len(repair)}  control set: {len(control)}  "
          f"(balance sheet excluded by design)\n")

    results = []
    for item in repair + control + fields:
        tag = (f"{item['set']:7s} {item['bank']:7s} {item['period']} "
               f"{item['kind'][:5]:5s} {item['statement']:12s}")
        pdf = pdf_for(item["bank"], item["period"], item["kind"])
        if not pdf:
            print(f"  {tag} PDF missing"); continue

        if item["set"] == "fields":
            text = page_text_at(pdf, item["hint"],
                                WINDOW_FOR.get(item["statement"], 3))
            if not text:
                print(f"  {tag} source_page {item['hint']} out of range"); continue
            time.sleep(DELAY)
            got, err = ask_field(key, args.model, text, item["label"], item["where"])
            if err:
                print(f"  {tag} p{item['hint']} ERR {err}")
                results.append({**{k: item[k] for k in ('set','bank','period','statement')},
                                "outcome": err}); continue
            want_v = float(item["want"]["value"])
            got_v = float(got.get("value") or 0)
            # Ratios are stored to 2dp; amounts are integers. Compare loosely
            # enough that a rounding difference is not scored as a wrong read.
            ok = bool(got.get("found")) and abs(want_v - got_v) <= max(
                0.01, abs(want_v) * 1e-6)
            print(f"  {tag} {item['field']:22s} p{item['hint']} "
                  f"{'MATCH ' if ok else 'DIFFER'} want={want_v:,.2f} got={got_v:,.2f}"
                  f"{'' if got.get('found') else ' (found=false)'}")
            results.append({**{k: item[k] for k in ('set','bank','period','statement')},
                            "field": item["field"],
                            "outcome": "match" if ok else "differ",
                            "want": want_v, "got": got_v, "page": item["hint"]})
            continue
        hit = find_page(pdf, item["label"], item.get("hint"))
        if not hit:
            print(f"  {tag} label not found on any page: {item['label'][:40]!r}")
            results.append({**{k: item[k] for k in ('set', 'bank', 'period', 'statement')},
                            "outcome": "page_not_found"})
            continue
        page, text = hit

        three = item["statement"] in THREE_COL
        time.sleep(DELAY)
        got, err = ask(key, args.model, text, item["label"], three,
                       item.get("h", ""))
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
    for name in ("repair", "control", "fields"):
        s = [r for r in results if r["set"] == name]
        if not s:
            continue
        m = sum(1 for r in s if r["outcome"] == "match")
        d = sum(1 for r in s if r["outcome"] == "differ")
        other = len(s) - m - d
        print(f"  {name:8s} {m}/{len(s)} match, {d} differ, {other} no-answer "
              f"({100.0 * m / len(s):.0f}%)")
    per_lane: dict[str, list[int]] = {}
    for r in results:
        if r["set"] != "fields":
            continue
        per_lane.setdefault(r["statement"], [0, 0])
        per_lane[r["statement"]][1] += 1
        per_lane[r["statement"]][0] += r["outcome"] == "match"
    if per_lane:
        print("\n  by lane (named metrics):")
        for lane, (m, n) in sorted(per_lane.items()):
            print(f"    {lane:16s} {m}/{n} ({100.0 * m / max(1, n):.0f}%)")
    Path("bench_text_cells.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote bench_text_cells.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
