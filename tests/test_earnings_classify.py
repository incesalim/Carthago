"""Offline tests for the earnings KAP classifier (no network).

Fixtures are real KAP subjects/types sampled from the production snapshot
(verified 2026-06): Turkish banks file only their financial reports on KAP, with
structured year/period/ruleType fields — no earnings-call or presentation
disclosures.
"""
from __future__ import annotations

from src.earnings.classify import (
    RESULTS_FILING,
    classify_kind,
    derive_period,
)


# --- classify_kind ----------------------------------------------------------

def test_finansal_rapor_is_results_filing():
    # disclosureType 'FR', the financial-statements filing.
    assert classify_kind("Finansal Rapor", "FR") == RESULTS_FILING


def test_faaliyet_raporu_is_results_filing():
    # Category ODA but disclosureType FR — the interim activity report.
    assert classify_kind("Faaliyet Raporu (Konsolide)", "FR") == RESULTS_FILING


def test_sorumluluk_beyani_excluded():
    # disclosureType FR but only the sign-off accompanying the report — not an event.
    assert classify_kind("Sorumluluk Beyanı (Konsolide)", "FR") is None
    assert classify_kind("Sorumluluk Beyanı (Konsolide Olmayan)", "FR") is None


def test_non_earnings_kap_subjects_are_none():
    for subj, dtype in [
        ("Özel Durum Açıklaması (Genel)", "ODA"),
        ("İzahname (SPK Tarafından Onaylanan)", "DG"),
        ("Kredi Derecelendirmesi", "ODA"),
        ("Kar Payı Dağıtım İşlemlerine İlişkin Bildirim", "CA"),
        ("Şirket Genel Bilgi Formu", "DG"),
        ("Genel Kurul İşlemlerine İlişkin Bildirim", "CA"),
        ("TSRS Uyumlu Sürdürülebilirlik Raporu", "ODA"),  # class FR but type ODA
    ]:
        assert classify_kind(subj, dtype) is None, subj


def test_results_keyword_fallback_without_type():
    # If raw_json lacks disclosureType, fall back to subject keywords.
    assert classify_kind("Finansal Rapor", None) == RESULTS_FILING
    assert classify_kind("Konsolide Finansal Tablolar ve Dipnotlar", None) == RESULTS_FILING


def test_call_precedence_over_presentation():
    # A (hypothetical) free-text disclosure mentioning both resolves to 'call'.
    assert classify_kind("Yatırımcı Sunumu Telekonferansı", "ODA") == "call"
    assert classify_kind("1Ç26 Yatırımcı Sunumu", "ODA") == "presentation_filing"


# --- derive_period ----------------------------------------------------------

def test_period_from_structured_fields():
    assert derive_period({"year": 2026, "period": 1, "ruleType": "3 Aylık"}) == "2026Q1"
    assert derive_period({"year": 2025, "period": 2, "ruleType": "6 Aylık"}) == "2025Q2"
    assert derive_period({"year": 2025, "period": 3, "ruleType": "9 Aylık"}) == "2025Q3"
    assert derive_period({"year": 2024, "period": 4, "ruleType": "12 Aylık"}) == "2024Q4"


def test_period_ruletype_wins_over_numeric_period():
    # ruleType is authoritative; a 6-month report is Q2 even if period reads oddly.
    assert derive_period({"year": 2025, "period": 6, "ruleType": "6 Aylık"}) == "2025Q2"


def test_period_from_date_string_fallback():
    assert derive_period({}, subject="31.03.2026 Konsolide Faaliyet Raporu") == "2026Q1"


def test_period_from_publishdate_fallback():
    # No tokens — an April filing maps to the just-ended Q1.
    assert derive_period({}, publish_date_iso="2026-05-08T16:16:03+00:00") == "2026Q1"
    # A February filing is the prior year's Q4 (annual).
    assert derive_period({}, publish_date_iso="2026-02-20T10:00:00+00:00") == "2025Q4"


def test_period_none_when_undeterminable():
    assert derive_period({}, subject="Özel Durum Açıklaması") is None
