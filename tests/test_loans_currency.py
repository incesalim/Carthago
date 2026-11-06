"""Tests for the loans_currency extractor and DB upsert."""
from __future__ import annotations

import sqlite3

from src.audit_reports.loans_currency import (
    CurrencyRow,
    LoansCurrencyReport,
    _extract_currency_text,
    _extract_currency_xy,
    _page_has_currency_columns,
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


# ---------------------------------------------------------------------------
# Period captions carrying across pages (KLNMA prints the current-period
# currency table on one page and the prior-period table on the next, each
# under its own caption — a page that opens with "Önceki Dönem" and no
# "Cari Dönem" of its own used to restart at 'current' and duplicate keys).
# ---------------------------------------------------------------------------

def _header_lines():
    # A minimal TP/YP header band: two tokens ≥30pt apart → tl / fc columns.
    return [[(60.0, 100.0, "TP"), (260.0, 300.0, "YP")]]


def test_xy_prior_period_caption_on_new_page():
    state = {"period_type": "current", "seen_current": False}
    page1 = _header_lines() + [
        [(60.0, 90.0, "Cari Dönem (31.12.2025)")],
        [(60.0, 90.0, "Tarım"), (95.0, 100.0, "797.877"), (295.0, 300.0, "1.228")],
    ]
    rows1 = _extract_currency_xy(91, page1, state)
    page2 = _header_lines() + [
        [(60.0, 90.0, "Önceki Dönem (31.12.2024)")],
        [(60.0, 90.0, "Tarım"), (95.0, 100.0, "732.750"), (295.0, 300.0, "576.351")],
    ]
    rows2 = _extract_currency_xy(92, page2, state)

    assert rows1 and rows2
    assert all(r.period_type == "current" for r in rows1)
    assert all(r.period_type == "prior" for r in rows2), (
        "a prior-period table opening its own page must inherit the caption state")


def test_xy_out_of_band_numbers_not_vacuumed():
    state = {"period_type": "current", "seen_current": False}
    # "Toplam" row of a NEIGHBOURING table: numbers sit far outside both the
    # tl band (x≈100) and the fc band (x≈300), so nothing fills in-band and
    # the row must be dropped, not stored with misassigned figures.
    lines = _header_lines() + [
        [(60.0, 90.0, "Cari Dönem (31.12.2025)")],
        [(60.0, 90.0, "Toplam"), (500.0, 540.0, "573.425"), (600.0, 640.0, "518.157")],
        [(60.0, 90.0, "Tarım"), (95.0, 100.0, "797.877"), (295.0, 300.0, "1.228")],
    ]
    rows = _extract_currency_xy(91, lines, state)
    assert [r.sector for r in rows] == ["agri_total"]


def test_text_prior_period_caption_on_new_page():
    state = {"period_type": "current", "seen_current": False}
    rows1 = _extract_currency_text(
        91, "Cari Dönem (31.12.2025)\nTarım 797.877 1.228\n", state)
    rows2 = _extract_currency_text(
        92, "Önceki Dönem (31.12.2024)\nTarım 732.750 576.351\n", state)

    assert rows1 and rows2
    assert all(r.period_type == "current" for r in rows1)
    assert all(r.period_type == "prior" for r in rows2)


# ---------------------------------------------------------------------------
# Text-fallback gate: a page must name both sides of the currency split for
# its sector rows to be currency rows at all. KLNMA's credit-risk note
# (loans / nonaccrual / provisions by sector, no currency dimension) and
# QNBFB's English prose lines ("FOR THE YEAR ENDED DECEMBER 31 2025") were
# both captured as TL/FC pairs by label-matching alone.
# ---------------------------------------------------------------------------

def test_page_has_currency_columns():
    assert _page_has_currency_columns(
        "Sektörlere göre kredilerin dağılımı\nTP YP TP YP\nTarım 100 200")
    assert _page_has_currency_columns(
        "Loans by sector\nTL FC\nAgriculture 100 200")
    assert _page_has_currency_columns(
        "Türk Lirası Yabancı Para\nTarım 100 200")
    # "(Bin Türk Lirası (TL))" rides in the preamble of every page — the TL
    # side alone must NOT pass the gate.
    assert not _page_has_currency_columns(
        "(Tutarlar aksi belirtilmedikçe Bin Türk Lirası (TL) olarak ifade "
        "edilmiştir.)\nÖnemli sektörlere göre muhtelif bilgiler\nTarım 797.877 1.228")
    assert not _page_has_currency_columns(
        "FOR THE YEAR ENDED DECEMBER 31 2025\nAgriculture 100 200")
