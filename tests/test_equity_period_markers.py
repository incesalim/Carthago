"""Guard the equity-change current/prior period markers.

A bank that prints its prior-period matrix FIRST (HSBC) relied on _PRIOR_RX
matching "Önceki Dönem"; the old pattern only covered "Önce(si) Dönem" and
missed the "ki", so the page defaulted to 'current' and the enforce-distinct
fallback swapped the two periods (stored "current" = the prior-year matrix).

Guarded by importorskip: equity_change imports pdfplumber (CI minimal deps omit).
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.equity_change import _CURRENT_RX, _PRIOR_RX  # noqa: E402


def test_prior_marker_matches_onceki_and_variants():
    for s in ("Önceki Dönem", "ÖNCEKİ DÖNEM", "Öncesi Dönem", "Önce Dönem",
              "Prior Period", "Previous Period"):
        assert _PRIOR_RX.search(s), s
        assert not _CURRENT_RX.search(s), s


def test_current_marker_matches_cari():
    for s in ("Cari Dönem", "CARİ DÖNEM", "Current Period"):
        assert _CURRENT_RX.search(s), s
        assert not _PRIOR_RX.search(s), s
