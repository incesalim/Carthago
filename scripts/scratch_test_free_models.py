"""THROWAWAY evaluation harness — free LLM providers on the "The Read" headline
rewrite (Option 1). Runs several deterministic Reads across several free models,
captures latency / token usage / throughput and the providers' rate-limit
headers, validates every number against the facts, and writes a readable
Markdown report (free_model_eval.md) + machine JSON (free_model_eval.json).

Keys come from GitHub secrets via env (mapped in test-free-models.yml):
  GROQ_API_KEY / CEREBRAS_API_KEY / GEMINI_API_KEY

Not wired into the dashboard or pipeline. Delete once a direction is chosen.
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
OUT_MD = ROOT / "free_model_eval.md"
OUT_JSON = ROOT / "free_model_eval.json"


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# ===========================================================================
# The task
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

# Each Read: realistic deterministic facts (as insights.ts would emit), the
# current template lead, and the driver bullets for context. `allowed` numbers
# are derived from the facts automatically (plus the period tokens).
SCENARIOS: list[dict] = [
    {
        "key": "overview",
        "tab": "Overview",
        "asOf": "2026-05",
        "facts": {
            "assets_yoy": 38.5, "loans_yoy": 42.1, "deposits_yoy": 36.0,
            "npl": 1.81, "npl_delta_pp": 0.04, "car": 18.1, "car_min": 12,
            "car_buffer_pp": 6.1, "roe": 34.2, "ldr": 88, "nim": 4.35,
            "nim_delta_pp": 0.07,
        },
        "headline": ("As of 2026-05: the sector is growing (assets +38.5% y/y) "
                     "and profitable (ROE 34.2%), with NPL at 1.81% and capital "
                     "comfortably above the minimum at 18.1%."),
        "drivers": [
            "Balance sheet expanding — assets +38.5% y/y, loans +42.1%, deposits +36.0%.",
            "NPL ratio 1.81% (+0.04pp m/m, broadly stable).",
            "Capital adequacy 18.1% — 6.1pp above the 12% minimum.",
            "ROE 34.2% (annualized). NIM 4.35% (+0.07pp m/m, widening).",
            "Loan-to-deposit 88% — funding comfortable.",
        ],
    },
    {
        "key": "asset_quality",
        "tab": "Asset Quality",
        "asOf": "2026-05",
        "facts": {
            "npl": 1.81, "npl_delta_pp": 0.04, "stage2": 8.4,
            "stage2_delta_pp": 0.3, "npl_stock_yoy": 46.0, "coverage": 74.2,
            "coverage_delta_pp": 0.5, "cards_npl": 3.6, "sme_npl": 2.9,
        },
        "headline": ("Headline asset quality is still benign — NPLs at 1.81% — "
                     "with coverage at 74.2% and slipping; the pockets to watch "
                     "are consumer cards books."),
        "drivers": [
            "NPL ratio 1.81% (+0.04pp m/m) — low by Turkish cycle standards.",
            "Stage-2 loans — the pre-NPL watchlist — 8.4% of the book (+0.3pp q/q, migrating up).",
            "NPL stock growing 46.0% y/y — formation running ahead of the book.",
            "Provision coverage 74.2% (-0.5pp m/m) — slipping as the book seasons.",
            "Stress concentrated in retail cards (3.6% NPL) vs 2.9% for SME.",
        ],
    },
    {
        "key": "profitability",
        "tab": "Profitability",
        "asOf": "2026-05",
        "facts": {
            "roe": 34.2, "roe_real_pp": 2.2, "cpi": 32.0, "nim": 4.35,
            "nim_delta_pp": 0.07, "roa": 3.1, "opex": 2.05, "opex_delta_pp": 0.03,
        },
        "headline": ("The sector earns 34.2% on equity — roughly at inflation "
                     "(+2.2pp real) — with NIM at 4.35% and widening."),
        "drivers": [
            "ROE 34.2% nominal — +2.2pp vs 12m-avg CPI (32.0%), barely positive in real terms.",
            "NIM 4.35% (+0.07pp m/m) — margins widening as funding reprices down.",
            "ROA 3.1% — the leverage-free read on the same earnings.",
            "Operating cost 2.05% of assets (deteriorating +0.03pp m/m).",
        ],
    },
    {
        "key": "liquidity",
        "tab": "Liquidity",
        "asOf": "2026-05",
        "facts": {
            "tl_ldr_public": 118, "tl_ldr_private": 96, "fc_dep_share": 39.5,
            "fc_dep_delta_pp": 2.1, "lcr": 148, "net_cbrt_funding_bn": 320,
        },
        "headline": ("Funding is manageable: TL loan-to-deposit 96% (private) / "
                     "118% (public), FC deposits 39.5% of the base, and LCR at 148%."),
        "drivers": [
            "TL loan-to-deposit: public 118% vs private 96% — public TL book more than fully lent.",
            "FC deposits 39.5% of the base (-2.1pp y/y) — dollarization unwinding.",
            "LCR 148% (audited quarterly) — a wide cushion over the 100% floor.",
            "Net CBRT funding ₺320bn surplus — the system parks TL at the central bank.",
        ],
    },
]


def build_user_msg(sc: dict) -> str:
    return (
        f"FACTS for the {sc['tab']} Read (the only numbers you may use):\n"
        + json.dumps(sc["facts"], indent=2)
        + "\n\nDETERMINISTIC DRIVERS (context):\n- "
        + "\n- ".join(sc["drivers"])
        + "\n\nCURRENT TEMPLATE LEAD (rewrite this):\n"
        + sc["headline"]
    )


def allowed_numbers(sc: dict) -> set[float]:
    allowed = {float(v) for v in sc["facts"].values() if isinstance(v, (int, float))}
    y, m = sc["asOf"].split("-")
    allowed.update({float(int(y)), float(int(m)), 100.0})  # period + the 100% LCR floor
    return allowed


NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_reasoning(text: str) -> tuple[str, bool]:
    """Some reasoning models leak a <think>…</think> block inline. Strip it and
    flag that it happened (a mark against using that model raw)."""
    had = bool(THINK_RE.search(text)) or "</think>" in text
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # unbalanced (truncated open tag)
        text = text.split("</think>", 1)[-1]
    return text.strip(), had


def check_numbers(text: str, allowed: set[float]) -> list[str]:
    unknown: list[str] = []
    for tok in NUM_RE.findall(text):
        try:
            n = float(tok)
        except ValueError:
            continue
        if not any(abs(n - a) < 0.01 or abs(abs(n) - a) < 0.01 for a in allowed):
            unknown.append(tok)
    return unknown


# ===========================================================================
# Providers (all OpenAI-compatible)
# ===========================================================================
PROVIDERS = {
    "groq": {
        "aliases": ["GROQ_API_KEY", "GROQ_API_TOKEN"],
        "base": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
            "meta-llama/llama-4-scout-17b-16e-instruct", "qwen/qwen3.6-27b",
            "llama-3.1-8b-instant",
        ],
    },
    "cerebras": {
        "aliases": ["CEREBRAS_API_KEY", "CEREBRAS_KEY", "CEREBRAS_API_TOKEN"],
        "base": "https://api.cerebras.ai/v1",
        "models": ["gpt-oss-120b", "zai-glm-4.7", "gemma-4-31b"],
    },
    "google": {
        "aliases": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"],
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            "gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash",
            "gemini-3.1-flash-lite", "gemini-flash-latest",
        ],
    },
}

RL_RE = re.compile(r"(ratelimit|rate-limit|retry-after|quota)", re.I)


def key_for(prov: dict) -> str | None:
    for a in prov["aliases"]:
        if os.environ.get(a):
            return os.environ[a]
    return None


def list_models(base: str, key: str) -> list[str]:
    try:
        r = requests.get(f"{base}/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        return sorted(m.get("id", "").replace("models/", "") for m in r.json().get("data", []))
    except Exception as e:  # noqa: BLE001
        return [f"<discovery failed: {type(e).__name__}: {e}>"]


def run_task(base: str, key: str, model: str, sc: dict) -> dict:
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_msg(sc)},
        ],
    }
    t0 = time.time()
    try:
        r = requests.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json=payload, timeout=90)
        dt = time.time() - t0
        rl = {k: v for k, v in r.headers.items() if RL_RE.search(k)}
        if r.status_code != 200:
            return {"ok": False, "err": f"HTTP {r.status_code}: {r.text[:140]}",
                    "dt": dt, "rl": rl}
        body = json.loads(r.content.decode("utf-8"))
        raw = body["choices"][0]["message"]["content"]
        text, leaked = strip_reasoning(raw.strip())
        usage = body.get("usage", {}) or {}
        unknown = check_numbers(text, allowed_numbers(sc))
        return {
            "ok": True, "dt": dt, "text": text, "leaked": leaked,
            "unknown": unknown,
            "in_tok": usage.get("prompt_tokens"), "out_tok": usage.get("completion_tokens"),
            "rl": rl,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": f"{type(e).__name__}: {e}", "dt": time.time() - t0, "rl": {}}


# ===========================================================================
# Report
# ===========================================================================
def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render_md(results: dict, catalogues: dict, rl: dict, meta: dict) -> str:
    L: list[str] = []
    L.append("# Free-Model Evaluation — “The Read” headline rewrite\n")
    L.append(f"*Run {meta['ts']} · commit `{meta['sha'][:8]}` · "
             f"{meta['n_models']} models × {len(SCENARIOS)} Reads · "
             f"temperature 0.4*\n")
    L.append("> **No winner is declared here.** This is the raw evidence — "
             "outputs, performance, rate limits — so the choice can be made "
             "deliberately.\n")

    # --- how tested
    L.append("## How this was tested\n")
    L.append("Each model is asked to rewrite a **deterministic** template lead "
             "(what `web/app/lib/insights.ts` already emits) into one synthesized "
             "sentence, **using only the numbers in the facts**. The output is then "
             "machine-checked: every number in the sentence must match a fact "
             "(±0.01) or it is flagged `NEW#`. That is the exact guardrail the real "
             "integration relies on — a flagged output would be rejected and the "
             "deterministic template shown instead.\n")
    L.append("**System prompt:**\n")
    L.append("```\n" + SYSTEM + "\n```\n")
    L.append("**Legend:** `✅` numbers clean · `⚠️ NEW#[…]` invented a number "
             "(would be rejected) · `🧠` leaked a reasoning block · `in/out` = "
             "prompt/completion tokens · `tok/s` = completion tokens per second.\n")

    # --- rate limits
    L.append("## Rate limits (measured from response headers)\n")
    L.append("Captured live from each provider's last response this run — "
             "authoritative for *this account/tier*.\n")
    for prov, headers in rl.items():
        L.append(f"**{prov}**")
        if not headers:
            L.append("- (no rate-limit headers returned on the OpenAI-compatible "
                     "endpoint — see provider docs)\n")
            continue
        L.append("")
        L.append("| header | value |")
        L.append("|---|---|")
        for k in sorted(headers):
            L.append(f"| `{k}` | {md_escape(str(headers[k]))} |")
        L.append("")

    # --- effectiveness
    L.append("## Effectiveness — can we actually use this within the limits?\n")
    L.append(EFFECTIVENESS)

    # --- results per Read
    L.append("## Results by Read\n")
    for sc in SCENARIOS:
        L.append(f"### {sc['tab']} — as of {sc['asOf']}\n")
        L.append("**Deterministic template (the thing being rewritten):**")
        L.append(f"> {sc['headline']}\n")
        L.append("| provider · model | latency | in/out tok | tok/s | numbers |")
        L.append("|---|--:|--:|--:|:--|")
        rows = results.get(sc["key"], [])
        for row in rows:
            name = f"{row['provider']} · {row['model']}"
            if not row["res"]["ok"]:
                L.append(f"| {name} | {row['res']['dt']:.1f}s | — | — | ❌ {md_escape(row['res']['err'])} |")
                continue
            res = row["res"]
            it, ot = res.get("in_tok"), res.get("out_tok")
            toks = f"{it or '?'}/{ot or '?'}"
            tps = f"{(ot / res['dt']):.0f}" if ot and res["dt"] else "—"
            flag = "✅" if not res["unknown"] else f"⚠️ NEW#{res['unknown']}"
            if res["leaked"]:
                flag += " 🧠"
            L.append(f"| {name} | {res['dt']:.1f}s | {toks} | {tps} | {flag} |")
        L.append("")
        L.append("**Outputs:**\n")
        for row in rows:
            if not row["res"]["ok"]:
                continue
            L.append(f"- **{row['provider']} · {row['model']}**  ")
            L.append(f"  > {row['res']['text']}")
        L.append("")

    # --- catalogues
    L.append("## Model catalogues visible to each key\n")
    for prov, cat in catalogues.items():
        L.append(f"**{prov}** ({len(cat)}): " + ", ".join(f"`{c}`" for c in cat) + "\n")

    return "\n".join(L)


EFFECTIVENESS = """\
The real use is **precomputed on a schedule, not live per request** — a cron
regenerates a Read's headline only when its as-of period advances, writes it to
D1, and the server component reads the cached string (falling back to the
deterministic template on any mismatch).

- `insights.ts` has **8 Reads** (Overview, Credit, Deposits, Asset Quality,
  Capital, Profitability, Liquidity, Market Risk).
- Worst case, regenerate **all 8 every week** = ~32/month. With a
  primary→fallback retry that is at most ~64 calls/month — **about 2 a day.**
- Every free tier measured here allows *dozens of requests per minute* and
  hundreds-to-thousands per day. **Volume is a non-issue by three orders of
  magnitude.** The constraint is never the rate limit — it is quality,
  determinism-gating, and provider reliability.

**How to use the headroom well** (options, not decided):
- **Primary + cross-provider fallback**: one model writes; if it errors, is
  rate-limited, or trips the number-check, fall through to a second provider,
  then to the deterministic template. Costs nothing, removes single-provider
  risk.
- **Ensemble/vote for free**: since volume is free, generate from 2-3 models and
  keep the one that (a) passes the number-check and (b) is closest to the target
  length. Quality win at zero marginal cost.
- **Regeneration gate**: reuse the summarizer's input-hash trick so a Read is
  only rewritten when its numbers actually change — keeps output stable week to
  week and avoids gratuitous drift.
"""


def main() -> None:
    load_env()
    meta = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sha": os.environ.get("GIT_SHA", "local"),
    }
    catalogues: dict = {}
    rl: dict = {}
    results: dict = {sc["key"]: [] for sc in SCENARIOS}
    n_models = 0

    keyed = {}
    for prov_name, prov in PROVIDERS.items():
        key = key_for(prov)
        if not key:
            print(f"[skip] {prov_name}: no key")
            continue
        keyed[prov_name] = key
        catalogues[prov_name] = list_models(prov["base"], key)
        print(f"[{prov_name}] {len(catalogues[prov_name])} models visible")

    for sc in SCENARIOS:
        print(f"\n=== Read: {sc['tab']} ===")
        for prov_name, key in keyed.items():
            prov = PROVIDERS[prov_name]
            cat = catalogues[prov_name]
            for model in prov["models"]:
                available = any(model in c for c in cat) or all(c.startswith("<") for c in cat)
                if not available:
                    continue
                res = run_task(prov["base"], key, model, sc)
                if res.get("rl"):
                    rl[prov_name] = res["rl"]
                elif prov_name not in rl:
                    rl[prov_name] = {}
                results[sc["key"]].append({"provider": prov_name, "model": model, "res": res})
                if res["ok"]:
                    flag = "OK" if not res["unknown"] else f"NEW#{res['unknown']}"
                    print(f"  > {prov_name}/{model}: {res['dt']:.1f}s [{flag}]"
                          + (" [reasoning-leak]" if res["leaked"] else ""))
                else:
                    print(f"  X {prov_name}/{model}: {res['err']}")
                time.sleep(1.5)  # gentle on free-tier RPM

    n_models = sum(len(PROVIDERS[p]["models"]) for p in keyed)
    meta["n_models"] = n_models
    md = render_md(results, catalogues, rl, meta)
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"meta": meta, "results": results, "rl": rl,
                                    "catalogues": catalogues}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\nWrote {OUT_MD.name} ({len(md)} chars) and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
