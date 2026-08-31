"""Manual refresh filters constrain PDF reads as well as financial extraction."""
import sqlite3
from types import SimpleNamespace

import pytest

import backfill_document_capture as capture
from src.audit_reports import r2_storage


@pytest.mark.parametrize("banks,period,expected", [
    (" icbct, DENIZ ", "2026Q2", {0, 1, 2}),
    (None, None, {0, 1, 2, 3, 4}),  # scheduled recent-filings behavior
])
def test_capture_reads_only_requested_recent_partitions(tmp_path, monkeypatch,
                                                       banks, period, expected):
    targets = [
        ("ICBCT", "2026Q2", "consolidated", "icbc-current-cons"),
        ("ICBCT", "2026Q2", "unconsolidated", "icbc-current-unco"),
        ("DENIZ", "2026Q2", "unconsolidated", "deniz-current"),
        ("AKBNK", "2026Q2", "unconsolidated", "other-bank"),
        ("ICBCT", "2026Q1", "unconsolidated", "other-quarter"),
        ("DENIZ", "2026Q2", "consolidated", "outside-recent-window"),
    ]
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE bank_audit_extractions "
                     "(bank_ticker,period,kind,success,extracted_at)")
        for i, (bank, quarter, kind, _) in enumerate(targets):
            conn.execute("INSERT INTO bank_audit_extractions VALUES (?,?,?,1,datetime('now',?))",
                         (bank, quarter, kind, "-200 hours" if i == 5 else "-1 hours"))
    reads = []

    def download(key, destination):
        reads.append(key)
        destination.write_bytes(b"fixture")

    monkeypatch.setattr(capture, "_r2_targets", lambda: targets)
    monkeypatch.setattr(r2_storage, "download_to", download)
    monkeypatch.setattr(capture, "capture_document", lambda _: SimpleNamespace(
        pages=[], page_count=0, line_count=0, cell_count=0, note_count=0,
        block_count=0, status="captured"))
    argv = ["capture", "--from-r2", "--recent-hours", "168", "--audit-db", str(db), "--dry-run"]
    if banks:
        argv += ["--bank", banks]
    if period:
        argv += ["--period", period]
    monkeypatch.setattr(capture.sys, "argv", argv)
    assert capture.main() == 0
    assert reads == [target[3] for i, target in enumerate(targets) if i in expected]

