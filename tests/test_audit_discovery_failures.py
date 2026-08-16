"""A failed discovery must not look like a bank that has not filed.

`discover_targets` is fail-safe on purpose — a dead IR page must never take the
sync down — but returning `[]` collapsed two different facts into one, and the
caller could not tell them apart. VAKIFK's 2026Q2 went unacquired for nine days
behind exactly that: its host answers a Turkish address and times out from the
GitHub runner, so every run logged one stderr line and fell back to a static
config with no 2026Q2 entry, while `new=0` reported the lane healthy.

The fallback stays. What changes is that the failure is now countable.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from src.audit_reports import discovery  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_failures():
    discovery.DISCOVERY_FAILURES.clear()
    yield
    discovery.DISCOVERY_FAILURES.clear()


def test_a_failed_discovery_still_returns_empty(monkeypatch):
    """The fail-safe is the point — the sync must survive a dead IR page."""
    def boom(ticker, cfg):
        raise TimeoutError("connect timeout=60")

    monkeypatch.setattr(discovery, "discover_from_ir", boom)
    assert discovery.discover_targets("VAKIFK", {}) == []


def test_a_failed_discovery_is_recorded(monkeypatch):
    def boom(ticker, cfg):
        raise TimeoutError("connect timeout=60")

    monkeypatch.setattr(discovery, "discover_from_ir", boom)
    discovery.discover_targets("VAKIFK", {})
    assert discovery.DISCOVERY_FAILURES == [("VAKIFK", "TimeoutError: connect timeout=60")]


def test_a_bank_outside_discovery_is_not_a_failure():
    """25 of 38 banks are not enabled. That is a config decision, not a fault,
    and counting it would bury the real ones."""
    assert discovery.discover_targets("ISCTR", {}) == []
    assert discovery.DISCOVERY_FAILURES == []


def test_a_successful_discovery_records_nothing(monkeypatch):
    monkeypatch.setattr(discovery, "discover_from_ir",
                        lambda t, c: [("2026Q2", "consolidated", "u")])
    assert discovery.discover_targets("ZIRAAT", {}) != []
    assert discovery.DISCOVERY_FAILURES == []


def test_the_failure_reaches_the_workflow_through_the_result_file(tmp_path, monkeypatch):
    """The run summary is where this has to surface: the scrape counts cannot
    show it (an unattempted target is in no denominator) and Telegram must not
    (a geo-blocked host fails every day, and a daily ping gets muted)."""
    spec = importlib.util.spec_from_file_location(
        "sync_disc", REPO / "scripts" / "sync_audit_reports.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)

    cfg = tmp_path / "urls.json"
    cfg.write_text(json.dumps({"banks": {"VAKIFK": {"urls": {}}}}), encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)

    def boom(ticker, bank_cfg):
        M.DISCOVERY_FAILURES.append((ticker, "TimeoutError: connect timeout=60"))
        return []

    monkeypatch.setattr(M, "discover_targets", boom)
    M.DISCOVERY_FAILURES.clear()
    M.scrape_to_r2(workers=1, db_path=None)
    assert M.DISCOVERY_FAILURES == [("VAKIFK", "TimeoutError: connect timeout=60")]

    # ...and the workflow reads it from there.
    wf = (REPO / ".github" / "workflows" / "refresh-audit.yml").read_text(
        encoding="utf-8")
    assert "discovery_failures" in wf
    assert "::warning title=Discovery fell back to static config::" in wf
