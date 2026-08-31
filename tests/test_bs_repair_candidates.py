"""Complete-statement evidence and row ownership for displaced BS candidates."""
import pytest

from src.audit_reports.extractor import (
    _count_values, _fitz_merge_rows, _parse_bs_with_checks, _parse_rows, _split_label,
)
from src.audit_reports.validator import validate_statement


def _original(text):
    return _parse_rows(_fitz_merge_rows(text, 6), 6)


def _by_hierarchy(rows):
    return {_split_label(label)[0]: (" ".join(_split_label(label)[1].split()), values)
            for label, values in rows}


def _validate(rows):
    return validate_statement([
        dict(hierarchy=_split_label(label)[0], item_name=_split_label(label)[1],
             amount_tl=values[0], amount_fc=values[1], amount_total=values[2])
        for label, values in rows
    ])


def test_value_above_child_recovers_both_periods_only_with_statement_evidence():
    # EXIM shape: row label and figures precede the displaced hierarchy label.
    text = "\n".join([
        "I. FINANCIAL ASSETS 900 100 1,000 400 100 500",
        "1.1 Cash 200 100 300 100 100 200",
        "Loans 700 0 700 300 0 300",
        "1.2 Amortised assets",
        "TOTAL ASSETS 900 100 1,000 400 100 500",
    ])
    before = _original(text)
    repaired = _parse_bs_with_checks(text)
    assert _validate(before).failed > 0
    assert _validate(repaired).failed == 0
    assert _by_hierarchy(repaired)["1.2"] == (
        "Loans Amortised assets", [700, 0, 700, 300, 0, 300])
    assert _by_hierarchy(repaired)["1.1"] == _by_hierarchy(before)["1.1"]
    assert _by_hierarchy(repaired)[""][1] == [900, 100, 1000, 400, 100, 500]


def test_value_above_roman_parent_keeps_its_child_and_grand_total():
    # FIBA shape: the value-bearing BORROWINGS line precedes roman II.
    text = "\n".join([
        "I. DEPOSITS 200 100 300 100 100 200",
        "BORROWINGS 700 0 700 300 0 300",
        "II. Funds borrowed",
        "2.1 Borrowed funds 700 0 700 300 0 300",
        "TOTAL LIABILITIES 900 100 1,000 400 100 500",
    ])
    repaired = _parse_bs_with_checks(text)
    rows = _by_hierarchy(repaired)
    assert rows["II."] == ("BORROWINGS Funds borrowed", [700, 0, 700, 300, 0, 300])
    assert rows["2.1"][1] == [700, 0, 700, 300, 0, 300]
    assert rows[""][1] == [900, 100, 1000, 400, 100, 500]
    assert len(repaired) == 4 and _validate(repaired).failed == 0


@pytest.mark.parametrize("missing", ["grand_total", "roman_parent"])
def test_partial_statement_cannot_authorize_a_displaced_row_repair(missing):
    lines = [
        "I. FINANCIAL ASSETS 900 100 1,000 400 100 500",
        "1.1 Cash 200 100 300 100 100 200",
        "Loans 700 0 700 300 0 300",
        "1.2 Amortised assets",
        "TOTAL ASSETS 900 100 1,000 400 100 500",
    ]
    if missing == "grand_total":
        lines.pop()
    else:
        # A reconciling lower subtree still does not prove the full statement.
        lines[0] = "1. FINANCIAL ASSETS 900 100 1,000 400 100 500"
        lines[-1] = "1.9 Unrelated assets 100 0 100 100 0 100"
        lines = [s.replace("1.", "1.1.", 1) if s.startswith("1.") else s for s in lines]
    text = "\n".join(lines)
    assert _parse_bs_with_checks(text) == _original(text)


def test_emlak_three_stray_dashes_do_not_become_current_zeroes():
    text = "\n".join([
        "I. FINANCIAL ASSETS 900 100 1,000 400 100 500",
        "1.1 Cash 200 100 300 100 100 200",
        "1.2 Amortised - - -",
        "Loans (5.II.b) 700 0 700 300 0 300",
        "TOTAL ASSETS 900 100 1,000 400 100 500",
    ])
    repaired = _parse_bs_with_checks(text)
    assert _by_hierarchy(repaired)["1.2"][1] == [700, 0, 700, 300, 0, 300]
    assert _validate(repaired).failed == 0


def test_clean_multiperiod_rows_keep_current_and_first_prior_triplets():
    text = "\n".join([
        "I. FINANCIAL ASSETS 900 100 1,000 400 100 500 300 100 400",
        "1.1 Cash 200 100 300 100 100 200 100 100 200",
        "1.2 Loans 700 0 700 300 0 300 200 0 200",
        "TOTAL ASSETS 900 100 1,000 400 100 500 300 100 400",
    ])
    repaired = _parse_bs_with_checks(text)
    assert repaired == _original(text)
    rows = _by_hierarchy(repaired)
    assert rows["I."][1] == [900, 100, 1000, 400, 100, 500]
    assert rows["1.1"][1] == [200, 100, 300, 100, 100, 200]
    assert rows["1.2"][1] == [700, 0, 700, 300, 0, 300]


def test_continuation_values_stay_with_previous_row_while_another_row_repairs():
    text = "\n".join([
        "I. FINANCIAL ASSETS 900 100 1,000 400 100 500",
        "1.1 Cash",
        "and balances 200 100 300 100 100 200",
        "1.2 Loans",
        "at amortised cost 300 0 300 100 0 100",
        "Financial assets 400 0 400 200 0 200",
        "1.3 at fair value",
        "TOTAL ASSETS 900 100 1,000 400 100 500",
    ])
    repaired = _by_hierarchy(_parse_bs_with_checks(text))
    assert repaired["1.1"] == ("Cash and balances", [200, 100, 300, 100, 100, 200])
    assert repaired["1.2"] == ("Loans at amortised cost", [300, 0, 300, 100, 0, 100])
    assert repaired["1.3"] == ("Financial assets at fair value", [400, 0, 400, 200, 0, 200])


def test_three_line_continuation_cannot_be_stolen_even_when_totals_still_tie():
    # Stealing the 200 from 1.1 into the empty 1.2 preserves row count and
    # parent sums. Arithmetic alone cannot establish ownership of these cells.
    text = "\n".join([
        "I. FINANCIAL ASSETS 500 0 500 300 0 300",
        "1.1 Cash",
        "and balances",
        "from banks 200 0 200 100 0 100",
        "1.2 Other assets",
        "1.3 Loans - - -",
        "at amortised cost 300 0 300 200 0 200",
        "TOTAL ASSETS 500 0 500 300 0 300",
    ])
    repaired = _by_hierarchy(_parse_bs_with_checks(text))
    assert repaired["1.1"] == ("Cash and balances from banks", [200, 0, 200, 100, 0, 100])
    assert "1.2" not in repaired


def test_single_missing_hierarchy_digit_repairs_only_uniquely_bracketed_sibling():
    text = "\n".join([
        "XV. EQUITY 900 100 1,000 400 100 500",
        "15.5 Reserves 900 100 1,000 400 100 500",
        "15.5.2 Legal reserve 200 100 300 100 100 200",
        "1.5.3 Other reserve 300 0 300 100 0 100",
        "15.5.4 Retained earnings 400 0 400 200 0 200",
        "TOTAL LIABILITIES 900 100 1,000 400 100 500",
    ])
    repaired = _by_hierarchy(_parse_bs_with_checks(text))
    assert repaired["15.5.3"] == ("Other reserve", [300, 0, 300, 100, 0, 100])
    assert "1.5.3" not in repaired
    ambiguous = text.replace("15.5.2", "15.5.1")
    assert _parse_bs_with_checks(ambiguous) == _original(ambiguous)


def test_reference_tokens_do_not_end_continuation_collection_early():
    assert _count_values("1.2 Loans (5.II.b) IV-6 200 100 300") == 3
    assert _count_values("1.2 Loans (5.II.b) -- -- -- -- -- --") == 6
    text = "1.2 Loans (5.II.b) 200 100 300\n100 100 200"
    assert _parse_bs_with_checks(text)[0][1] == [200, 100, 300, 100, 100, 200]
