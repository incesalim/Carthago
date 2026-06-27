"""Row-label taxonomy regression tests for the NPL movement extractor.

Guarded by importorskip: npl_movement imports pdfplumber, which CI's minimal
dependency set omits. The label matcher itself is pure-stdlib.
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.npl_movement import _DATE_BALANCE_RX, _match_row_label  # noqa: E402


def test_date_balance_row_tolerates_glued_suffix():
    # ODEA glues the word to the year ("31 Aralık 2021Bakiyesi") with no space —
    # the opening balance row was missed (the \b fell between "1" and "B").
    assert _DATE_BALANCE_RX.match("31 Aralık 2021Bakiyesi 142.814 21.734 1.824.580")
    assert _DATE_BALANCE_RX.match("31 Mart 2022 Bakiyesi 117.728 32.155 1.731.331")  # spaced
    assert _DATE_BALANCE_RX.match("31 Aralık 2024 103,885 209,960 144,837")          # bare date


def test_opening_label_variants_map_to_opening():
    # BURGAN (cons, English) and EXIM (English) opening rows were unmatched →
    # the block started on Additions, nulling opening_balance (the roll-forward
    # then couldn't tie).
    assert _match_row_label("Ending Balance of Prior Period 25,581 413,818") == "opening_balance"
    assert _match_row_label("Balance at the End of the Previous Period 75.305 - 801.748") == "opening_balance"


def test_previous_period_opening_not_shadowed_by_closing():
    # The EXIM opening phrase is a superstring-prefix risk against the closing
    # "Balance at the End of the Period"; longest-first matching must keep them
    # distinct (opening vs closing), or the roll-forward double-reads.
    assert _match_row_label("Balance at the End of the Period 16.779 38.015 941.266") == "closing_balance"
    assert _match_row_label("Balance at the End of the Previous Period 75.305") == "opening_balance"


def test_specific_provision_maps_to_provision():
    # BURGAN heads the provision row "Specific Provision (-)" — doesn't start with
    # "provision", so the generic prefixes missed it.
    assert _match_row_label("Specific Provision (-) 7,246 210,343 379,789") == "provision"
    assert _match_row_label("Provisions (-) 16.779 38.015 941.266") == "provision"
