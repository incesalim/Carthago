#!/usr/bin/env python3
"""Scratch bench: can an LLM read a filing's REPORTING UNIT as well as a regex?

2026Q2 is the quarter every Turkish bank switched its audit report from "bin
Türk Lirası" to "milyon Türk Lirası". Nothing in the extractor knows what a
reporting unit is, so the printed figures land 1000x small, and no validator
can see it — every BS/P&L check is an internal identity, and a uniform scale
change leaves all of them footing. See docs/PROJECT_STATE.md.

So the unit has to be READ off the filing. This benches the two ways of doing
that against each other on real filings:

  baseline   one regex over the first pages          (free, offline)
  candidate  an LLM classifying the same text        (paid, needs the network)

The model is asked for a LABEL from a closed set — THOUSAND / MILLION / BILLION
/ UNKNOWN — and never for a figure. That is deliberate: AGENTS.md's "no LLM sets
a number" is not negotiable, and unit detection is a classification, which is
the one shape of this problem an LLM is allowed to touch. Whatever wins here,
the amounts themselves stay deterministic.

Read-only: pulls PDFs from R2, writes nothing to R2, D1 or the local snapshot.

Scratch by design — delete it once the finding is written down.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.audit_reports import r2_storage  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
HEADERS_EXTRA = {"HTTP-Referer": "https://carthago.app", "X-Title": "carthago"}

# The corpus: the quarter of the switch, and the quarter before it as a control.
# Both bases where the bank files them. Q1 is the control precisely because a
# detector that answers MILLION to everything would still score 100% on Q2.
BANKS = ["AKBNK", "GARAN", "YKBNK", "KLNMA", "ENPARA", "TEB"]
PERIODS = ["2026Q1", "2026Q2"]
KINDS = ["unconsolidated", "consolidated"]

FRONT_PAGES = 8  # the declaration sits on p3-p5 in every filing seen so far
CHARS_PER_PAGE = 2200

# ---------------------------------------------------------------------------
# Baseline: the deterministic detector
# ---------------------------------------------------------------------------
UNIT_RE = re.compile(
    r"(bin|milyon|milyar|thousand|million|billion)s?\s+"
    r"(?:of\s+)?(?:t[uü]rk\s+liras[iı]|turkish\s+lira)",
    re.I,
)
_NORM = {
    "bin": "THOUSAND", "thousand": "THOUSAND",
    "milyon": "MILLION", "million": "MILLION",
    "milyar": "BILLION", "billion": "BILLION",
}


def regex_unit(pages: list[str]) -> str:
    for txt in pages:
        m = UNIT_RE.search(txt)
        if m:
            return _NORM[m.group(1).lower()]
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Candidate: the LLM
# ---------------------------------------------------------------------------
SYSTEM = (
    "You read the front matter of a Turkish bank's BRSA audit report and report "
    "the MONETARY UNIT the financial statements are presented in.\n"
    "The filing states this explicitly, in Turkish (e.g. 'aksi belirtilmediği "
    "müddetçe bin Türk Lirası cinsinden hazırlanmıştır') or in English (e.g. "
    "'unless stated otherwise, presented in thousands of Turkish Lira').\n"
    "Answer with STRICT JSON and nothing else:\n"
    '  {"unit": "THOUSAND"|"MILLION"|"BILLION"|"UNKNOWN", "evidence": "<the '
    'exact phrase you read it from, verbatim, max 120 chars>"}\n'
    "Use UNKNOWN if the text does not state it. Never guess from the size of any "
    "number, and never report a number."
)

VALID = {"THOUSAND", "MILLION", "BILLION", "UNKNOWN"}


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
            **HEADERS_EXTRA}


def pick_model(key: str, wanted: str) -> str:
    """Resolve the model id from /models. Never hardcoded — OpenRouter renames
    and retires ids often enough that a literal here becomes a future 404."""
    r = requests.get(f"{BASE}/models", headers=_auth(key), timeout=30)
    r.raise_for_status()
    models = r.json()["data"]
    ids = {m["id"] for m in models}

    if wanted and wanted in ids:
        return wanted
    if wanted:
        near = sorted(i for i in ids if wanted.lower() in i.lower())
        raise SystemExit(
            f"model {wanted!r} not visible on this key."
            + (f" Closest: {near[:8]}" if near else "")
        )

    # Default: the cheapest deepseek "flash" if present, else cheapest deepseek.
    def price(m: dict) -> float:
        return float((m.get("pricing") or {}).get("prompt") or 0)

    ds = sorted((m for m in models if m["id"].startswith("deepseek/")), key=price)
    flash = [m for m in ds if "flash" in m["id"]]
    if flash:
        return flash[0]["id"]
    if ds:
        return ds[0]["id"]
    raise SystemExit("no deepseek model visible on this key")


def list_free(key: str) -> None:
    """Which :free models does this key actually see? The DeepSeek eval found
    none for deepseek/*; nemotron is the open question this answers."""
    r = requests.get(f"{BASE}/models", headers=_auth(key), timeout=30)
    r.raise_for_status()
    models = r.json()["data"]
    free = sorted(m["id"] for m in models if m["id"].endswith(":free"))
    print(f"== :free models visible: {len(free)} ==")
    for i in free:
        print(f"   {i}")
    nem = sorted(m["id"] for m in models if "nemotron" in m["id"].lower())
    print(f"\n== nemotron models visible: {len(nem)} ==")
    for i in nem:
        m = next(x for x in models if x["id"] == i)
        p = m.get("pricing") or {}
        pin = float(p.get("prompt") or 0) * 1e6
        pout = float(p.get("completion") or 0) * 1e6
        tag = "FREE" if i.endswith(":free") else f"${pin:.3f}/${pout:.3f} per Mtok"
        print(f"   {i:<58} {tag}")


def classify(key: str, model: str, text: str, provider: str = "") -> tuple[str, str, dict]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }
    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": False}

    r = requests.post(f"{BASE}/chat/completions", headers=_auth(key),
                      json=body, timeout=120)
    if r.status_code != 200:
        return "HTTP_ERROR", f"{r.status_code}: {r.text[:160]}", {}
    d = r.json()
    content = (d["choices"][0]["message"]["content"] or "").strip()
    usage = d.get("usage") or {}
    try:
        parsed = json.loads(content)
        unit = str(parsed.get("unit", "")).upper()
        ev = str(parsed.get("evidence", ""))[:120]
    except (json.JSONDecodeError, AttributeError):
        return "UNPARSEABLE", content[:120], usage
    return (unit if unit in VALID else f"INVALID:{unit}"), ev, usage


# ---------------------------------------------------------------------------


def front_text(pdf_bytes: bytes) -> list[str]:
    import fitz

    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        return [doc[i].get_text()[:CHARS_PER_PAGE]
                for i in range(min(FRONT_PAGES, doc.page_count))]
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="pin a model id (default: cheapest deepseek flash)")
    ap.add_argument("--provider", default="", help="pin the OpenRouter upstream")
    ap.add_argument("--list-free", action="store_true", help="list :free + nemotron models, then exit")
    ap.add_argument("--baseline-only", action="store_true", help="run the regex only — spends nothing")
    args = ap.parse_args()

    key = os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    if not key and not args.baseline_only:
        print("OPEN_ROUTER_API not set — secrets are CI-only. Run via test-openrouter.yml.")
        return 1

    if args.list_free:
        list_free(key)
        return 0

    model = "" if args.baseline_only else pick_model(key, args.model)
    if model:
        print(f"model: {model}" + (f"  provider={args.provider}" if args.provider else ""))
    print(f"corpus: {len(BANKS)} banks x {PERIODS} x {KINDS}\n")

    rows = []
    for ticker in BANKS:
        for period in PERIODS:
            for kind in KINDS:
                r2key = f"{ticker.lower()}/{ticker}_{period}_{kind}.pdf"
                if not r2_storage.exists(r2key):
                    continue
                dest = Path("data/_bench") / f"{ticker}_{period}_{kind}.pdf"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    r2_storage.download_to(r2key, dest)
                pages = front_text(dest.read_bytes())
                truth = regex_unit(pages)

                llm, ev, usage, dt = "-", "", {}, 0.0
                if not args.baseline_only:
                    t0 = time.time()
                    llm, ev, usage = classify(key, model, "\n\n".join(pages), args.provider)
                    dt = time.time() - t0

                rows.append({
                    "bank": ticker, "period": period, "kind": kind,
                    "regex": truth, "llm": llm, "evidence": ev,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "seconds": round(dt, 2),
                })
                mark = "" if args.baseline_only else ("  OK" if llm == truth else "  <-- DISAGREE")
                print(f"  {ticker:7s} {period} {kind:15s} regex={truth:9s} llm={llm:9s}"
                      f" {dt:5.1f}s{mark}")

    print(f"\n== {len(rows)} filings ==")
    by_unit: dict[str, int] = {}
    for r in rows:
        by_unit[f"{r['period']} {r['regex']}"] = by_unit.get(f"{r['period']} {r['regex']}", 0) + 1
    for k in sorted(by_unit):
        print(f"  regex: {k:20s} {by_unit[k]}")

    if not args.baseline_only:
        agree = sum(1 for r in rows if r["llm"] == r["regex"])
        pin = sum(r["prompt_tokens"] for r in rows)
        pout = sum(r["completion_tokens"] for r in rows)
        print(f"\n  agreement: {agree}/{len(rows)}")
        for r in rows:
            if r["llm"] != r["regex"]:
                print(f"    DISAGREE {r['bank']} {r['period']} {r['kind']}: "
                      f"regex={r['regex']} llm={r['llm']} ev={r['evidence']!r}")
        print(f"  tokens: {pin:,} in / {pout:,} out")
        print(f"  median latency: "
              f"{sorted(r['seconds'] for r in rows)[len(rows) // 2]:.1f}s")

    out = Path("bench_unit_detection.json")
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
