#!/usr/bin/env python3
"""Scratch probe: does the `OPEN_ROUTER_API` secret actually work, and what do
the DeepSeek models cost?

The key was added as a repo secret on 2026-07-05 and has never been read by any
code in this repo — so "we have an OpenRouter key" was, until this ran, an
untested claim. Secrets are CI-only (never local), hence a dispatch workflow
rather than a local run.

Four questions, cheapest first, each gating the next:

  1. does the key authenticate at all?          GET  /api/v1/key
  2. what credit / rate budget does it have?    (same response)
  3. which DeepSeek models exist, at what $?    GET  /api/v1/models
  4. does a real completion actually come back? POST /api/v1/chat/completions
     ...and what did it really cost?            GET  /api/v1/generation

Step 4 deliberately runs OUR prompt, not "say hello": it replays a "The Read"
headline rewrite through `src/news/free_llm.py`'s own `unknown_numbers` +
`_well_formed` validators, including a derive-the-buffer number trap. A model
that authenticates but invents figures is useless to this repo, and that is
exactly what the round-3 gauntlet rejected llama-4-scout for. See
docs/knowledge/free-model-eval-round3.md.

Scratch by design (sibling of the removed `scratch_test_free_models.py`):
delete it once the finding is written down.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.news.free_llm import SYSTEM, NUM_RE, _well_formed, unknown_numbers  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
# OpenRouter attributes usage to a referring app; harmless but keeps the
# dashboard readable if this ever becomes a real lane.
HEADERS_EXTRA = {
    "HTTP-Referer": "https://carthago.app",
    "X-Title": "carthago",
}

# A real Read, with a trap: the CAR buffer (18.1 - 12.0 = 6.1) is NOT in the
# facts. A model that prints 6.1 is deriving a figure it was told not to.
FACTS_HEADLINE = (
    "Sector profitability improved in the quarter as funding costs eased."
)
FACTS_ITEMS = [
    "Sector ROE 28.4%, up 3.1pp q/q",
    "Net interest margin 4.2%, up 0.6pp q/q",
    "Deposit cost 41.5%, down 5.2pp q/q",
    "Capital adequacy ratio 18.1% against a 12.0% requirement",
    "Stage-2 loans 8.7% of gross loans",
]


def _key() -> str | None:
    return os.environ.get("OPEN_ROUTER_API") or os.environ.get("OPENROUTER_API_KEY")


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **HEADERS_EXTRA}


def check_key(key: str) -> bool:
    """Q1+Q2 — does it authenticate, and what is the budget?"""
    print("== 1. key ==", flush=True)
    r = requests.get(f"{BASE}/key", headers=_auth(key), timeout=30)
    if r.status_code != 200:
        print(f"  FAIL HTTP {r.status_code}: {r.text[:300]}")
        return False
    d = r.json().get("data", {})
    usage, limit = d.get("usage"), d.get("limit")
    print(f"  OK  label={d.get('label')!r}  free_tier={d.get('is_free_tier')}")
    print(f"      usage=${usage}  limit={'unlimited (pay-as-you-go)' if limit is None else f'${limit}'}")
    if limit is not None and usage is not None:
        print(f"      remaining=${limit - usage:.4f}")
    if d.get("rate_limit"):
        print(f"      rate_limit={d['rate_limit']}")
    return True


def deepseek_models(key: str) -> list[dict]:
    """Q3 — which DeepSeek models does this account see, and at what price?

    Discovered, never hardcoded: OpenRouter renames/retires DeepSeek ids often
    enough (deepseek-chat → -v3-0324 → -v3.x) that a literal id in this repo
    would be a future 404.
    """
    print("\n== 2. deepseek models ==", flush=True)
    r = requests.get(f"{BASE}/models", headers=_auth(key), timeout=30)
    r.raise_for_status()
    models = [m for m in r.json()["data"] if m["id"].startswith("deepseek/")]

    def price(m: dict) -> tuple[float, float]:
        p = m.get("pricing") or {}
        return float(p.get("prompt") or 0), float(p.get("completion") or 0)

    models.sort(key=lambda m: (price(m)[0], price(m)[1]))
    print(f"  {len(models)} deepseek model(s) visible")
    print(f"  {'id':<44} {'$/Mtok in':>10} {'$/Mtok out':>11} {'ctx':>9}")
    for m in models:
        pin, pout = price(m)
        print(f"  {m['id']:<44} {pin * 1e6:>10.3f} {pout * 1e6:>11.3f} {m.get('context_length', 0):>9,}")
    return models


def try_completion(key: str, model_id: str) -> bool:
    """Q4 — a real call, validated by the repo's own guardrails."""
    print(f"\n== 3. completion: {model_id} ==", flush=True)
    facts = FACTS_HEADLINE + "\n" + "\n".join(FACTS_ITEMS)
    allowed = [float(x) for x in NUM_RE.findall(facts)]
    payload = {
        "model": model_id,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "FACTS (the only numbers you may use):\n" + facts
                + "\n\nCURRENT TEMPLATE LEAD (rewrite this):\n" + FACTS_HEADLINE,
            },
        ],
    }
    t0 = time.monotonic()
    r = requests.post(f"{BASE}/chat/completions", headers=_auth(key), json=payload, timeout=120)
    elapsed = time.monotonic() - t0
    if r.status_code != 200:
        print(f"  FAIL HTTP {r.status_code}: {r.text[:400]}")
        return False

    body = r.json()
    if body.get("error"):  # OpenRouter can 200 with an error envelope
        print(f"  FAIL error envelope: {json.dumps(body['error'])[:400]}")
        return False
    msg = body["choices"][0]["message"]
    text = (msg.get("content") or "").strip()
    usage = body.get("usage") or {}

    print(f"  HTTP 200 in {elapsed:.1f}s  provider={body.get('provider')}")
    print(f"  tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}")
    if msg.get("reasoning"):
        print(f"  NOTE reasoning field present ({len(msg['reasoning'])} chars) — provider exposes it separately")
    print(f"  output: {text!r}")

    if not text:
        print("  REJECT empty content (reasoning likely ate the token budget)")
        return False
    ok_form = _well_formed(text)
    bad = unknown_numbers(text, allowed)
    print(f"  well_formed={ok_form}  invented_numbers={bad or 'none'}")
    if "6.1" in text:
        print("  ^ NOTE 6.1 = the derived CAR buffer trap (18.1-12.0). Not in the facts.")

    # Q4b — what it actually cost, from OpenRouter's own accounting.
    gen_id = body.get("id")
    if gen_id:
        time.sleep(2)  # generation stats settle a moment after the response
        g = requests.get(f"{BASE}/generation", headers=_auth(key), params={"id": gen_id}, timeout=30)
        if g.status_code == 200:
            gd = g.json().get("data", {})
            print(f"  actual cost: ${gd.get('total_cost')}  native_tokens="
                  f"{gd.get('native_tokens_prompt')}+{gd.get('native_tokens_completion')}")
        else:
            print(f"  (generation stats unavailable: HTTP {g.status_code})")

    return ok_form and not bad


def main() -> int:
    key = _key()
    if not key:
        print("OPEN_ROUTER_API is not set — nothing to test.", file=sys.stderr)
        return 1
    print(f"key present: {len(key)} chars, prefix {key[:8]}...\n")

    if not check_key(key):
        return 1

    models = deepseek_models(key)
    if not models:
        print("\nNo deepseek models visible to this key.", file=sys.stderr)
        return 1

    # Test the cheapest free variant (if any) and the cheapest paid one: free
    # proves the key works without credits, paid proves the account can bill.
    free = [m for m in models if float((m.get("pricing") or {}).get("prompt") or 0) == 0]
    paid = [m for m in models if float((m.get("pricing") or {}).get("prompt") or 0) > 0]
    targets = [m["id"] for m in (free[:1] + paid[:1])]
    override = os.environ.get("MODEL_ID")
    if override:
        targets = [override]

    results = {mid: try_completion(key, mid) for mid in targets}

    print("\n== summary ==")
    for mid, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {mid}")
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
