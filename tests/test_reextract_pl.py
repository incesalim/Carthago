"""Legacy P&L repair pushes its role sidecar only when the map changes."""
import gzip
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fitz")

from scripts import reextract_pl as repair  # noqa: E402
from src.audit_reports.extractor import StatementRow  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.units import UnitContext  # noqa: E402

B, P, K = "TEST", "2026Q2", "unconsolidated"


@pytest.mark.parametrize("old_hierarchy", ["XXV.", None, "XXIV."])
def test_main_pushes_roles_only_when_content_changed(tmp_path, monkeypatch, old_hierarchy):
    seed = tmp_path / "seed.db"
    with sqlite3.connect(seed) as conn:
        init_schema(conn)
        conn.execute(
            "INSERT INTO bank_audit_profit_loss "
            "(bank_ticker, period, kind, item_order, hierarchy, item_name, amount) "
            "VALUES (?,?,?,?,?,?,?)", (B, P, K, 20, "XXV.", "NET PROFIT", 42))
        if old_hierarchy is not None:
            conn.execute(
                "INSERT INTO bank_audit_pl_roles "
                "(bank_ticker, period, kind, hierarchy, role, derived_at) "
                "VALUES (?,?,?,?,?,?)",
                (B, P, K, old_hierarchy, "period_net", "2026-01-01 00:00:00"))
    snapshot = gzip.compress(seed.read_bytes())
    db = tmp_path / "audit.db"
    monkeypatch.setattr(repair, "DB", db)
    monkeypatch.setattr(repair, "GZ", tmp_path / "audit.db.gz")
    monkeypatch.setattr(repair, "_guard_against_ci_writers", lambda: None)

    def download(key, destination):
        Path(destination).write_bytes(snapshot if key == repair.SNAP else b"mock PDF")

    monkeypatch.setattr(repair.r2_storage, "download_to", download)
    monkeypatch.setattr(repair.r2_storage, "upload_file", lambda path, key: Path(path).stat().st_size)
    # Enough rows to pass this legacy command's existing row-count guard; only
    # the last row is a semantic anchor. The amount changes in every case while
    # the old role map may be correct, absent, or stale.
    report = SimpleNamespace(profit_loss=[
        *[StatementRow(order=i, hierarchy=f"1.{i}", name="Interest income",
                       footnote=None, cur_amount=i) for i in range(1, 20)],
        StatementRow(order=20, hierarchy="XXV.", name="NET PROFIT",
                     footnote=None, cur_amount=99),
    ])
    monkeypatch.setattr(repair, "extract", lambda path: report)
    monkeypatch.setattr(repair.UnitContext, "for_partition", lambda *args: UnitContext.canonical())
    pushes = []
    monkeypatch.setattr(repair, "replace_partitions", lambda *args: pushes.append(args))
    monkeypatch.setattr(sys, "argv", ["reextract_pl", "--bank", B, "--period", P, "--kind", K])

    assert repair.main() == 0
    expected_tables = ["bank_audit_profit_loss"]
    if old_hierarchy != "XXV.":
        expected_tables.append("bank_audit_pl_roles")
    assert pushes == [([(B, P, K)], db, expected_tables)]
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT hierarchy, role FROM bank_audit_pl_roles").fetchall() == [
                ("XXV.", "period_net")]
        assert conn.execute(
            "SELECT amount FROM bank_audit_profit_loss WHERE hierarchy='XXV.'").fetchone() == (99,)
        if old_hierarchy == "XXV.":
            assert conn.execute("SELECT derived_at FROM bank_audit_pl_roles").fetchone() == (
                "2026-01-01 00:00:00",)
