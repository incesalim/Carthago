"""Kimi (Moonshot AI) API client.

OpenAI-compatible chat-completions interface. We use it for the weekly
regulatory-briefing summarizer — JSON-mode output, low temperature for
reproducibility.

Env vars:
  KIMI_API_KEY   — required. Set in GitHub Secrets for the cron.
  KIMI_API_URL   — optional. Defaults to https://api.moonshot.ai/v1/chat/completions.
                   Override to api.moonshot.cn if you're on the CN endpoint.
  KIMI_MODEL     — optional. Defaults to "moonshot-v1-32k" (32K context, cheapest
                   model that fits our 90-day briefing window). Switch to
                   "moonshot-v1-128k" if you ever extend the window past
                   ~150 items.
"""
from __future__ import annotations

import json
import os
import time

import requests

DEFAULT_API_URL = "https://api.moonshot.ai/v1/chat/completions"
# Default to 128k context — gives comfortable headroom for the 365-day
# briefing window (~30K input tokens). Cost is ~$7/year at weekly cadence,
# still negligible. Override via KIMI_MODEL env var if needed.
DEFAULT_MODEL = "moonshot-v1-128k"


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    json_object: bool = False,
    timeout: int = 180,
    retries: int = 2,
) -> dict:
    """One-shot chat completion. Returns the parsed response.

    `json_object=True` asks Kimi to return strict JSON in `choices[0].message.content`
    (OpenAI-compatible `response_format` flag). The caller is responsible for
    json.loads-ing the result.
    """
    api_key = os.environ.get("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY is not set")
    # `or DEFAULT`, not `get(k, DEFAULT)`: CI sets these to "" when the driving
    # input/variable is unset, and an empty string is not absent — it would post to
    # "" and send an empty model. Same trap SITE_URL hit in generate-reads.yml.
    url = os.environ.get("KIMI_API_URL") or DEFAULT_API_URL
    payload: dict = {
        "model": model or os.environ.get("KIMI_MODEL") or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}

    # OpenRouter only (Moonshot ignores it; we send it only when asked). OpenRouter
    # fronts one model with many upstream providers whose speed, quantization and
    # even PARAMETER SUPPORT differ — one serves deepseek-v4-flash with no
    # response_format at all, which would silently break json_object mode. Unpinned,
    # every call is a fresh draw: measured 8 providers in an hour, output ranging
    # 7-4,436 tokens, and a ~40% cost premium over the cheapest tier.
    # allow_fallbacks=false is deliberate: a wrong/unavailable name then FAILS
    # loudly instead of quietly substituting another provider.
    order = os.environ.get("LLM_PROVIDER_ORDER", "").strip()
    if order:
        payload["provider"] = {
            "order": [p.strip() for p in order.split(",") if p.strip()],
            "allow_fallbacks": os.environ.get("LLM_ALLOW_FALLBACKS", "").lower() == "true",
        }

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            r.raise_for_status()
            # Decode as UTF-8 explicitly: Moonshot's response omits a charset,
            # so requests' r.json() guesses (often latin-1) and mangles Turkish
            # characters ("Türkiye" -> "TÃ¼rkiye"). Decode the raw bytes.
            return json.loads(r.content.decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Kimi request failed after {retries + 1} attempts: {last_err}")


def extract_text(response: dict) -> str:
    """Pull the content string out of a Kimi response."""
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Kimi response shape: {json.dumps(response)[:300]}") from e


def extract_json(response: dict) -> dict | list:
    """Pull and parse a JSON-mode response."""
    txt = extract_text(response)
    # Kimi sometimes wraps the JSON in a ```json ... ``` block despite json_object mode.
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.split("```", 2)[1]
        if txt.startswith("json"):
            txt = txt[4:]
    return json.loads(txt.strip())
