"""Offline tests for the investor-presentation discovery (no network).

The IR page fetch (``_get``) is monkeypatched to return an inline HTML fixture,
so the skeleton-reproduction logic is exercised exactly like the live validator
but without hitting the network.
"""
from __future__ import annotations

import types

from src.earnings import presentations
from src.earnings.presentations import _extract_qcode, _period_of, discover_presentation


# --- quarter-code parsing ---------------------------------------------------

def test_extract_qcode_variants():
    assert _extract_qcode("1Q26_BRSA_Consolidated_Earnings_Presentation.pdf") == "2026Q1"
    assert _extract_qcode("akbank_earnings_presentation_4q2025.pdf") == "2025Q4"
    assert _extract_qcode("yapi_kredi_1q26_earnings_presentation.pdf") == "2026Q1"
    assert _extract_qcode("rapor_1ç2025.pdf") == "2025Q1"
    assert _extract_qcode("no_quarter_here.pdf") is None


def test_period_of_prefers_quarter_end_date():
    # A quarter-end date in the URL resolves directly.
    assert _period_of("foo/31032026_report.pdf") == "2026Q1"
    # Else falls back to the quarter code.
    assert _period_of("foo/3Q25_Earnings.pdf") == "2025Q3"


# --- discovery against an inline IR-page fixture ----------------------------

_GARANTI_HTML = """
<html><body>
  <a href="/en/images/pdf/1Q26_BRSA_Consolidated_Earnings_Presentation.pdf">1Q26</a>
  <a href="/en/images/pdf/4Q25_BRSA_Consolidated_Earnings_Presentation.pdf">4Q25</a>
  <a href="/en/images/pdf/3Q25_BRSA_Consolidated_Earnings_Presentation.pdf">3Q25</a>
  <a href="/en/images/pdf/some_unrelated_factsheet.pdf">other</a>
</body></html>
"""

_GARANTI_CFG = {
    "ir_page": "https://www.garantibbvainvestorrelations.com/en/earnings",
    "urls": {
        "presentation": {
            "2025Q3": "https://www.garantibbvainvestorrelations.com/en/images/pdf/3Q25_BRSA_Consolidated_Earnings_Presentation.pdf",
            "2025Q4": "https://www.garantibbvainvestorrelations.com/en/images/pdf/4Q25_BRSA_Consolidated_Earnings_Presentation.pdf",
        }
    },
}


def _fake_get(html: str):
    def _get(url: str):
        return types.SimpleNamespace(text=html, url=url)
    return _get


def test_discovery_reproduces_known_and_finds_new(monkeypatch):
    monkeypatch.setattr(presentations, "_get", _fake_get(_GARANTI_HTML))
    found = dict(discover_presentation("GARAN", _GARANTI_CFG))
    # Reproduces the two seeded quarters with the same paths…
    assert found["2025Q3"].endswith("/3Q25_BRSA_Consolidated_Earnings_Presentation.pdf")
    assert found["2025Q4"].endswith("/4Q25_BRSA_Consolidated_Earnings_Presentation.pdf")
    # …and discovers the newer quarter from the same naming pattern.
    assert found["2026Q1"].endswith("/1Q26_BRSA_Consolidated_Earnings_Presentation.pdf")
    # The unrelated factsheet (different skeleton, no quarter) is not picked up.
    assert all("factsheet" not in u for u in found.values())


def test_opaque_url_config_gates_to_empty(monkeypatch):
    # Known URLs carry no quarter token → discovery refuses (static-only).
    cfg = {
        "ir_page": "https://example.com/ir",
        "urls": {"presentation": {"2025Q4": "https://example.com/docs/latest_presentation.pdf"}},
    }
    monkeypatch.setattr(presentations, "_get", _fake_get("<a href='x.pdf'>x</a>"))
    assert discover_presentation("XBANK", cfg) == []
