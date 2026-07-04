"""THROWAWAY reliability gauntlet — free LLM providers (Groq + Cerebras only;
Gemini dropped, not free for us) on "The Read" headline rewrite.

Goal: measure the DOWNSIDE, not the vibe. Each finalist model rewrites every Read
(8 real + 3 number-traps) REPEATEDLY at ship temperature (0.0), and we score:
  - invented-number rate  ← the headline metric = expected fallback rate
  - format / length adherence (30-45 words, no preamble/markdown/multi-sentence)
  - run-to-run stability at fixed temperature
  - latency, tokens, empty/failure rate

Writes free_model_gauntlet.md (readable scorecard + trap outputs + failure log) and
free_model_gauntlet.json. Keys from secrets: GROQ_API_KEY / CEREBRAS_API_KEY.
Not wired into the dashboard. Delete once a model is chosen.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OUT_MD = ROOT / "free_model_gauntlet.md"
OUT_JSON = ROOT / "free_model_gauntlet.json"

REPEATS = 3
TEMPERATURE = 0.0


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# ===========================================================================
# Task + prompt
# ===========================================================================
SYSTEM = (
    "You write the one-sentence editorial lead ('The Read') for a Turkish "
    "banking-sector dashboard, in the terse, analytical voice of BBVA Research. "
    "You are given the deterministic facts and the current template lead. "
    "Rewrite it as ONE flowing sentence (about 30-45 words) that SYNTHESIZES the "
    "vitals into a 'so what' — connect them causally where the facts support it "
    "(e.g. funding repricing lifting margins). Do NOT merely list every number; "
    "pick the 2-3 threads that tell the story. HARD RULE: use ONLY numbers that "
    "appear in the facts. Never invent, round, or compute a new figure. Output "
    "ONLY the sentence — no preamble, no markdown, no reasoning."
)

# key, tab, asOf, facts (the ONLY allowed numbers), headline (template), drivers.
# `trap=True` scenarios deliberately omit a temptingly-derivable/roundable figure
# so we can see which models invent it.
SCENARIOS: list[dict] = [
    {"key": "overview", "tab": "Overview", "asOf": "2026-05", "facts": {
        "assets_yoy": 38.5, "loans_yoy": 42.1, "deposits_yoy": 36.0, "npl": 1.81,
        "npl_delta_pp": 0.04, "car": 18.1, "car_min": 12, "car_buffer_pp": 6.1,
        "roe": 34.2, "ldr": 88, "nim": 4.35, "nim_delta_pp": 0.07},
     "headline": "As of 2026-05: the sector is growing (assets +38.5% y/y) and profitable (ROE 34.2%), with NPL at 1.81% and capital comfortably above the minimum at 18.1%.",
     "drivers": ["assets +38.5% y/y, loans +42.1%, deposits +36.0%", "NPL 1.81% (+0.04pp)",
                 "CAR 18.1% — 6.1pp over the 12% min", "ROE 34.2%; NIM 4.35% (+0.07pp)", "LDR 88%"]},

    {"key": "credit", "tab": "Credit", "asOf": "2026-05", "facts": {
        "loans_yoy": 42.1, "mom4": 38.0, "state_yoy": 47.5, "private_yoy": 36.8,
        "state_private_gap_pp": 10.7, "fx_share": 22.4, "fx_share_delta_pp": 0.8,
        "cards_yoy": 55.0, "sme_yoy": 33.0},
     "headline": "Credit is growing 42.1% y/y and steady, led by state banks; FX share of the book at 22.4% and falling.",
     "drivers": ["loan growth 42.1% y/y; 4-week pace 38.0%", "state 47.5% vs private 36.8% (10.7pp gap)",
                 "FX loans 22.4% (-0.8pp y/y)", "mix cards 55.0% vs SME 33.0%"]},

    {"key": "deposits", "tab": "Deposits", "asOf": "2026-05", "facts": {
        "deposits_yoy": 36.0, "loans_yoy": 42.1, "funding_gap_pp": 6.1, "fc_share": 39.5,
        "fc_share_delta_pp": 2.1, "demand_share": 22.0, "demand_delta_pp": 1.3, "ldr": 88},
     "headline": "Deposits growing 36.0% y/y — behind loans by 6.1pp, so the funding gap is widening; FC deposits 39.5% of the base and the loan-to-deposit ratio 88%.",
     "drivers": ["deposits 36.0% y/y, behind loans (42.1%) by 6.1pp", "FC deposits 39.5% (-2.1pp y/y)",
                 "demand deposits 22.0% (-1.3pp)", "LDR 88%"]},

    {"key": "asset_quality", "tab": "Asset Quality", "asOf": "2026-05", "facts": {
        "npl": 1.81, "npl_delta_pp": 0.04, "stage2": 8.4, "stage2_delta_pp": 0.3,
        "npl_stock_yoy": 46.0, "coverage": 74.2, "coverage_delta_pp": 0.5,
        "cards_npl": 3.6, "sme_npl": 2.9},
     "headline": "Headline asset quality is still benign — NPLs at 1.81% — with coverage at 74.2% and slipping; the pockets to watch are consumer cards books.",
     "drivers": ["NPL 1.81% (+0.04pp)", "Stage-2 8.4% of the book (+0.3pp)", "NPL stock +46.0% y/y",
                 "coverage 74.2% (-0.5pp)", "cards NPL 3.6% vs SME 2.9%"]},

    {"key": "capital", "tab": "Capital", "asOf": "2026-05", "facts": {
        "car": 18.1, "car_min": 12, "car_buffer_pp": 6.1, "car_delta_pp": 0.2,
        "cet1": 14.3, "equity_yoy": 31.0, "leverage_x": 8.4},
     "headline": "The sector holds a 6.1pp buffer over the 12% minimum (CAR 18.1%, CET1 14.3%); the question is whether 31.0% equity growth keeps funding the balance sheet.",
     "drivers": ["CAR 18.1% — 6.1pp over the 12% min (+0.2pp)", "CET1 14.3%",
                 "equity +31.0% y/y", "gearing 8.4x equity"]},

    {"key": "profitability", "tab": "Profitability", "asOf": "2026-05", "facts": {
        "roe": 34.2, "roe_real_pp": 2.2, "cpi": 32.0, "nim": 4.35, "nim_delta_pp": 0.07,
        "roa": 3.1, "opex": 2.05, "opex_delta_pp": 0.03},
     "headline": "The sector earns 34.2% on equity — roughly at inflation (+2.2pp real) — with NIM at 4.35% and widening.",
     "drivers": ["ROE 34.2% (+2.2pp vs 32.0% CPI)", "NIM 4.35% (+0.07pp)", "ROA 3.1%",
                 "opex 2.05% of assets (+0.03pp)"]},

    {"key": "liquidity", "tab": "Liquidity", "asOf": "2026-05", "facts": {
        "tl_ldr_public": 118, "tl_ldr_private": 96, "fc_dep_share": 39.5,
        "fc_dep_delta_pp": 2.1, "lcr": 148, "lcr_floor": 100, "net_cbrt_funding_bn": 320},
     "headline": "Funding is manageable: TL loan-to-deposit 96% (private) / 118% (public), FC deposits 39.5% of the base, and LCR at 148%.",
     "drivers": ["TL LDR public 118% vs private 96%", "FC deposits 39.5% (-2.1pp y/y)",
                 "LCR 148% (over the 100% floor)", "net CBRT funding TL 320bn surplus"]},

    {"key": "market_risk", "tab": "Market Risk", "asOf": "2026-05", "facts": {
        "nop_pct": 3.2, "nop_limit": 20, "gap1y_pct": 12.5},
     "headline": "Direct FX risk is small (NOP +3.2% of capital); the real sensitivity is rates — a negative repricing gap gears earnings to the easing cycle continuing.",
     "drivers": ["FX net open position +3.2% of capital (inside the +/-20% limit), net long",
                 "the <=1y repricing gap is -12.5% of assets — liabilities reprice first, so falling rates lift NII"]},

    # ---- number-traps (facts omit the temptingly derivable / roundable figure) ----
    {"key": "trap_round", "tab": "TRAP: rounding", "asOf": "2026-05", "trap": True,
     "trap_note": "Values invite rounding (39.7→40, 49.8→50, 33.4→33/'a third'). Any rounded number is invented.",
     "facts": {"loans_yoy": 39.7, "state_yoy": 49.8, "fx_share": 33.4},
     "headline": "Credit growth 39.7% y/y, led by state banks (49.8%); FX share 33.4% of the book.",
     "drivers": ["loan growth 39.7% y/y", "state banks 49.8% y/y", "FX share 33.4% of the book"]},

    {"key": "trap_derive_real", "tab": "TRAP: derive real ROE", "asOf": "2026-05", "trap": True,
     "trap_note": "ROE and CPI given, real spread NOT given. Computing 34.2-31.9=2.3 and stating it is invention.",
     "facts": {"roe": 34.2, "cpi": 31.9, "nim": 4.35},
     "headline": "The sector earns 34.2% on equity against 31.9% inflation, with NIM at 4.35%.",
     "drivers": ["ROE 34.2%", "CPI 31.9%", "NIM 4.35%"]},

    {"key": "trap_derive_buffer", "tab": "TRAP: derive buffer", "asOf": "2026-05", "trap": True,
     "trap_note": "CARs and minimum given, buffer NOT given. Computing 18.1-12=6.1 and stating it is invention.",
     "facts": {"car": 18.1, "cet1": 14.3, "car_min": 12},
     "headline": "Sector CAR 18.1% and CET1 14.3%, both above the 12% minimum.",
     "drivers": ["CAR 18.1%", "CET1 14.3%", "minimum 12%"]},
]


def build_user_msg(sc: dict) -> str:
    return (
        f"FACTS for the {sc['tab']} Read (the only numbers you may use):\n"
        + json.dumps(sc["facts"], indent=2)
        + "\n\nDETERMINISTIC DRIVERS (context):\n- " + "\n- ".join(sc["drivers"])
        + "\n\nCURRENT TEMPLATE LEAD (rewrite this):\n" + sc["headline"]
    )


def allowed_numbers(sc: dict) -> set[float]:
    allowed = {float(v) for v in sc["facts"].values() if isinstance(v, (int, float))}
    y, m = sc["asOf"].split("-")
    allowed.update({float(int(y)), float(int(m))})
    return allowed


# ===========================================================================
# Output analysis
# ===========================================================================
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
DASHES = "-‐‑‒–—"
PREAMBLE_RE = re.compile(r"^\s*(here|sure|okay|certainly|as requested|below|the read)\b", re.I)


def strip_reasoning(text: str) -> tuple[str, bool]:
    had = bool(THINK_RE.search(text)) or "</think>" in text
    text = THINK_RE.sub("", text)
    if "</think>" in text:
        text = text.split("</think>", 1)[-1]
    return text.strip(), had


def unknown_numbers(text: str, allowed: set[float]) -> list[str]:
    """Numbers that aren't facts. Digits glued to a label (Stage-2, CET1) are not
    claims — skipped."""
    out: list[str] = []
    for m in NUM_RE.finditer(text):
        j = m.start() - 1
        while j >= 0 and text[j] in DASHES:
            j -= 1
        if j >= 0 and text[j].isalpha():
            continue
        try:
            n = float(m.group())
        except ValueError:
            continue
        if not any(abs(n - a) < 0.01 or abs(abs(n) - a) < 0.01 for a in allowed):
            out.append(m.group())
    return out


def format_flags(text: str) -> list[str]:
    flags = []
    if "\n" in text:
        flags.append("multiline")
    if any(t in text for t in ("**", "`", "##")) or text.lstrip().startswith(("#", "- ", "* ")):
        flags.append("markdown")
    if PREAMBLE_RE.search(text) or text.lstrip()[:1] in ('"', "'", "“"):
        flags.append("preamble")
    if len(re.findall(r"[.!?]\s+[A-Z]", text)) >= 1:
        flags.append("multi-sentence")
    return flags


# ===========================================================================
# Providers (Groq + Cerebras)
# ===========================================================================
PROVIDERS = {
    "groq": {
        "aliases": ["GROQ_API_KEY", "GROQ_API_TOKEN"],
        "base": "https://api.groq.com/openai/v1",
        "min_interval": 6.0,
        "models": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile",
                   "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"],
    },
    "cerebras": {
        "aliases": ["CEREBRAS_API_KEY", "CEREBRAS_KEY", "CEREBRAS_API_TOKEN"],
        "base": "https://api.cerebras.ai/v1",
        "min_interval": 13.0,  # free tier is 5 req/min -> 1 per 12s + margin
        "models": ["gpt-oss-120b", "zai-glm-4.7", "gemma-4-31b"],
    },
}
_last_call: dict[str, float] = {}


def key_for(prov: dict) -> str | None:
    for a in prov["aliases"]:
        if os.environ.get(a):
            return os.environ[a]
    return None


def pace(prov_name: str, interval: float) -> None:
    wait = _last_call.get(prov_name, 0.0) + interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[prov_name] = time.time()


def run_once(prov_name: str, prov: dict, key: str, model: str, sc: dict) -> dict:
    payload = {"model": model, "temperature": TEMPERATURE, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": build_user_msg(sc)}]}
    for attempt in range(3):
        pace(prov_name, prov["min_interval"])
        t0 = time.time()
        try:
            r = requests.post(f"{prov['base']}/chat/completions",
                              headers={"Authorization": f"Bearer {key}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=120)
            dt = time.time() - t0
            rl = {k: v for k, v in r.headers.items()
                  if re.search(r"ratelimit|retry-after", k, re.I)}
            if r.status_code == 429:
                back = float(r.headers.get("retry-after", "15"))
                print(f"    429 {prov_name}/{model} — backoff {back:.0f}s", flush=True)
                time.sleep(min(back, 30) + 1)
                continue
            if r.status_code != 200:
                return {"ok": False, "err": f"HTTP {r.status_code}: {r.text[:120]}", "dt": dt, "rl": rl}
            body = json.loads(r.content.decode("utf-8"))
            raw = body["choices"][0]["message"]["content"] or ""
            text, leaked = strip_reasoning(raw.strip())
            usage = body.get("usage", {}) or {}
            return {"ok": True, "dt": dt, "text": text, "leaked": leaked,
                    "unknown": unknown_numbers(text, allowed_numbers(sc)),
                    "flags": format_flags(text), "words": len(text.split()) if text else 0,
                    "empty": not text, "out_tok": usage.get("completion_tokens"), "rl": rl}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{type(e).__name__}: {e}", "dt": time.time() - t0, "rl": {}}
    return {"ok": False, "err": "429 after retries", "dt": 0.0, "rl": {}}


# ===========================================================================
# Aggregate + report
# ===========================================================================
def esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["res"]["ok"]]
    n = len(rows)
    good = [r for r in ok if not r["res"]["empty"]]
    invented = [r for r in good if r["res"]["unknown"]]
    bad_fmt = [r for r in good if r["res"]["flags"]]
    over = [r for r in good if r["res"]["words"] > 45]
    within = [r for r in good if 30 <= r["res"]["words"] <= 45]
    empties = [r for r in ok if r["res"]["empty"]]
    errs = [r for r in rows if not r["res"]["ok"]]
    lat = [r["res"]["dt"] for r in ok]
    return {
        "n": n, "invent_rate": len(invented) / n if n else 0,
        "empty_rate": (len(empties) + len(errs)) / n if n else 0,
        "fmt_bad_rate": len(bad_fmt) / len(good) if good else 0,
        "within_len": len(within) / len(good) if good else 0,
        "over_len": len(over) / len(good) if good else 0,
        "avg_lat": sum(lat) / len(lat) if lat else 0,
        "leaked": any(r["res"].get("leaked") for r in ok),
        "n_invent": len(invented), "n_err": len(errs) + len(empties),
    }


def render(results: dict, aggs: dict, rl: dict, meta: dict) -> str:
    L: list[str] = []
    L.append("# Free-model reliability gauntlet — “The Read”\n")
    L.append(f"*Run {meta['ts']} · commit `{meta['sha'][:8]}` · Groq + Cerebras · "
             f"{meta['n_models']} models × {len(SCENARIOS)} Reads × {REPEATS} repeats · "
             f"temperature {TEMPERATURE}*\n")
    L.append("Gemini is excluded (not free for us). This round measures the "
             "**downside**: how often each model breaks the number-lock or the format, "
             "and how stable it is when called repeatedly at the temperature we'd ship.\n")

    # scorecard
    L.append("## Scorecard — ranked by reliability (lower invent-rate is better)\n")
    L.append("| model | invent-rate | fmt-bad | empty/err | ≤45w | in 30–45w | avg lat | notes |")
    L.append("|---|--:|--:|--:|--:|--:|--:|:--|")
    ordered = sorted(aggs.items(), key=lambda kv: (kv[1]["invent_rate"], kv[1]["fmt_bad_rate"],
                                                   -kv[1]["within_len"]))
    for name, a in ordered:
        note = []
        if a["leaked"]:
            note.append("reasoning-leak")
        if a["over_len"] > 0.3:
            note.append("runs long")
        L.append(f"| {name} | {a['invent_rate']*100:.0f}% ({a['n_invent']}/{a['n']}) | "
                 f"{a['fmt_bad_rate']*100:.0f}% | {a['empty_rate']*100:.0f}% | "
                 f"{(1-a['over_len'])*100:.0f}% | {a['within_len']*100:.0f}% | "
                 f"{a['avg_lat']:.1f}s | {', '.join(note) or '—'} |")
    L.append("\n*invent-rate = share of samples containing a number that isn't a fact "
             "(= how often we'd fall back to the deterministic template). fmt-bad = "
             "preamble/markdown/multi-sentence/multiline. Label digits (Stage-2, CET1) "
             "are not counted as invented.*\n")

    # number traps
    L.append("## Number-trap results (the interesting failures)\n")
    L.append("Each trap's facts omit a temptingly derivable/roundable figure. A model "
             "that stays clean respected the number-lock; a flagged one would be caught "
             "and fall back.\n")
    for sc in SCENARIOS:
        if not sc.get("trap"):
            continue
        L.append(f"### {sc['tab']}\n")
        L.append(f"*{sc['trap_note']}*\n")
        L.append(f"> template: {sc['headline']}\n")
        L.append("| model | clean? | invented | sample rewrite |")
        L.append("|---|:--:|:--|:--|")
        for row in results[sc["key"]]:
            res = row["res"]
            if not res["ok"]:
                L.append(f"| {row['model']} | — | (error) | {esc(res['err'])} |")
                continue
            mark = "✅" if not res["unknown"] and not res["empty"] else "❌"
            inv = ", ".join(res["unknown"]) or ("EMPTY" if res["empty"] else "—")
            L.append(f"| {row['model']} | {mark} | {inv} | {esc(res['text'])[:150]} |")
        L.append("")

    # failure log (core reads)
    L.append("## Failure log — every invented / empty / mis-formatted sample (core Reads)\n")
    any_fail = False
    for sc in SCENARIOS:
        if sc.get("trap"):
            continue
        fails = [r for r in results[sc["key"]]
                 if r["res"]["ok"] and (r["res"]["unknown"] or r["res"]["empty"] or r["res"]["flags"])]
        if not fails:
            continue
        any_fail = True
        L.append(f"**{sc['tab']}**")
        for r in fails:
            res = r["res"]
            why = []
            if res["unknown"]:
                why.append(f"invented {res['unknown']}")
            if res["empty"]:
                why.append("empty")
            if res["flags"]:
                why.append("+".join(res["flags"]))
            L.append(f"- `{r['model']}` — {', '.join(why)}: {esc(res['text'])[:160] or '(empty)'}")
        L.append("")
    if not any_fail:
        L.append("*(none — every core-Read sample was clean and well-formed.)*\n")

    # one clean sample per model
    L.append("## One representative rewrite per model (Overview)\n")
    seen = set()
    for row in results["overview"]:
        if row["model"] in seen or not row["res"]["ok"] or row["res"]["empty"]:
            continue
        seen.add(row["model"])
        L.append(f"- **{row['provider']} · {row['model']}**  ")
        L.append(f"  > {row['res']['text']}")
    L.append("")

    # rate limits
    L.append("## Rate limits (measured this run)\n")
    for prov, headers in rl.items():
        L.append(f"**{prov}**: " + (", ".join(f"`{k}`={v}" for k, v in sorted(headers.items()))
                                    or "(none returned)"))
        L.append("")
    return "\n".join(L)


def main() -> None:
    load_env()
    meta = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sha": os.environ.get("GIT_SHA", "local")}
    keyed = {}
    for pn, prov in PROVIDERS.items():
        k = key_for(prov)
        if k:
            keyed[pn] = k
        else:
            print(f"[skip] {pn}: no key")
    meta["n_models"] = sum(len(PROVIDERS[p]["models"]) for p in keyed)

    results: dict = {sc["key"]: [] for sc in SCENARIOS}
    rl: dict = {}
    total = len(SCENARIOS) * meta["n_models"] * REPEATS
    done = 0
    for sc in SCENARIOS:
        for pn, key in keyed.items():
            prov = PROVIDERS[pn]
            for model in prov["models"]:
                for _ in range(REPEATS):
                    res = run_once(pn, prov, key, model, sc)
                    if res.get("rl"):
                        rl[pn] = res["rl"]
                    results[sc["key"]].append({"provider": pn, "model": model, "res": res})
                    done += 1
                tag = "trap " if sc.get("trap") else ""
                last = results[sc["key"]][-1]["res"]
                st = ("ok" if last["ok"] and not last.get("empty") else "FAIL")
                print(f"[{done}/{total}] {tag}{sc['key']} · {pn}/{model}: {st}", flush=True)

    aggs = {f"{r['provider']} · {r['model']}": None
            for sc in SCENARIOS for r in results[sc["key"]]}
    for name in list(aggs):
        rows = [r for sc in SCENARIOS for r in results[sc["key"]]
                if f"{r['provider']} · {r['model']}" == name]
        aggs[name] = aggregate(rows)

    md = render(results, aggs, rl, meta)
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"meta": meta, "aggs": aggs, "results": results, "rl": rl},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_MD.name} + {OUT_JSON.name}")


if __name__ == "__main__":
    main()
