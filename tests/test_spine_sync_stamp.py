"""The spine-sync stamp (source_freshness 'audit_spine').

push_to_d1 stamps the marker at the single choke point every spine push goes
through. The gate matters as much as the write: a push that did NOT ship the
spine tables must not claim the spine synced (that would hide a stalled
refresh-audit behind an unrelated green push), and no stamp failure may ever
fail the push itself — monitoring telemetry is not load-bearing.
"""
import sys
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

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


# --- one bad filing must not abort the fleet's refresh ------------------------
#
# KLNMA 2025Q4 cons (2026-09-18): loans_by_sector's duplicate guard raised at
# STORE time, and the sync's upsert call was the one per-partition step without
# a guard — so a single unextractable filing rolled back and failed the whole
# run, blocking the spine rebuild and push for every other bank.

def test_store_failure_is_per_partition_not_fleet_fatal(monkeypatch, tmp_path):
    import sync_audit_reports as sync

    def fake_worker(args):
        ticker, period, kind, key, tmp_dir = args
        return (ticker, period, kind, key, True, 40, 40, 10, 40, 0, 1.0, None, object(), "x.pdf")

    calls = {"n": 0}

    def fake_upsert(conn, ticker, period, kind, rep, key, **kw):
        calls["n"] += 1
        if ticker == "BADBNK":
            raise ValueError("duplicate sector/period rows in extracted table")

    class _SerialPool:
        """ProcessPoolExecutor stand-in that runs workers inline — no pickling,
        same submit/result contract (real Futures, for as_completed)."""
        def __init__(self, max_workers=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, fn, arg):
            fut = Future()
            try:
                fut.set_result(fn(arg))
            except Exception as exc:  # noqa: BLE001 — mirrors the worker contract
                fut.set_exception(exc)
            return fut

    monkeypatch.setattr(sync, "ProcessPoolExecutor", _SerialPool)
    monkeypatch.setattr(sync, "_worker_extract", fake_worker)
    monkeypatch.setattr(sync, "upsert_report", fake_upsert)
    monkeypatch.setattr(sync, "UnitContext", SimpleNamespace(for_partition=lambda *a, **k: None))
    monkeypatch.setattr(sync, "list_r2_pdfs", lambda: [
        ("BADBNK", "2025Q4", "consolidated", "k1"),
        ("GOODBNK", "2026Q2", "consolidated", "k2"),
    ])
    monkeypatch.setattr(sync, "already_extracted", lambda db: set())
    monkeypatch.setattr(sync, "record_pdf_validity", lambda db, inv: 0)

    counts = sync.extract_from_r2(workers=1, db_path=tmp_path / "t.db")
    assert counts["fail"] == 1
    assert calls["n"] == 2  # the good partition still stored
