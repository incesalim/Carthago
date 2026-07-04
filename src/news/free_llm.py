"""Free OpenAI-compatible LLM client for the "The Read" headline rewrite.

Fallback chain (chosen after the round-3 reliability gauntlet — see
docs/knowledge/free-model-eval-round3.md):
    Cerebras gpt-oss-120b  →  Groq openai/gpt-oss-120b  →  Cerebras gemma-4-31b

Every rewrite is number-validated: it may use ONLY numbers present in the
deterministic facts. Digits bound to a label (Stage-2, CET1, 1-year) are not
claims and are ignored. A rewrite that invents a number, breaks format, or is
empty is rejected and the next provider is tried; if all fail the caller keeps
the deterministic headline.

NOT for the regulations snapshot (that stays on paid Kimi). Env (GitHub secrets
in CI): CEREBRAS_KEY / GROQ_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

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

# Ordered fallback chain. Each entry is OpenAI-compatible. `family` shares a rate
# budget (both cerebras models draw on the same 5-req/min free tier); `min_gap`
# is the seconds to leave between successive calls to that family so the PRIMARY
# (Cerebras) never trips its own limit and we don't fall through to Groq/gemma.
PROVIDERS = [
    {"name": "cerebras/gpt-oss-120b", "family": "cerebras", "min_gap": 13.0,
     "base": "https://api.cerebras.ai/v1",
     "model": "gpt-oss-120b", "keys": ["CEREBRAS_KEY", "CEREBRAS_API_KEY"]},
    {"name": "groq/openai/gpt-oss-120b", "family": "groq", "min_gap": 3.0,
     "base": "https://api.groq.com/openai/v1",
     "model": "openai/gpt-oss-120b", "keys": ["GROQ_API_KEY", "GROQ_API_TOKEN"]},
    {"name": "cerebras/gemma-4-31b", "family": "cerebras", "min_gap": 13.0,
     "base": "https://api.cerebras.ai/v1",
     "model": "gemma-4-31b", "keys": ["CEREBRAS_KEY", "CEREBRAS_API_KEY"]},
]

# Per-family throttle so the primary is used consistently instead of rate-limiting
# into failover. Cerebras free tier = 5 req/min → one call per ~12s (13s margin).
_last_call: dict[str, float] = {}


def _pace(family: str, min_gap: float) -> None:
    wait = _last_call.get(family, 0.0) + min_gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[family] = time.monotonic()

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
DASHES = "-‐‑‒–—"


def _key(provider: dict) -> str | None:
    for env in provider["keys"]:
        if os.environ.get(env):
            return os.environ[env]
    return None


def _strip_reasoning(text: str) -> str:
    text = THINK_RE.sub("", text)
    if "</think>" in text:
        text = text.split("</think>", 1)[-1]
    return text.strip()


def unknown_numbers(text: str, allowed: list[float]) -> list[str]:
    """Numbers in `text` that aren't facts. Label-bound digits (Stage-2, CET1,
    1-year) are skipped on either side."""
    out: list[str] = []
    for m in NUM_RE.finditer(text):
        j = m.start() - 1
        while j >= 0 and text[j] in DASHES:
            j -= 1
        if j >= 0 and text[j].isalpha():
            continue
        k = m.end()
        if k < len(text) and text[k] in DASHES and k + 1 < len(text) and text[k + 1].isalpha():
            continue
        n = float(m.group())
        if not any(abs(n - a) < 0.01 or abs(abs(n) - a) < 0.01 for a in allowed):
            out.append(m.group())
    return out


def _well_formed(text: str) -> bool:
    if not text or "\n" in text:
        return False
    if any(t in text for t in ("**", "`", "##")):
        return False
    if re.match(r"^\s*(here|sure|okay|certainly|as requested|the read)\b", text, re.I):
        return False
    words = len(text.split())
    return 8 <= words <= 60


def _call(provider: dict, key: str, facts: str, headline: str, timeout: int = 60) -> str | None:
    user = (
        "FACTS (the only numbers you may use):\n" + facts
        + "\n\nCURRENT TEMPLATE LEAD (rewrite this):\n" + headline
    )
    payload = {
        "model": provider["model"],
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    _pace(provider["family"], provider["min_gap"])
    r = requests.post(
        f"{provider['base']}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
    body = json.loads(r.content.decode("utf-8"))
    msg = body["choices"][0]["message"]
    return _strip_reasoning((msg.get("content") or "").strip())


def rewrite_headline(headline: str, items: list[str]) -> tuple[str | None, str | None]:
    """Rewrite `headline` using only the numbers in `headline` + `items`.
    Returns (rewrite, model_name) on success, else (None, None)."""
    facts = headline + "\n" + "\n".join(items)
    allowed = [float(x) for x in NUM_RE.findall(facts)]
    for provider in PROVIDERS:
        key = _key(provider)
        if not key:
            continue
        try:
            text = _call(provider, key, facts, headline)
        except Exception as e:  # noqa: BLE001 — try next provider
            print(f"    [{provider['name']}] error: {type(e).__name__}: {e}", flush=True)
            continue
        if not _well_formed(text):
            print(f"    [{provider['name']}] rejected: malformed/empty", flush=True)
            continue
        bad = unknown_numbers(text, allowed)
        if bad:
            print(f"    [{provider['name']}] rejected: invented {bad}", flush=True)
            continue
        return text, provider["name"]
    return None, None
