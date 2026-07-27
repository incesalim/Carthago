"""The amount-integrity guard: column classification + defect classification.

BRSA reports print every figure as a whole number of thousands of TL, so a
fractional value in an amount column is something we mis-read. The check turns
that into an invariant. Two things have to hold for it to be worth running:

  1. it must sweep the AMOUNT columns and skip the RATIO ones — a check that
     alerts on `capital_adequacy_ratio = 15.23` is a check that gets muted;
  2. it must tell a wrong NUMBER from a leaked NON-number, because only the
     first is a data defect worth waking someone for.

Both are pinned here. No DB and no network: the column map comes from the
schema, and the classifier is pure arithmetic.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from check_amount_integrity import (  # noqa: E402
    RATIO_COLUMNS,
    SEPARATOR_FRACTION_DIGITS,
    amount_columns,
    fraction_digits,
    is_misread_separator,
)
from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402


# --- what gets swept -------------------------------------------------------

def test_amount_columns_are_derived_from_the_registry_not_hand_listed():
    """A new statement type must be swept the moment it is registered — the
    hand-written-list failure mode this repo already paid for once with
    push_to_d1's --only-tables."""
    swept = amount_columns()
    assert swept, "no amount columns found — the schema walk is broken"
    assert {t for t, _ in swept} <= set(AUDIT_TABLES)


def test_every_ratio_column_is_excluded():
    """A ratio is legitimately fractional. Sweeping it means a permanent false
    positive, and a check that cries wolf daily is a check nobody reads."""
    swept = set(amount_columns())
    for table, cols in RATIO_COLUMNS.items():
        for col in cols:
            assert (table, col) not in swept, f"{table}.{col} is a ratio, not an amount"


def test_the_ratio_exclusions_name_columns_that_actually_exist():
    """An exclusion for a renamed or dropped column silently stops excluding
    anything — and silently starts sweeping whatever replaced it."""
    import sqlite3

    from src.audit_reports.schema import init_schema
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    for table, cols in RATIO_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        missing = cols - have
        assert not missing, f"RATIO_COLUMNS[{table}] names absent column(s): {missing}"


def test_the_headline_amount_columns_are_swept():
    """Spot-check the ones that carry the numbers the site publishes."""
    swept = set(amount_columns())
    for pair in [
        ("bank_audit_balance_sheet", "amount_total"),
        ("bank_audit_profit_loss", "amount"),
        ("bank_audit_capital", "cet1_capital"),        # caught ISCTR 2024Q2
        ("bank_audit_credit_quality", "stage2_amount"),  # caught DENIZ 2023Q4
        ("bank_audit_fx_position", "net_position"),
        ("bank_audit_repricing", "gap"),
    ]:
        assert pair in swept, f"{pair[0]}.{pair[1]} is not being swept"


# --- wrong number vs leaked non-number -------------------------------------

@pytest.mark.parametrize("value", [
    270336.203,    # ISCTR 2024Q2 cet1 — real 270,336,203 (found in the corpus)
    -535.779,      # DENIZ 2023Q4 stage-2 ECL — real -535,779 (found in the corpus)
    1234.567,
])
def test_a_three_digit_fraction_is_a_mis_read_separator(value):
    assert fraction_digits(value) == SEPARATOR_FRACTION_DIGITS
    assert is_misread_separator(value)


@pytest.mark.parametrize("value", [-319.110, 4200.100, -1234.500, 999.000_1])
def test_a_separator_misread_ending_in_zero_is_still_caught(value):
    """THE trap. "-319.110" becomes the double -319.11 the instant it is parsed;
    the trailing zero is unrecoverable, so the fraction-length signal alone
    misfiles roughly one in ten of this class. The integer-part signal is what
    catches them — no BRSA marker has three integer digits."""
    assert is_misread_separator(value)


@pytest.mark.parametrize("value", [
    11.3,    # GARAN equity-change: a row marker in the paid-in-capital column
    11.2,
    4.5,     # loans-by-sector: sector numbering
    2.1,
    1.01,    # QNBFB cash-flow / P&L
    2.8,
    -16.5,   # a negative marker leak, same class
])
def test_a_marker_leak_does_not_alert(value):
    assert not is_misread_separator(value)


def test_float_representation_noise_does_not_inflate_the_fraction():
    """Without the .6f cap, a double's repr turns 4.5 into 4.500000000000001 and
    the leak would be misfiled as a separator bug — i.e. it would page someone."""
    assert fraction_digits(0.1 + 4.4) == 1
    assert not is_misread_separator(0.1 + 4.4)
    assert fraction_digits(270336.203) == 3


def test_the_classifier_is_sign_blind():
    """Both notations for a negative reach this check; they must classify alike."""
    assert fraction_digits(-535.779) == fraction_digits(535.779)
    assert is_misread_separator(-535.779) == is_misread_separator(535.779)
