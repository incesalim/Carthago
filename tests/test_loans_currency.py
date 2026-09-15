"""Tests for the loans_currency extractor and DB upsert."""
from __future__ import annotations

import sqlite3

from src.audit_reports.loans_currency import (
    CurrencyRow,
    LoansCurrencyReport,
    upsert,
)
from src.audit_reports.units import UnitContext


# ---------------------------------------------------------------------------
# Dataclass basics
# ---------------------------------------------------------------------------

def test_currency_row_defaults():
    r = CurrencyRow(sector="agri_total")
    assert r.tl_amount is None
    assert r.fc_amount is None
    assert r.tl_pct is None
    assert r.fc_pct is None
    assert r.period_type == "current"
    assert r.page == 0
    assert r.raw_label == ""


def test_report_defaults():
    rep = LoansCurrencyReport(pdf_path="/tmp/test.pdf")
    assert rep.rows == []


# ---------------------------------------------------------------------------
# DB upsert roundtrip
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE bank_audit_loans_currency (
    bank_ticker TEXT NOT NULL, period TEXT NOT NULL, kind TEXT NOT NULL,
    sector TEXT NOT NULL, period_type TEXT NOT NULL, source_page INTEGER,
    tl_amount REAL, fc_amount REAL, tl_pct REAL, fc_pct REAL,
    raw_label TEXT, extracted_at TEXT,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def _unit() -> UnitContext:
    return UnitContext("bin", 1)


def test_upsert_roundtrip():
    conn = _conn()
    rep = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42, raw_label="Tarım"),
        CurrencyRow(sector="total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42, raw_label="Toplam"),
    ])
    n = upsert(conn, "GARAN", "2024Q4", "consolidated", rep, unit=_unit())
    assert n == 2
    rows = conn.execute(
        "SELECT sector, tl_amount, fc_amount FROM bank_audit_loans_currency "
        "ORDER BY sector").fetchall()
    assert rows == [("agri_total", 10000.0, 5000.0), ("total", 10000.0, 5000.0)]


def test_upsert_idempotent():
    conn = _conn()
    rep = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42),
        CurrencyRow(sector="total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42),
    ])
    upsert(conn, "GARAN", "2024Q4", "consolidated", rep, unit=_unit())
    upsert(conn, "GARAN", "2024Q4", "consolidated", rep, unit=_unit())
    rows = conn.execute("SELECT COUNT(*) FROM bank_audit_loans_currency").fetchone()
    assert rows[0] == 2


def test_upsert_replaces_changed():
    conn = _conn()
    rep1 = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42),
    ])
    upsert(conn, "GARAN", "2024Q4", "consolidated", rep1, unit=_unit())
    rep2 = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=9999, fc_amount=4444,
                    period_type="current", page=42),
    ])
    upsert(conn, "GARAN", "2024Q4", "consolidated", rep2, unit=_unit())
    row = conn.execute(
        "SELECT tl_amount, fc_amount FROM bank_audit_loans_currency").fetchone()
    assert row == (9999.0, 4444.0)


def test_upsert_prior_period():
    conn = _conn()
    rep = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42),
        CurrencyRow(sector="agri_total", tl_amount=8000, fc_amount=4000,
                    period_type="prior", page=42),
    ])
    upsert(conn, "GARAN", "2024Q4", "consolidated", rep, unit=_unit())
    rows = conn.execute(
        "SELECT period_type, tl_amount FROM bank_audit_loans_currency "
        "ORDER BY period_type").fetchall()
    assert rows == [("current", 10000.0), ("prior", 8000.0)]


def test_upsert_rejects_duplicate_sector_period():
    conn = _conn()
    rep = LoansCurrencyReport(rows=[
        CurrencyRow(sector="agri_total", tl_amount=10000, fc_amount=5000,
                    period_type="current", page=42),
        CurrencyRow(sector="agri_total", tl_amount=9999, fc_amount=4444,
                    period_type="current", page=42),
    ])
    try:
        upsert(conn, "GARAN", "2024Q4", "consolidated", rep, unit=_unit())
        assert False, "should have raised ValueError"
    except ValueError:
        pass
