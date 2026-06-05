"""Tests for scripts/notify.py — the alert helper must never crash the caller
and must no-op safely when no channel is configured."""
import importlib

import notify  # provided on sys.path via pyproject pythonpath = ["scripts", "."]


def test_no_channel_returns_false(monkeypatch):
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ALERT_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(notify)
    assert notify.notify("hello") is False  # nothing configured → no-op


def test_send_failure_is_swallowed(monkeypatch):
    # Configure a channel but make the POST fail — notify must return False,
    # not raise, so a failing alert never masks the real failure it reports.
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.invalid/hook")
    importlib.reload(notify)
    monkeypatch.setattr(notify, "_post_json", lambda url, payload: False)
    assert notify.notify("boom") is False
