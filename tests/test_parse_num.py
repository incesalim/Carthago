"""`parse_num` — the numeric primitive every audit extractor shares.

It is imported by capital_adequacy, credit_quality, equity_change, fx_position,
liquidity, loans_by_sector, npl_movement, oci and repricing, and until
2026-07-27 it had no tests at all. The defect those tests would have caught:

    parse_num('-319.110')  ->  -319.11    (should be -319110)

The TR-vs-EN format sniff is anchored (`^\\d{1,3}(\\.\\d{3})+$`), so a leading
'-' failed it and the number fell through to the English branch, where the
thousands separator was read as a decimal point — a silent 1000x error. Two
groups ('-1.234.567') survived on the `count('.') > 1` clause and parenthesised
negatives never reached the sniff, so it only ever bit single-group
hyphen-negatives: the BRSA section-4 market-risk net-off and gap rows.

The invariant the fix restores, and the one worth holding onto: **a number's
sign does not change how its format is read.** Every case below is asserted
against its positive twin for exactly that reason.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.extractor import parse_amount, parse_num  # noqa: E402


# --- the defect ------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("-319.110", -319110.0),   # the reported case (fx net-off row)
    ("-45.678", -45678.0),
    ("-1.000", -1000.0),
    ("-999.999", -999999.0),
])
def test_hyphen_negative_with_one_thousands_group(text, expected):
    """Was read 1000x too small: '-319.110' -> -319.11."""
    assert parse_num(text) == expected


@pytest.mark.parametrize("digits", [
    "319.110", "45.678", "1.000", "999.999", "1.234.567",
    "1.234.567,89", "12.345", "1,234,567.89", "0.5", "319.11",
])
def test_sign_does_not_change_the_format_reading(digits):
    """The general rule. A hyphen in front must only negate the value."""
    assert parse_num("-" + digits) == -parse_num(digits)


@pytest.mark.parametrize("digits", ["319.110", "1.234.567", "45.678"])
def test_parenthesised_and_hyphen_negatives_agree(digits):
    """Both notations appear in the corpus; they must not disagree."""
    assert parse_num(f"({digits})") == parse_num(f"-{digits}")


# --- format detection ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    # Turkish: '.' thousands, ',' decimal
    ("1.234.567", 1234567.0),
    ("319.110", 319110.0),
    ("1.234.567,89", 1234567.89),
    ("-1.234.567", -1234567.0),
    ("-319,110", -319110.0),          # no dot at all -> ',' stripped as thousands
    # English: ',' thousands, '.' decimal
    ("1,234,567", 1234567.0),
    ("1,234,567.89", 1234567.89),
    ("-1,234,567", -1234567.0),
    # A single dot whose group is NOT 3 digits is a genuine decimal point,
    # positive or negative — this is the ambiguity the sniff exists to resolve.
    ("0.5", 0.5),
    ("-0.5", -0.5),
    ("319.11", 319.11),
    ("-319.11", -319.11),
    # Bare integers
    ("0", 0.0),
    ("42", 42.0),
    ("-42", -42.0),
])
def test_format_detection(text, expected):
    assert parse_num(text) == expected


# --- nil and unparseable ---------------------------------------------------

@pytest.mark.parametrize("text", ["-", "", "  ", " - "])
def test_lone_dash_and_blank_are_nil(text):
    assert parse_num(text) == 0.0


@pytest.mark.parametrize("text", ["--", "abc", "n/a", "(", "-.", "1.2.3.4.5x"])
def test_unparseable_is_none_not_zero(text):
    """None and 0.0 mean different things downstream: a validator SKIPS a NULL
    field and CHECKS a zero, so a mis-parse that returned 0.0 would foot."""
    assert parse_num(text) is None


def test_whitespace_is_tolerated():
    assert parse_num("  1.234  ") == 1234.0
    assert parse_num(" ( 319.110 ) ") == -319110.0


# --- parse_amount ----------------------------------------------------------

@pytest.mark.parametrize("text", ["", "  ", "-", "--", "---", "—", "–", "–—"])
def test_parse_amount_reads_a_dash_run_as_nil(text):
    """The note-table nil form. parse_num only knows the single '-'."""
    assert parse_amount(text) == 0.0


@pytest.mark.parametrize("text,expected", [
    ("1.234.567", 1234567.0),
    ("-319.110", -319110.0),
    ("(319.110)", -319110.0),
])
def test_parse_amount_defers_to_parse_num_for_real_values(text, expected):
    assert parse_amount(text) == expected


def test_parse_amount_still_returns_none_for_junk():
    assert parse_amount("abc") is None
