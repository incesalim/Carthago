"""Unit tests for the §4 extractor number-format helpers.

Guarded by importorskip: capital_adequacy imports pdfplumber, which CI's minimal
dependency set doesn't install, so this module is skipped there and runs locally.
The cases encode the real per-bank format variants (TR decimal comma, leading vs
trailing %, dot-thousands) that the cross-bank testing surfaced.
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.capital_adequacy import (  # noqa: E402
    _parse_ratio,
    _repair_split_digits,
    _trailing_two_tokens,
)


def test_parse_ratio_handles_tr_and_en_and_percent_placement():
    assert _parse_ratio("16.79") == 16.79      # EN dot decimal (DENIZ amounts EN)
    assert _parse_ratio("16,79") == 16.79      # TR comma decimal (DENIZ ratio)
    assert _parse_ratio("11,71%") == 11.71     # trailing % (AKBNK)
    assert _parse_ratio("%5.50") == 5.5        # leading % (TEB)
    assert _parse_ratio("1,016.79") == 1016.79  # EN thousands + decimal
    # TR thousands + decimal: an FC LCR can exceed 1000 ("1.158,00" = 1158.00).
    # The rightmost separator is the decimal, so the format is inferred not
    # assumed EN — the old code stripped commas and read this as 1.158 (the FIBA
    # lcr_fc bug).
    assert _parse_ratio("1.158,00") == 1158.0
    assert _parse_ratio("1.080,24") == 1080.24
    assert _parse_ratio("938,87") == 938.87     # sub-1000 TR decimal, unchanged
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


def test_trailing_two_tokens_skips_footnote_markers():
    # ATBANK: "(2)" after the label is a footnote reference, not a value —
    # naive collection read it as current=2.00 and pushed 17.77 to prior.
    assert _trailing_two_tokens("Sermaye Yeterliliği Oranı (%) (2) 17.77") == ["17.77"]
    # Marker between the two real columns must not displace either value.
    assert _trailing_two_tokens("Capital Adequacy Ratio (%) (1) 18.76 21.85") == [
        "18.76", "21.85"]
    # A real parenthesized negative (separators/decimals) still parses.
    assert _trailing_two_tokens("Some deduction (1,208) (2,310)") == [
        "(1,208)", "(2,310)"]


def test_repair_split_digits_rejoins_tfkb_damage():
    # TFKB's text layer detaches the leading digit of every number.
    assert _repair_split_digits(
        "Toplam Özkaynak (Ana Sermaye ve Katkı Sermaye Toplamı) 1 1,372,338 1 0,094,760"
    ) == "Toplam Özkaynak (Ana Sermaye ve Katkı Sermaye Toplamı) 11,372,338 10,094,760"
    assert _repair_split_digits(
        "Sermaye Yeterliliği Oranı (%) 2 0.20 1 7.85"
    ) == "Sermaye Yeterliliği Oranı (%) 20.20 17.85"
    # Separator-leading fragment ("7 ,348,196") and decimal fragment ("2 .500").
    assert _repair_split_digits(
        "İndirimler Öncesi Çekirdek Sermaye 7 ,348,196 6 ,601,019"
    ) == "İndirimler Öncesi Çekirdek Sermaye 7,348,196 6,601,019"
    assert _repair_split_digits("tamponu oranı 2 .500 2 .500") == (
        "tamponu oranı 2.500 2.500")


def test_repair_split_digits_leaves_clean_lines_alone():
    for ln in [
        "Capital Adequacy Ratio (%) 18.76 21.85",
        "Total Risk Weighted Assets 3,154,771,905 2,645,600,330",
        "rates as of 31 December 2021.",            # date stays a date
        "Yönetmeliğin 9 uncu maddesinin (i) bendi",  # prose ordinals untouched
        "Tier 1 Capital Ratio (%) 14.08 16.61",      # label digit untouched
    ]:
        assert _repair_split_digits(ln) == ln


def test_ratio_labels_match_consolidated_prefixes():
    # VAKIFK consolidated reports prefix every ratio label with "Konsolide";
    # without the prefix match, CAR fell through to a narrative line ("…30").
    from src.audit_reports.capital_adequacy import _FIELD_RX

    rx_by_field = {f: rxs for f, _is_ratio, rxs in _FIELD_RX}

    def matches(field, line):
        return any(rx.match(line) for rx in rx_by_field[field])

    assert matches("capital_adequacy_ratio",
                   "Konsolide Sermaye Yeterliliği Oranı (%) 20,63 18,32")
    assert matches("cet1_ratio",
                   "Konsolide Çekirdek Sermaye Yeterliliği Oranı (%) 18,33 15,57")
    assert matches("tier1_ratio",
                   "Konsolide Ana Sermaye Yeterliliği Oranı (%) 20,01 17,71")
    # "Konsolide Sermaye…" must hit CAR, not the Tier1/CET1 patterns.
    assert not matches("tier1_ratio",
                       "Konsolide Sermaye Yeterliliği Oranı (%) 20,63 18,32")


def test_labels_match_tskb_squished_and_core_variants():
    # TSKB 2023-2024 squishes ALL inter-word spaces out of the text layer,
    # and says "Core" where other banks say "Common".
    from src.audit_reports.capital_adequacy import _FIELD_RX, _START_RX

    rx_by_field = {f: rxs for f, _is_ratio, rxs in _FIELD_RX}

    def matches(field, line):
        return any(rx.match(line) for rx in rx_by_field[field])

    assert any(rx.search("Core EquityTier1CapitalBeforeDeductions 23.718.003")
               for rx in _START_RX)
    assert matches("cet1_capital", "Core Equity Tier I Capital 44.540.818 31.507.909")
    assert matches("capital_adequacy_ratio", "CapitalAdequacyRatio(%) 22,87 26,16")
    assert matches("tier1_ratio", "TierICapitalAdequacyRatio(%) 21,76 25,02")
    assert matches("total_rwa", "TotalRiskWeightedAssets 148.421.372 106.339.113")
    # The Before-Deductions line must NOT be read as the CET1 total,
    # squished or spaced.
    assert not matches("cet1_capital",
                       "Core Equity Tier 1 Capital Before Deductions 46.114.215")
    assert not matches("cet1_capital",
                       "Core EquityTier1CapitalBeforeDeductions 23.718.003")
