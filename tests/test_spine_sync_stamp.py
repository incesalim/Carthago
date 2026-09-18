"""The spine-sync stamp (source_freshness 'audit_spine').

push_to_d1 stamps the marker at the single choke point every spine push goes
through. The gate matters as much as the write: a push that did NOT ship the
spine tables must not claim the spine synced (that would hide a stalled
refresh-audit behind an unrelated green push), and no stamp failure may ever
fail the push itself — monitoring telemetry is not load-bearing.
"""
import sys
from pathlib import Path

import push_to_d1
import scripts.healthcheck as scripts_healthcheck
from src.audit_reports import registry

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _capture(monkeypatch):
    calls = []

    def fake_write(source, f):
        calls.append((source, dict(f)))

    # stamp_spine_sync resolves `scripts.healthcheck` lazily — patch THAT
    # module object, not the pythonpath alias `healthcheck` (a second identity).
    monkeypatch.setattr(scripts_healthcheck, "write_freshness", fake_write)
    return calls


def test_a_push_shipping_the_spine_stamps_the_marker(monkeypatch):
    calls = _capture(monkeypatch)
    push_to_d1.stamp_spine_sync({"bank_audit_statement_types", "bank_audit_coverage"})
    assert len(calls) == 1
    source, f = calls[0]
    assert source == "audit_spine"
    assert f["status"] == "ok"
    assert f["latest_period"] == str(len(registry.REGISTRY))
    assert f"{len(registry.REGISTRY)} registry lanes" in f["note"]


def test_an_everything_push_stamps_the_marker(monkeypatch):
    calls = _capture(monkeypatch)
    push_to_d1.stamp_spine_sync(None)
    assert len(calls) == 1


def test_a_push_without_spine_tables_stamps_nothing(monkeypatch):
    calls = _capture(monkeypatch)
    push_to_d1.stamp_spine_sync({"bank_audit_balance_sheet", "bank_audit_extractions"})
    assert calls == []


def test_a_stamp_failure_never_fails_the_push(monkeypatch):
    def boom(_source, _f):
        raise RuntimeError("wrangler down")
    monkeypatch.setattr(scripts_healthcheck, "write_freshness", boom)
    push_to_d1.stamp_spine_sync({"bank_audit_statement_types"})  # must not raise
