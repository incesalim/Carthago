"""A transient connection reset must not cost a filing.

2026-10-31, both audit dispatches: akbankinvestorrelations.com served AKBNK's
2026Q3 consolidated PDF to the same GitHub runner ten seconds before resetting
the unconsolidated one — `[FAIL] err:ConnectionError` twice, while the host was
demonstrably up. The single-shot `requests.get` turned a per-request reset into
a terminal verdict, and the quarter needed a manual local download → R2 upload
→ extract-only rescue.

`fetch_pdf_bytes` now retries transient `RequestException`s. Pinned here:
  1. reset-then-success returns the body (the AKBNK class, healed);
  2. a permanently refusing host still fails — after three tries, with the
     same `err:<ExceptionName>` note as before, so downstream accounting and
     the systemic-alarm semantics are unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import sync_audit_reports as M  # noqa: E402


class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self.status_code = status
        self.content = body


def _patch_net(monkeypatch, script_get, script_sleep):
    monkeypatch.setattr(M.requests, "get", script_get)
    monkeypatch.setattr(M.time, "sleep", script_sleep)


def test_transient_reset_then_success_returns_body(monkeypatch):
    """One reset, then the PDF — the AKBNK 2026Q3 unconsolidated case."""
    calls, sleeps = [], []

    def fake_get(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("Connection reset by peer")
        return _Resp(b"%PDF-1.4 fake-body")

    _patch_net(monkeypatch, fake_get, sleeps.append)
    body, note = M.fetch_pdf_bytes("https://ir.example/x.pdf", "AKBNK")
    assert body == b"%PDF-1.4 fake-body"
    assert note == "ok"
    assert len(calls) == 2
    assert sleeps == [5]  # first backoff only


def test_permanently_blocked_host_fails_after_three_tries(monkeypatch):
    """denizbank/icbc class: every attempt refused, verdict unchanged."""
    calls, sleeps = [], []

    def fake_get(url, **kwargs):
        calls.append(url)
        raise requests.exceptions.SSLError("handshake failed")

    _patch_net(monkeypatch, fake_get, sleeps.append)
    body, note = M.fetch_pdf_bytes("https://blocked.example/x.pdf", "DENIZ")
    assert body is None
    assert note == "err:SSLError"
    assert len(calls) == 3
    assert sleeps == [5, 10]


def test_http_error_status_does_not_retry(monkeypatch):
    """A definitive HTTP verdict is an answer, not a flake — no retry."""
    calls, sleeps = [], []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _Resp(b"x", 404)

    _patch_net(monkeypatch, fake_get, sleeps.append)
    body, note = M.fetch_pdf_bytes("https://ir.example/gone.pdf", "TEB")
    assert body is None
    assert note == "http:404"
    assert len(calls) == 1
    assert sleeps == []
