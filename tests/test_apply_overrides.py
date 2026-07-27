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


# --- capital: which period column an override lands on ----------------------

def _ins_capital(c, period_type, cet1, bank="X", period="2024Q2",
                 kind="consolidated"):
    c.execute(
        "INSERT INTO bank_audit_capital (bank_ticker, period, kind, period_type, "
        "cet1_capital) VALUES (?,?,?,?,?)", (bank, period, kind, period_type, cet1))
    c.commit()


def _capital(c):
    return dict(c.execute(
        "SELECT period_type, cet1_capital FROM bank_audit_capital").fetchall())


def _capital_override(**extra):
    return {"bank_ticker": "X", "period": "2024Q2", "kind": "consolidated",
            "statement": "capital", "fields": {"cet1_capital": 270336203}, **extra}


def test_capital_override_defaults_to_the_current_column():
    """Every capital override authored before 2026-07-27 omits period_type and
    means the current column. That must not change."""
    c = _conn()
    _ins_capital(c, "current", 1)
    _ins_capital(c, "prior", 2)
    apply_overrides._apply_one(c, _capital_override())
    assert _capital(c) == {"current": 270336203, "prior": 2}


def test_capital_override_can_target_the_prior_column():
    """A section-4 prior column re-prints the prior YEAR-END, so a bad quarter is
    provable against the other three quarters of the following year (ISCTR 2024Q2
    CET1). Before this, such an override silently patched the CURRENT row —
    corrupting a correct figure and leaving the wrong one in place."""
    c = _conn()
    _ins_capital(c, "current", 305357338)
    _ins_capital(c, "prior", 270336.203)
    apply_overrides._apply_one(c, _capital_override(period_type="prior"))
    assert _capital(c) == {"current": 305357338, "prior": 270336203}


def test_capital_override_matching_no_row_says_so():
    """An override that matches nothing leaves the wrong value in place while the
    run reports success — the silent no-op this repo has paid for before."""
    c = _conn()
    _ins_capital(c, "current", 1)
    msg = apply_overrides._apply_one(c, _capital_override(period_type="prior"))
    assert "NO MATCH" in msg


def test_credit_quality_override_targets_the_named_period_column():
    """The DENIZ 2023Q4 shape: the defect is in the prior column, and the current
    one for the same section must be left alone."""
    c = _conn()
    for pt, stage2 in (("current", -2386482.0), ("prior", -535.779)):
        c.execute(
            "INSERT INTO bank_audit_credit_quality (bank_ticker, period, kind, "
            "section, period_type, stage2_amount) VALUES (?,?,?,?,?,?)",
            ("X", "2023Q4", "consolidated", "loans_ecl_expense", pt, stage2))
    c.commit()
    apply_overrides._apply_one(c, {
        "bank_ticker": "X", "period": "2023Q4", "kind": "consolidated",
        "statement": "credit_quality", "section": "loans_ecl_expense",
        "period_type": "prior", "fields": {"stage2_amount": -535779},
    })
    assert dict(c.execute("SELECT period_type, stage2_amount FROM "
                          "bank_audit_credit_quality").fetchall()) == {
        "current": -2386482.0, "prior": -535779}
