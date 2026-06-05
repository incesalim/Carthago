"""Send an alert to Telegram and/or Discord. No-op (just logs) if unconfigured.

Stdlib only — safe to call from any workflow without extra deps.

Env (any set → that channel is used):
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID   — Telegram bot (primary)
  ALERT_WEBHOOK_URL                        — Discord (or any {"content": …} webhook)

Usage:
  from notify import notify         # when scripts/ is on sys.path
  notify("BDDK refresh failed: …")
  # or:  python scripts/notify.py "message"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def _post_json(url: str, payload: dict) -> bool:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception as e:  # network / HTTP — never let alerting crash the caller
        print(f"[notify] send failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def notify(text: str) -> bool:
    """Send `text` to every configured channel. Returns True if any send
    succeeded. If nothing is configured, logs to stderr and returns False."""
    sent = False

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        ok = _post_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
        )
        sent = sent or ok

    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        ok = _post_json(webhook, {"content": text[:1900]})
        sent = sent or ok

    if not sent:
        print(f"[notify] (no channel configured) {text}", file=sys.stderr)
    return sent


if __name__ == "__main__":
    # Best-effort: always exit 0 so a missing channel / transient send failure
    # never turns an alert step red on top of the real failure it's reporting.
    msg = " ".join(sys.argv[1:]) or "(test alert from notify.py)"
    notify(msg)
    sys.exit(0)
