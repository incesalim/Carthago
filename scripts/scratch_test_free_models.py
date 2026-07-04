"""THROWAWAY smoke test — evaluate FREE models (Groq / Cerebras / Google Gemini)
on the Option-1 task: rewrite the deterministic "The Read" headline into one
fluid, synthesized sentence WITHOUT inventing any number.

This touches nothing in the dashboard or pipeline. It is meant to be run from a
manual `workflow_dispatch` (keys live in GitHub secrets, not locally) and then
deleted. It discovers each provider's model catalogue, runs the task against a
curated free-model shortlist, and validates output the way the real integration
will: every number in the rewrite must already be a fact.

Env (mapped from secrets in the workflow):
  GROQ_API_KEY / CEREBRAS_API_KEY / GEMINI_API_KEY
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# Local convenience only: load repo-root .env if present (CI has none → env wins).
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


# ---------------------------------------------------------------------------
# Task input: a realistic deterministic Overview "Read" (what insights.ts would
# emit). The LLM must rewrite `DET_HEADLINE` using ONLY these numbers.
# ---------------------------------------------------------------------------
FACTS = {
    "asOf": "2026-05",
    "assets_yoy": 38.5,
    "loans_yoy": 42.1,
    "deposits_yoy": 36.0,
    "npl": 1.81,
    "npl_delta_pp": 0.04,
    "car": 18.1,
    "car_min": 12,
    "car_buffer_pp": 6.1,
    "roe": 34.2,
    "ldr": 88,
    "nim": 4.35,
    "nim_delta_pp": 0.07,
}
DET_HEADLINE = (
    "As of 2026-05: the sector is growing (assets +38.5% y/y) and profitable "
    "(ROE 34.2%), with NPL at 1.81% and capital comfortably above the minimum "
    "at 18.1%."
)
DET_DRIVERS = [
    "Balance sheet expanding — assets +38.5% y/y, loans +42.1%, deposits +36.0%.",
    "NPL ratio 1.81% (+0.04pp m/m, broadly stable).",
    "Capital adequacy 18.1% — 6.1pp above the 12% minimum.",
    "ROE 34.2% (annualized).",
    "NIM 4.35% (+0.07pp m/m — margins widening as funding reprices down).",
    "Loan-to-deposit 88% — funding comfortable.",
]

SYSTEM = (
    "You write the one-sentence editorial lead ('The Read') for a Turkish "
    "banking-sector dashboard, in the terse, analytical voice of BBVA Research. "
    "You are given the deterministic facts and the current template lead. "
    "Rewrite it as ONE flowing sentence (max ~45 words) that SYNTHESIZES the "
    "vitals into a 'so what' — connect them causally where the facts support it "
    "(e.g. funding repricing lifting margins). HARD RULE: use ONLY numbers that "
    "appear in the facts below. Never invent, round, or compute a new figure. "
    "Do not add a number that isn't given. Output ONLY the sentence, no preamble."
)


def build_user_msg() -> str:
    return (
        "FACTS (the only numbers you may use):\n"
        + json.dumps(FACTS, indent=2)
        + "\n\nDETERMINISTIC DRIVERS:\n- "
        + "\n- ".join(DET_DRIVERS)
        + "\n\nCURRENT TEMPLATE LEAD (rewrite this):\n"
        + DET_HEADLINE
    )


# ---------------------------------------------------------------------------
# Number validation — the guardrail the real integration relies on.
# ---------------------------------------------------------------------------
def allowed_numbers() -> set[float]:
    allowed: set[float] = set()
    for v in FACTS.values():
        if isinstance(v, (int, float)):
            allowed.add(float(v))
    allowed.update({2026.0, 5.0})  # period tokens that legitimately appear
    return allowed


NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def check_numbers(text: str) -> tuple[bool, list[str]]:
    allowed = allowed_numbers()
    unknown: list[str] = []
    for tok in NUM_RE.findall(text):
        try:
            n = float(tok)
        except ValueError:
            continue
        if any(abs(n - a) < 0.01 or abs(abs(n) - a) < 0.01 for a in allowed):
            continue
        unknown.append(tok)
    return (len(unknown) == 0), unknown


# ---------------------------------------------------------------------------
# Providers — all OpenAI-compatible, so one client shape covers them.
# ---------------------------------------------------------------------------
PROVIDERS = {
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile",
            "moonshotai/kimi-k2-instruct",
            "openai/gpt-oss-120b",
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
        ],
    },
    "cerebras": {
        "key_env": "CEREBRAS_API_KEY",
        "base": "https://api.cerebras.ai/v1",
        "models": [
            "llama-3.3-70b",
            "gpt-oss-120b",
            "qwen-3-32b",
            "llama3.1-8b",
        ],
    },
    "google": {
        "key_env": "GEMINI_API_KEY",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ],
    },
}


def key_for(prov: dict) -> str | None:
    aliases = {
        "GROQ_API_KEY": ["GROQ_API_KEY", "GROQ_API_TOKEN"],
        "CEREBRAS_API_KEY": ["CEREBRAS_API_KEY", "CEREBRAS_KEY", "CEREBRAS_API_TOKEN"],
        "GEMINI_API_KEY": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"],
    }.get(prov["key_env"], [prov["key_env"]])
    for a in aliases:
        v = os.environ.get(a)
        if v:
            return v
    return None


def list_models(base: str, key: str) -> list[str]:
    try:
        r = requests.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        return sorted(m.get("id", "").replace("models/", "") for m in data)
    except Exception as e:  # noqa: BLE001
        return [f"<discovery failed: {type(e).__name__}: {e}>"]


def run_task(base: str, key: str, model: str) -> dict:
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_msg()},
        ],
    }
    t0 = time.time()
    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        dt = time.time() - t0
        if r.status_code != 200:
            return {"ok": False, "err": f"HTTP {r.status_code}: {r.text[:160]}", "dt": dt}
        content = json.loads(r.content.decode("utf-8"))
        text = content["choices"][0]["message"]["content"].strip()
        num_ok, unknown = check_numbers(text)
        return {"ok": True, "dt": dt, "text": text, "num_ok": num_ok, "unknown": unknown}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": f"{type(e).__name__}: {e}", "dt": time.time() - t0}


def main() -> None:
    load_env()
    print("=" * 78)
    print("FREE-MODEL BAKE-OFF — Option 1: rewrite 'The Read' headline")
    print("=" * 78)
    print("\nDeterministic lead being rewritten:")
    print(f"  {DET_HEADLINE}\n")

    any_key = False
    for name, prov in PROVIDERS.items():
        key = key_for(prov)
        print("\n" + "-" * 78)
        print(f"PROVIDER: {name}   ({prov['base']})")
        print("-" * 78)
        if not key:
            print(f"  [skip] no key — set {prov['key_env']} in env/secrets")
            continue
        any_key = True
        print(f"  key: ...{key[-4:]}  (len {len(key)})")
        catalogue = list_models(prov["base"], key)
        chat_models = [m for m in catalogue if not m.startswith("<")]
        if not chat_models:
            print(f"  discovery: {catalogue[0] if catalogue else 'none'}")
        print(f"  {len(chat_models) or '?'} models visible to this key. Testing shortlist:\n")

        for model in prov["models"]:
            available = (not chat_models) or (model in catalogue) or any(
                model in c for c in catalogue
            )
            if not available:
                print(f"  . {model:<32} [not in catalogue — skipped]")
                continue
            res = run_task(prov["base"], key, model)
            if not res["ok"]:
                print(f"  X {model:<32} {res['dt']:.1f}s  {res['err']}")
                continue
            flag = "OK" if res["num_ok"] else f"NEW#{res['unknown']}"
            print(f"  > {model:<32} {res['dt']:.1f}s  [{flag}]")
            print(f"      {res['text']}")
            time.sleep(1)  # be gentle on free-tier rate limits

    print("\n" + "=" * 78)
    print("Full model catalogues (for picking the final model):")
    for name, prov in PROVIDERS.items():
        key = key_for(prov)
        if not key:
            continue
        cat = list_models(prov["base"], key)
        print(f"\n[{name}] {len(cat)} entries:")
        for m in cat:
            print(f"    {m}")

    if not any_key:
        print("\nNo provider keys found in env/secrets.")


if __name__ == "__main__":
    main()
