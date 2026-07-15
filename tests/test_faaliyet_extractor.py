"""Offline unit tests for the faaliyet (annual-report) franchise extractor.

Text fixtures + synthetic word-boxes — no network, no real PDFs — so the suite
runs in CI's minimal-deps job. Covers number parsing (the 1.769 vs 1,769 trap),
prose anchors, sanity bands, the coordinate-anchor geometry, the partition-replace
upsert, and a guard that branch/employee counts are NOT sourced here (they come
from the audit lane's bank_audit_profile).
"""
from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("fitz")  # CI installs minimal deps; extractor needs fitz (PyMuPDF)

from src.faaliyet import extractor as ex  # noqa: E402
from src.faaliyet.loader import upsert_report  # noqa: E402
from src.faaliyet.schema import init_schema  # noqa: E402


# --- number parsing --------------------------------------------------------
@pytest.mark.parametrize("num,suf,lang,expect", [
    ("1.769", None, "tr", (1769.0, "count")),     # TR thousands sep
    ("1,769", None, "en", (1769.0, "count")),     # EN thousands sep
    ("5.812", None, "tr", (5812.0, "count")),
    ("12,4", "milyon", "tr", (12.4, "count_mn")),  # TR decimal
    ("12.4", "million", "en", (12.4, "count_mn")), # EN decimal
    ("(101)", None, "tr", (101.0, "count")),
])
def test_parse_count(num, suf, lang, expect):
    assert ex.parse_count(num, suf, lang) == expect


def test_parse_count_garbage():
    assert ex.parse_count("", None) is None
    assert ex.parse_count("abc", None) is None


# --- prose anchors: ATM, POS, milyon müşteri, cards ------------------------
def test_atm_and_customers_millions():
    txt = "ATM sayısı 5.812 adede ulaşırken, aktif müşteri sayısı 12,4 milyon oldu."
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 5, "tr")}
    assert stats["atm_count"].value == 5812
    assert stats["atm_count"].unit == "count"
    assert stats["customer_active"].value == 12.4
    assert stats["customer_active"].unit == "count_mn"


def test_pos_and_merchant_and_cards():
    txt = ("POS cihazı 142.300, üye işyeri sayısı 318.000; "
           "kredi kartı sayısı 8,1 milyon, toplam kart sayısı 15,5 milyon.")
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 6, "tr")}
    assert stats["pos_count"].value == 142300
    assert stats["merchant_count"].value == 318000
    assert stats["cards_credit"].value == 8.1
    assert stats["cards_total"].value == 15.5
    assert stats["cards_total"].unit == "count_mn"


def test_band_rejects_implausible():
    # 9 million "ATMs" is absurd (band tops out at 25k) → dropped.
    txt = "ATM sayısı 9.000.000"
    stats = {s.metric_key: s for s in ex.extract_stats_from_text(txt, 1, "tr")}
    assert "atm_count" not in stats


# --- overlap removed: branches/employees are NOT sourced here -------------
def test_no_branch_or_employee_metrics():
    txt = ("Banka, yurt içinde 1.745 ve yurt dışında 24 şubesiyle hizmet vermektedir. "
           "Banka'nın personel sayısı 12.591 kişidir. ATM sayısı 5.812'dir.")
    keys = {s.metric_key for s in ex.extract_stats_from_text(txt, 3, "tr")}
    assert "branch_total" not in keys and "branch_domestic" not in keys
    assert "employee_count" not in keys
    assert "branch_total" not in ex.METRIC_KEYS and "employee_count" not in ex.METRIC_KEYS
    # the non-overlapping ATM figure is still captured
    assert "atm_count" in keys


# --- coordinate anchor (synthetic infographic) -----------------------------
def test_coordinate_nearest_number():
    # An icon tile: "5.812" sits above its "ATM" label; "318.000" above "Üye İşyeri".
    rows = [
        [(40.0, 70.0, "5.812"), (240.0, 280.0, "318.000")],   # number row
        [(42.0, 80.0, "ATM"), (236.0, 300.0, "Üye"), (305.0, 340.0, "İşyeri")],
    ]
    stats = {s.metric_key: s for s in
             ex.extract_stats_from_words(rows, page=4, lang="tr",
                                         want={"atm_count", "merchant_count"})}
    assert stats["atm_count"].value == 5812
    assert stats["merchant_count"].value == 318000
    assert stats["atm_count"].confidence == "low"


# --- loader: partition replace --------------------------------------------
def test_upsert_replaces_partition():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    rep = ex.FranchiseReport(pdf_path="x.pdf", fiscal_year=2024, n_pages=200)
    rep.stats = [ex.FranchiseStat("atm_count", 5812, "count", source_page=5)]
    upsert_report(conn, "AKBNK", 2024, rep, source_url="http://x", r2_key="akbnk/x.pdf")
    n = conn.execute("SELECT COUNT(*) FROM faaliyet_franchise WHERE bank_ticker='AKBNK'").fetchone()[0]
    assert n == 1
    # re-run with different stats → partition replaced, not duplicated
    rep.stats = [ex.FranchiseStat("atm_count", 5900, "count", source_page=5),
                 ex.FranchiseStat("customer_active", 12.4, "count_mn")]
    upsert_report(conn, "AKBNK", 2024, rep)
    rows = conn.execute(
        "SELECT metric_key, value FROM faaliyet_franchise WHERE bank_ticker='AKBNK'"
        " ORDER BY metric_key").fetchall()
    assert rows == [("atm_count", 5900.0), ("customer_active", 12.4)]
    ext = conn.execute("SELECT success, metrics_found FROM faaliyet_extractions"
                       " WHERE bank_ticker='AKBNK'").fetchone()
    assert ext == (1, 2)
