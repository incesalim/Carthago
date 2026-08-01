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
    'exact phrase you read it from, verbatim, max 60 chars>"}\n'
    "Answer immediately. Do not reason at length — the answer is a phrase you "
    "either find in the text or do not.\n"
    "Use UNKNOWN if the text does not state it. Never guess from the size of any "
    "number, and never report a number."
)

VALID = {"THOUSAND", "MILLION", "BILLION", "UNKNOWN"}

# The JSON Schema for strict structured outputs. The free nemotron endpoint
# advertises `structured_outputs`, so the unit can be constrained to an enum
# rather than requested politely — which is exactly the failure being fixed.
UNIT_SCHEMA = {
    "name": "reporting_unit",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "unit": {"type": "string", "enum": sorted(VALID)},
            "evidence": {"type": "string"},
        },
        "required": ["unit", "evidence"],
        "additionalProperties": False,
    },
}

# Variants under test. Nemotron 3 Super gates its chain-of-thought on a /think
# vs /no_think system directive, and OpenRouter exposes reasoning_effort on top;
# the baseline failure was CoT spilling into `content` until max_tokens ran out,
# so each lever here attacks that from a different side.
VARIANTS: dict[str, dict] = {
    "v0_baseline":      {},
    "v1_schema":        {"schema": True},
    "v2_nothink":       {"nothink": True},
    "v3_effort_none":   {"effort": "none"},
    "v4_schema_nothink": {"schema": True, "nothink": True},
    "v5_all":           {"schema": True, "nothink": True, "effort": "none"},
    # effort=none was the one lever that mattered; these isolate it. v6 pairs it
    # with the schema (no /no_think), v7 is a bare repeat to check the 22/22 is
    # stable rather than a lucky seed.
    "v6_schema_effort": {"schema": True, "effort": "none"},
    "v7_effort_repeat": {"effort": "none"},
}


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


def classify(key: str, model: str, text: str, provider: str = "",
             cfg: dict | None = None) -> tuple[str, str, dict]:
    cfg = cfg or {}
    system = SYSTEM
    if cfg.get("nothink"):
        # Nemotron 3 Super gates chain-of-thought on this directive. The bench's
        # whole failure mode was CoT written into `content`, so turning it off at
        # the source beats trying to out-budget it with max_tokens.
        system = "/no_think\n" + system

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "seed": 7,
        # Generous, because reasoning models bill and BUDGET their thinking as
        # output: at max_tokens=200 deepseek-v4-flash spent the whole allowance
        # reasoning and the JSON came back truncated mid-string, which scored as
        # a wrong answer when it was a harness bug. finish_reason is surfaced
        # below so a future truncation is never mistaken for a bad model again.
        "max_tokens": 1200,
    }

    if cfg.get("schema"):
        body["response_format"] = {"type": "json_schema", "json_schema": UNIT_SCHEMA}
        # Fail loudly rather than silently routing to an endpoint that ignores
        # the schema — a soft fallback would make this variant unmeasurable.
        body["provider"] = {"require_parameters": True}
    else:
        body["response_format"] = {"type": "json_object"}

    if cfg.get("effort"):
        body["reasoning"] = {"effort": cfg["effort"]}

    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": False}

    for attempt in range(4):
        r = requests.post(f"{BASE}/chat/completions", headers=_auth(key),
                          json=body, timeout=120)
        if r.status_code == 429:  # free endpoints are rate-limited
            time.sleep(5 * (attempt + 1))
            continue
        break
    if r.status_code != 200:
        return "HTTP_ERROR", f"{r.status_code}: {r.text[:160]}", {}
    d = r.json()
    # A 200 with no `choices` is real: OpenRouter returns an error object in the
    # body when an upstream rejects a parameter combination. Surfacing it as a
    # scored result beats crashing the whole sweep on one bad variant.
    if not d.get("choices"):
        err = (d.get("error") or {}).get("message") or json.dumps(d)[:160]
        return "NO_CHOICES", err[:160], {}
    choice = d["choices"][0]
    content = (choice["message"]["content"] or "").strip()
    usage = dict(d.get("usage") or {})
    usage["finish_reason"] = choice.get("finish_reason")
    try:
        parsed = json.loads(content)
        unit = str(parsed.get("unit", "")).upper()
        ev = str(parsed.get("evidence", ""))[:120]
    except (json.JSONDecodeError, AttributeError):
        # Distinguish "ran out of room" from "returned nonsense" — they mean
        # very different things about the model.
        why = "TRUNCATED" if choice.get("finish_reason") == "length" else "UNPARSEABLE"
        return why, content[:120], usage
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


def load_corpus() -> list[dict]:
    """Every filing we hold, with the deterministic answer attached."""
    out = []
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
                out.append({
                    "bank": ticker, "period": period, "kind": kind,
                    "text": "\n\n".join(pages), "truth": regex_unit(pages),
                })
    return out


def sweep(key: str, model: str, names: list[str], provider: str) -> int:
    """Run the corpus through each variant and compare.

    Scores two things separately, because the baseline failure was never a
    reading failure: `correct` is the returned label matching the regex;
    `comprehended` is the model having quoted the right unit word in its
    evidence even when the label came back empty or truncated. The gap between
    them is the part prompt/schema work can actually close.
    """
    corpus = load_corpus()
    print(f"{len(corpus)} filings · {len(names)} variant(s)\n")
    summary, detail = [], []

    for name in names:
        cfg = VARIANTS[name]
        correct = comprehended = 0
        modes: dict[str, int] = {}
        tin = tout = 0
        lat: list[float] = []
        for item in corpus:
            t0 = time.time()
            unit, ev, usage = classify(key, model, item["text"], provider, cfg)
            dt = time.time() - t0
            lat.append(dt)
            tin += usage.get("prompt_tokens", 0) or 0
            tout += usage.get("completion_tokens", 0) or 0

            ok = unit == item["truth"]
            correct += ok
            # Did it READ the filing right, whatever it then returned?
            want = {"THOUSAND": ("bin", "thousand"), "MILLION": ("milyon", "million"),
                    "BILLION": ("milyar", "billion")}.get(item["truth"], ())
            saw = any(w in (ev or "").lower() for w in want)
            comprehended += ok or saw
            if not ok:
                modes[unit] = modes.get(unit, 0) + 1
                detail.append({"variant": name, **{k: item[k] for k in
                               ("bank", "period", "kind", "truth")},
                               "got": unit, "evidence": ev})

        n = len(corpus)
        summary.append({
            "variant": name, "config": cfg, "correct": correct, "n": n,
            "comprehended": comprehended,
            "failure_modes": modes,
            "tokens_in": tin, "tokens_out": tout,
            "median_s": round(sorted(lat)[n // 2], 1),
        })
        print(f"  {name:20s} {correct:2d}/{n}  read-ok {comprehended:2d}/{n}  "
              f"out={tout:6,d}tok  {sorted(lat)[n // 2]:5.1f}s  "
              f"{modes if modes else ''}")

    print(f"\n{'variant':20s} {'score':>7s} {'read-ok':>8s} {'out tok':>9s} {'med s':>6s}")
    print("-" * 55)
    for s in sorted(summary, key=lambda x: -x["correct"]):
        print(f"{s['variant']:20s} {s['correct']:3d}/{s['n']:<3d} "
              f"{s['comprehended']:4d}/{s['n']:<3d} {s['tokens_out']:9,d} {s['median_s']:6.1f}")
    print(f"{'regex (baseline)':20s} {len(corpus):3d}/{len(corpus):<3d} "
          f"{len(corpus):4d}/{len(corpus):<3d} {0:9,d} {0.0:6.1f}")

    if detail:
        print("\n== misses ==")
        for d in detail[:40]:
            print(f"  {d['variant']:20s} {d['bank']:7s} {d['period']} {d['kind'][:5]:5s} "
                  f"want={d['truth']:8s} got={d['got']:12s} ev={(d['evidence'] or '')[:70]!r}")

    Path("bench_unit_detection.json").write_text(
        json.dumps({"summary": summary, "misses": detail}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print("\nwrote bench_unit_detection.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="pin a model id (default: cheapest deepseek flash)")
    ap.add_argument("--provider", default="", help="pin the OpenRouter upstream")
    ap.add_argument("--list-free", action="store_true", help="list :free + nemotron models, then exit")
    ap.add_argument("--baseline-only", action="store_true", help="run the regex only — spends nothing")
    ap.add_argument("--variants", default="",
                    help=f"comma-separated variants to sweep: {','.join(VARIANTS)}")
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

    if args.variants:
        names = [v.strip() for v in args.variants.split(",") if v.strip()]
        unknown = [v for v in names if v not in VARIANTS]
        if unknown:
            raise SystemExit(f"unknown variant(s) {unknown}; have {list(VARIANTS)}")
        return sweep(key, model, names, args.provider)

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
