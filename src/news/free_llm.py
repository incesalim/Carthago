"""OpenAI-compatible LLM client for the "The Read" headline rewrite.

Fallback chain, then the deterministic template as the ultimate safety net (the
caller keeps the deterministic headline when every provider fails):
    OpenRouter deepseek-v4-flash @Baidu  →  Cerebras gpt-oss-120b
      →  Groq openai/gpt-oss-120b  →  (deterministic template)

⚠️ THE HEAD OF THIS CHAIN IS PAID, and adding it deliberately gave up a property
this module was built around. The round-3 reliability gauntlet
(docs/knowledge/free-model-eval-round3.md) picked the SAME model on two
independent providers precisely so that a shown LLM headline always sounds the
same, whichever provider answered. With deepseek-flash in front, a headline
written on a Baidu outage is a DIFFERENT VOICE from one written normally — an
accepted cost of the 2026-08-17 decision to lead every lane with deepseek-flash,
not an oversight. The number validator below is unchanged and still the thing
that makes any of these providers safe.

Every rewrite is number-validated: it may use ONLY numbers present in the
deterministic facts. Digits bound to a label (Stage-2, CET1, 1-year) are not
claims and are ignored. A rewrite that invents a number, breaks format, or is
empty is rejected and the next provider is tried; if all fail the caller keeps
the deterministic headline.

Env (GitHub secrets in CI): OPEN_ROUTER_API / CEREBRAS_KEY / GROQ_API_KEY.
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

# Ordered fallback chain. deepseek-flash leads; behind it the two free providers
# serve the SAME model (gpt-oss-120b), so a fallback headline at least sounds the
# same as another fallback headline. If all three fail the caller keeps the
# deterministic template.
#
# `family` shares a provider rate budget; `min_gap` is the seconds between
# successive calls to that family so a provider stays under its limit instead of
# failing over (Cerebras free tier = 5 req/min → one call per ~12s, 13s margin).
# OpenRouter is metered rather than rate-capped here, so it needs no gap.
#
# `headers`/`params` are merged per provider: OpenRouter wants app attribution,
# and the upstream pin is not optional — unpinned it draws from ~8 providers whose
# quality, price and even PARAMETER SUPPORT differ. allow_fallbacks=False stops
# OpenRouter substituting an upstream; it does NOT disable the chain below, so a
# Baidu outage still falls through to the free models and then to the template.
PROVIDERS = [
    {"name": "openrouter/deepseek-v4-flash", "family": "openrouter", "min_gap": 0.0,
     "base": "https://openrouter.ai/api/v1",
     "model": "deepseek/deepseek-v4-flash",
     "keys": ["OPEN_ROUTER_API", "OPENROUTER_API_KEY"],
     "headers": {"HTTP-Referer": "https://carthago.app", "X-Title": "carthago"},
     "params": {"provider": {"order": ["Baidu"], "allow_fallbacks": False},
                "seed": 1729}},
    {"name": "cerebras/gpt-oss-120b", "family": "cerebras", "min_gap": 13.0,
     "base": "https://api.cerebras.ai/v1",
     "model": "gpt-oss-120b", "keys": ["CEREBRAS_KEY", "CEREBRAS_API_KEY"]},
    {"name": "groq/openai/gpt-oss-120b", "family": "groq", "min_gap": 3.0,
     "base": "https://api.groq.com/openai/v1",
     "model": "openai/gpt-oss-120b", "keys": ["GROQ_API_KEY", "GROQ_API_TOKEN"]},
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


class _RateLimited(Exception):
    """A 429 — retry the SAME provider (so we keep using the primary) rather than
    immediately failing over."""

    def __init__(self, retry_after: float | None = None):
        super().__init__("rate limited")
        self.retry_after = retry_after


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
        # Match on MAGNITUDE: a fact printed negative (e.g. "-7.3pp real") that the
        # model phrases positive ("7.3pp below inflation") is the same figure, not
        # an invention. The deterministic bullets still carry the correct sign.
        if not any(abs(abs(n) - abs(a)) < 0.01 for a in allowed):
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
        **provider.get("params", {}),
    }
    _pace(provider["family"], provider["min_gap"])
    r = requests.post(
        f"{provider['base']}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 **provider.get("headers", {})},
        json=payload,
        timeout=timeout,
    )
    if r.status_code == 429:
        ra = r.headers.get("retry-after")
        try:
            retry_after = float(ra) if ra else None
        except ValueError:
            retry_after = None
        raise _RateLimited(retry_after)
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
        # Retry THIS provider on 429 (with backoff) before failing over, so the
        # primary is used consistently rather than rate-limiting into a backup.
        text: str | None = None
        for attempt in range(3):
            try:
                text = _call(provider, key, facts, headline)
                break
            except _RateLimited as rl:
                wait = min(rl.retry_after or 6.0 * (attempt + 1), 25.0)
                print(f"    [{provider['name']}] 429 — waiting {wait:.0f}s "
                      f"(attempt {attempt + 1}/3)", flush=True)
                time.sleep(wait)
            except Exception as e:  # noqa: BLE001 — non-429 error → next provider
                print(f"    [{provider['name']}] error: {type(e).__name__}: {e}", flush=True)
                break
        if text is None:
            continue  # persistently rate-limited or errored → next provider
        if not _well_formed(text):
            print(f"    [{provider['name']}] rejected: malformed/empty", flush=True)
            continue
        bad = unknown_numbers(text, allowed)
        if bad:
            print(f"    [{provider['name']}] rejected: invented {bad}", flush=True)
            continue
        return text, provider["name"]
    return None, None
