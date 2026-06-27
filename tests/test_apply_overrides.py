"""Regression tests for scripts/apply_overrides._apply_one.

Pure-sqlite (no R2 / D1 / wrangler), so they run under CI's minimal deps.
"""
import sqlite3

import pytest

from src.audit_reports.schema import init_schema

apply_overrides = pytest.importorskip("apply_overrides")  # scripts/ on pythonpath


def _conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _ins(c, hierarchy, total, item_order=1, bank="X", period="2024Q4",
         kind="unconsolidated", statement="assets"):
    c.execute(
        "INSERT INTO bank_audit_balance_sheet (bank_ticker, period, kind, statement, "
        "item_order, hierarchy, item_name, amount_tl, amount_fc, amount_total) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (bank, period, kind, statement, item_order, hierarchy, hierarchy, 0, 0, total))
    c.commit()


def test_trailing_dot_override_updates_not_inserts():
    # The stored key is normalised ("1.3.2"); an override authored against the
    # pre-normalisation key ("1.3.2.") must UPDATE the existing row, not insert a
    # phantom duplicate that double-counts under the 1.3 parent.
    c = _conn()
    _ins(c, "1.3.2", 100)
    apply_overrides._apply_one(c, {
        "bank_ticker": "X", "period": "2024Q4", "kind": "unconsolidated",
        "statement": "assets", "hierarchy": "1.3.2.", "item_name": "Equity Securities",
        "amount_tl": 40, "amount_fc": 60, "amount_total": 100,
    })
    rows = c.execute("SELECT hierarchy, amount_total FROM bank_audit_balance_sheet "
                     "WHERE statement='assets'").fetchall()
    assert rows == [("1.3.2", 100)]  # one row, updated in place — no duplicate


def test_exact_match_still_updates():
    c = _conn()
    _ins(c, "2.5", 200)
    apply_overrides._apply_one(c, {
        "bank_ticker": "X", "period": "2024Q4", "kind": "unconsolidated",
        "statement": "assets", "hierarchy": "2.5", "item_name": "ECL",
        "amount_tl": 50, "amount_fc": 150, "amount_total": 999,
    })
    rows = c.execute("SELECT COUNT(*), MAX(amount_total) FROM bank_audit_balance_sheet").fetchone()
    assert rows == (1, 999)
