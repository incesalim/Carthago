"""Refreshing a capture warning must not broaden into a financial backfill."""
import json
import sqlite3

from scripts.backfill_audit_source_capture import _pending_lanes
from src.audit_reports.schema import init_schema


def test_failed_capture_selection_excludes_accounting_and_missing_lanes():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    for lane, check in [("equity_change", "capture_unmapped_rows"),
                        ("capital", "cap_composition")]:
        conn.execute("INSERT INTO bank_audit_validation "
                     "(bank_ticker, period, kind, statement, checks_failed, failed_detail) "
                     "VALUES ('X','2026Q2','consolidated',?,1,?)",
                     (lane, json.dumps([{"check": check}])))
    lanes = ("equity_change", "capital", "liquidity")
    assert _pending_lanes(conn, "X", "2026Q2", "consolidated", lanes,
                          refresh_existing=True, only_failing=True) == ("equity_change",)
    assert _pending_lanes(conn, "X", "2026Q2", "unconsolidated", lanes,
                          refresh_existing=True, only_failing=True) == ()
