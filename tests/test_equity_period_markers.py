"""Guard the equity-change current/prior period markers.

A bank that prints its prior-period matrix FIRST (HSBC) relied on _PRIOR_RX
matching "Önceki Dönem"; the old pattern only covered "Önce(si) Dönem" and
missed the "ki", so the page defaulted to 'current' and the enforce-distinct
fallback swapped the two periods (stored "current" = the prior-year matrix).

Guarded by importorskip: equity_change imports fitz (CI minimal deps omit).
"""
import pytest

pytest.importorskip("fitz")

from src.audit_reports import equity_change as EC  # noqa: E402

_CURRENT_RX = EC._CURRENT_RX
_PRIOR_RX = EC._PRIOR_RX
_max_year = EC._max_year


def test_max_year_picks_latest_period_end():
    # The current table closes on the later date, so the marker-less period
    # resolver (ALNTF) keys off the larger max-year. Current page shows
    # opening 2024 + closing 2025; prior page shows 2023 + 2024.
    assert _max_year("31 Aralık 2024 ... 31 Aralık 2025 ...") == 2025
    assert _max_year("31 Aralık 2023 ... 31 Aralık 2024 ...") == 2024
    assert _max_year("no years here") is None


def test_prior_marker_matches_onceki_and_variants():
    for s in ("Önceki Dönem", "ÖNCEKİ DÖNEM", "Öncesi Dönem", "Önce Dönem",
              "Prior Period", "Previous Period"):
        assert _PRIOR_RX.search(s), s
        assert not _CURRENT_RX.search(s), s


def test_current_marker_matches_cari():
    for s in ("Cari Dönem", "CARİ DÖNEM", "Current Period"):
        assert _CURRENT_RX.search(s), s
        assert not _PRIOR_RX.search(s), s


def test_single_page_prior_first_uses_explicit_block_headers(monkeypatch):
    """ANADOLU prints prior first and current second, with no dates beside the
    block headers.  The report-title year therefore cannot establish order."""
    text = "\n".join([
        "31 MART 2024 ... ÖZKAYNAKLAR DEĞİŞİM TABLOSU",
        "Önceki Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "Dönem Sonu Bakiyesi (III+IV+…+X+XI) " + "- " * 16,
        "Cari Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
    ])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    assert EC._block1_period_for_split("unused.pdf", 13) == "prior"


def test_single_page_current_first_stays_current(monkeypatch):
    text = "\n".join([
        "Cari Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "Dönem Sonu Bakiyesi (III+IV+…+X+XI) " + "- " * 16,
        "Önceki Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
    ])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    assert EC._block1_period_for_split("unused.pdf", 13) == "current"
