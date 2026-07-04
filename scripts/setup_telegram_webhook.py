"""Register / inspect / remove the Telegram Q&A bot webhook.

The bot lives in the Cloudflare Worker at {WORKER_URL}/api/telegram/webhook
(web/app/api/telegram/webhook/route.ts). Telegram must be told to push updates
there, and to echo a secret token we verify on every request.

Stdlib only. Reads:
  TELEGRAM_BOT_TOKEN       — BotFather token (required)
  TELEGRAM_WEBHOOK_SECRET  — the same secret you `wrangler secret put` on the
                             Worker (required for `set`)
  WORKER_URL               — Worker origin (default: the prod workers.dev URL)

Usage:
  python scripts/setup_telegram_webhook.py gen-secret   # print a random secret
  python scripts/setup_telegram_webhook.py set          # register the webhook
  python scripts/setup_telegram_webhook.py info         # show current webhook
  python scripts/setup_telegram_webhook.py delete       # remove the webhook
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.request

DEFAULT_WORKER = "https://turkish-banking-dashboard.incesalim10.workers.dev"


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _token() -> str:
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        sys.exit("TELEGRAM_BOT_TOKEN is not set.")
    return t


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "info"

    if cmd == "gen-secret":
        print(secrets.token_urlsafe(32))
        return 0

    token = _token()

    if cmd == "set":
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not secret:
            sys.exit("TELEGRAM_WEBHOOK_SECRET is not set (run `gen-secret` first, "
                     "then `wrangler secret put TELEGRAM_WEBHOOK_SECRET` with the same value).")
        worker = os.environ.get("WORKER_URL", DEFAULT_WORKER).rstrip("/")
        url = f"{worker}/api/telegram/webhook"
        resp = _api(token, "setWebhook", {
            "url": url,
            "secret_token": secret,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        })
        print(json.dumps(resp, indent=2))
        return 0 if resp.get("ok") else 1

    if cmd == "delete":
        resp = _api(token, "deleteWebhook", {"drop_pending_updates": True})
        print(json.dumps(resp, indent=2))
        return 0 if resp.get("ok") else 1

    if cmd == "info":
        print(json.dumps(_api(token, "getWebhookInfo"), indent=2))
        return 0

    sys.exit(f"unknown command: {cmd!r} (use gen-secret | set | info | delete)")


if __name__ == "__main__":
    raise SystemExit(main())
