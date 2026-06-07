"""Unit tests for the §4 extractor number-format helpers.

Guarded by importorskip: capital_adequacy imports pdfplumber, which CI's minimal
dependency set doesn't install, so this module is skipped there and runs locally.
The cases encode the real per-bank format variants (TR decimal comma, leading vs
trailing %, dot-thousands) that the cross-bank testing surfaced.
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.capital_adequacy import _parse_ratio, _trailing_two_tokens  # noqa: E402


def test_parse_ratio_handles_tr_and_en_and_percent_placement():
    assert _parse_ratio("16.79") == 16.79      # EN dot decimal (DENIZ amounts EN)
    assert _parse_ratio("16,79") == 16.79      # TR comma decimal (DENIZ ratio)
    assert _parse_ratio("11,71%") == 11.71     # trailing % (AKBNK)
    assert _parse_ratio("%5.50") == 5.5        # leading % (TEB)
    assert _parse_ratio("1,016.79") == 1016.79  # EN thousands + decimal
    assert _parse_ratio("-") is None
    assert _parse_ratio("") is None


def test_trailing_two_tokens_takes_last_two_numbers():
    # Embedded label digits (the '1' in CET1) are ignored — only trailing run.
    assert _trailing_two_tokens("CET1 Capital Ratio (%) 14.08 16.61") == ["14.08", "16.61"]
    assert _trailing_two_tokens(
        "Total Capital ( Total of Tier I and Tier II ) 591,806,874 578,162,530"
    ) == ["591,806,874", "578,162,530"]
    # Turkish dot-thousands amounts + glued row number.
    assert _trailing_two_tokens(
        "Toplam Risk Ağırlıklı Tutarlar 2.453.951.205 2.050.564.478"
    ) == ["2.453.951.205", "2.050.564.478"]
    # Leading-% percentage columns (TEB leverage row).
    assert _trailing_two_tokens("15.Leverage ratio %5.50 %5.49") == ["%5.50", "%5.49"]


def test_trailing_two_tokens_empty_when_no_numbers():
    assert _trailing_two_tokens("Components of total capital") == []
