"""Offline unit tests for the faaliyet (annual-report) franchise extractor.

Text fixtures + synthetic word-boxes — no network, no real PDFs — so the suite
runs in CI's minimal-deps job. Covers number parsing (the 1.769 vs 1,769 trap),
prose anchors, sanity bands, branch footing, prior-year comparatives, the
expense-line negative case, and the coordinate-anchor geometry.
"""
from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("pdfplumber")  # CI installs minimal deps; extractor needs pdfplumber

from src.faaliyet import extractor as ex  # noqa: E402
from src.faaliyet.loader import crosscheck, upsert_report  # noqa: E402
from src.faaliyet.schema import init_schema  # noqa: E402


# --- number parsing --------------------------------------------------------
@pytest.mark.parametrize("num,suf,lang,expect", [
    ("1.769", None, "tr", (1769.0, "count")),     # TR thousands sep
    ("1,769", None, "en", (1769.0, "count")),     # EN thousands sep
    ("646", None, "tr", (646.0, "count")),
    ("12.591", None, "tr", (12591.0, "count")),
    ("15,5", "milyon", "tr", (15.5, "count_mn")),  # TR decimal
    ("15.5", "million", "en", (15.5, "count_mn")), # EN decimal
    ("1.084", None, "tr", (1084.0, "count")),
    ("(651)", None, "tr", (651.0, "count")),
])
def test_parse_count(num, suf, lang, expect):
    assert ex.parse_count(num, suf, lang) == expect


def test_parse_count_garbage():
    assert ex.parse_count("", None) is None
    assert ex.parse_count("abc", None) is None


# --- branch dom/for/total split + footing ----------------------------------
def test_branch_split_turkish():
    txt = "Banka, yurt içinde 1.745 ve yurt dışında 24 şubesiyle hizmet vermektedir."
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 3, "tr")}
    assert stats["branch_domestic"].value == 1745
    assert stats["branch_foreign"].value == 24
    assert stats["branch_total"].value == 1769     # derived
    assert stats["branch_total"].confidence in ("high", "medium")


def test_branch_consisting_of_english():
    txt = ("The Bank operates with a total of 1,092 branches consisting of "
           "1,084 domestic and 8 foreign branches.")
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 1, "en")}
    assert stats["branch_total"].value == 1092
    assert stats["branch_domestic"].value == 1084
    assert stats["branch_foreign"].value == 8


def test_branch_footing_boosts_confidence():
    txt = "yurt içinde 1.084 ve yurt dışında 8 şubesi, toplam 1.092 şube."
    rep = ex.FranchiseReport()
    rep.stats = ex.extract_stats_from_text(txt, 1, "tr")
    ex._foot_branches(rep.stats)
    bt = next(s for s in rep.stats if s.metric_key == "branch_total")
    # derived total 1092 == 1084+8 → footing holds → high
    assert bt.confidence == "high"


# --- employees, including the expense-line negative case -------------------
def test_employee_sayisi():
    txt = "Banka'nın personel sayısı 12.591 (31 Aralık 2024: 12.778) kişidir."
    out = ex.extract_stats_from_text(txt, 2, "tr")
    current = {s.metric_key: s for s in out if s.period_type == "current"}
    assert current["employee_count"].value == 12591
    prior = [s for s in out if s.metric_key == "employee_count" and s.period_type == "prior"]
    assert prior and prior[0].value == 12778


def test_employee_expense_line_not_matched():
    # "Personel Giderleri 5.432.100" is a TL expense, NOT a headcount.
    txt = "PERSONEL GİDERLERİ 5.432.100 bin TL olarak gerçekleşmiştir."
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 9, "tr")}
    assert "employee_count" not in stats


# --- infographic-style figures: ATM, milyon müşteri ------------------------
def test_atm_and_customers_millions():
    txt = "ATM sayısı 5.812 adede ulaşırken, aktif müşteri sayısı 12,4 milyon oldu."
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 5, "tr")}
    assert stats["atm_count"].value == 5812
    assert stats["customer_active"].value == 12.4
    assert stats["customer_active"].unit == "count_mn"


def test_band_rejects_implausible():
    # 9 million "branches" is absurd → dropped by the band.
    txt = "şube sayısı 9.000.000"
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 1, "tr")}
    assert "branch_total" not in stats


# --- coordinate anchor (synthetic infographic) -----------------------------
def test_coordinate_nearest_number():
    # An icon tile: the number "1.769" sits directly above its "Şube" label,
    # while a far-away "5.812" belongs to the ATM tile.
    rows = [
        [(40.0, 70.0, "1.769"), (240.0, 270.0, "5.812")],   # number row
        [(42.0, 80.0, "Şube"), (238.0, 275.0, "ATM")],      # label row
    ]
    stats = {s.metric_key: s for s in
             ex.extract_stats_from_words(rows, page=4, lang="tr",
                                         want={"branch_total", "atm_count"})}
    assert stats["branch_total"].value == 1769
    assert stats["atm_count"].value == 5812
    assert stats["branch_total"].confidence == "low"


# --- loader cross-check against bank_audit_profile -------------------------
def _profile_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "CREATE TABLE bank_audit_profile (bank_ticker TEXT, period TEXT, kind TEXT,"
        " branches_domestic INT, branches_foreign INT, branches_total INT, personnel INT)"
    )
    conn.execute(
        "INSERT INTO bank_audit_profile VALUES ('AKBNK','2024Q4','consolidated',"
        " 646, 1, 647, 12591)"
    )
    conn.commit()
    return conn


def test_crosscheck_agreement_boosts():
    conn = _profile_db()
    stats = [ex.FranchiseStat("employee_count", 12600, "count", confidence="medium")]
    note = crosscheck(conn, "AKBNK", 2024, stats)
    assert stats[0].confidence == "high"      # 12600 vs 12591 → within 5%
    assert note is None


def test_crosscheck_disagreement_downgrades_and_notes():
    conn = _profile_db()
    stats = [ex.FranchiseStat("branch_total", 900, "count", confidence="high")]
    note = crosscheck(conn, "AKBNK", 2024, stats)
    assert stats[0].confidence == "medium"
    assert note and "branch_total" in note


def test_upsert_replaces_partition():
    conn = _profile_db()
    rep = ex.FranchiseReport(pdf_path="x.pdf", fiscal_year=2024, n_pages=200)
    rep.stats = [ex.FranchiseStat("atm_count", 5812, "count", source_page=5)]
    upsert_report(conn, "AKBNK", 2024, rep, source_url="http://x", r2_key="akbnk/x.pdf")
    n = conn.execute("SELECT COUNT(*) FROM faaliyet_franchise WHERE bank_ticker='AKBNK'").fetchone()[0]
    assert n == 1
    # re-run with a different stat → partition replaced, not duplicated
    rep.stats = [ex.FranchiseStat("atm_count", 5900, "count", source_page=5),
                 ex.FranchiseStat("employee_count", 12591, "count")]
    upsert_report(conn, "AKBNK", 2024, rep)
    rows = conn.execute(
        "SELECT metric_key, value FROM faaliyet_franchise WHERE bank_ticker='AKBNK'"
        " ORDER BY metric_key").fetchall()
    assert rows == [("atm_count", 5900.0), ("employee_count", 12591.0)]
    ext = conn.execute("SELECT success, metrics_found FROM faaliyet_extractions"
                       " WHERE bank_ticker='AKBNK'").fetchone()
    assert ext == (1, 2)
