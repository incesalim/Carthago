"""Reporting-unit normalisation: the 2026Q2 Bin -> Milyon switch.

The sector changed denomination in 2026Q2 and no in-filing check can see it —
every structural validator is a ratio of figures sharing a scale, so all eleven
Q2 filings footed perfectly while every stored figure was wrong by 1000x.

Two failure directions, both silent:
  * an amount left unscaled  -> the figure is 1000x too small;
  * a RATIO scaled by 1000   -> a 15% capital ratio becomes 15,000.

So these tests pin the classification exhaustively, pin that old filings are
untouched, and pin that an unreadable unit refuses rather than assumes.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402


# --- the classification must be exhaustive -----------------------------------

@pytest.fixture(scope="module")
def schema():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def _numeric_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")
            if r[2].upper() in ("REAL", "INTEGER", "INT", "NUMERIC")}


def test_every_numeric_column_is_classified(schema):
    """THE gate. A new numeric column that is money and unlisted is stored 1000x
    too small; one that is a ratio and listed as money is 1000x too large. Both
    pass every validator, so nothing else would catch it."""
    unclassified = {}
    for t in AUDIT_TABLES:
        if not schema.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone():
            continue
        known = U.MONEY_COLUMNS.get(t, frozenset()) | U.NON_MONEY_NUMERIC.get(t, frozenset())
        missing = _numeric_columns(schema, t) - known
        if missing:
            unclassified[t] = sorted(missing)
    assert not unclassified, (
        f"numeric columns classified as neither money nor non-money: {unclassified}")


def test_no_column_is_classified_as_both(schema):
    for t in AUDIT_TABLES:
        both = U.MONEY_COLUMNS.get(t, frozenset()) & U.NON_MONEY_NUMERIC.get(t, frozenset())
        assert not both, f"{t}: {sorted(both)} is both money and not-money"


def test_the_classification_names_only_real_columns(schema):
    """A typo in the registry silently stops scaling that column."""
    for t in set(U.MONEY_COLUMNS) | set(U.NON_MONEY_NUMERIC):
        if not schema.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone():
            continue
        real = {r[1] for r in schema.execute(f"PRAGMA table_info({t})")}
        named = U.MONEY_COLUMNS.get(t, frozenset()) | U.NON_MONEY_NUMERIC.get(t, frozenset())
        assert named <= real, f"{t}: {sorted(named - real)} not in the table"


def test_ratios_and_counts_are_never_money():
    """Verified against 4.5 years of stored values, not assumed: capital ratios
    run 4.85-138 while the amounts in the same table average 64,314,574; stage
    coverages are fractions; 925 of 933 lcr_total values sit below 1000."""
    assert "cet1_ratio" not in U.money_columns("bank_audit_capital")
    assert "capital_adequacy_ratio" not in U.money_columns("bank_audit_capital")
    for c in ("stage1_coverage", "stage2_coverage", "stage3_coverage"):
        assert c not in U.money_columns("bank_audit_stages")
    assert U.money_columns("bank_audit_liquidity") == frozenset(), \
        "LCR, NSFR and leverage are all ratios — nothing in liquidity is money"
    assert U.money_columns("bank_audit_profile") == frozenset(), \
        "branch and personnel counts are not money"


def test_the_money_side_covers_the_statements_that_carry_figures():
    for t, col in [("bank_audit_balance_sheet", "amount_tl"),
                   ("bank_audit_profit_loss", "amount"),
                   ("bank_audit_oci", "amount"),
                   ("bank_audit_cash_flow", "amount"),
                   ("bank_audit_capital", "total_rwa"),
                   ("bank_audit_npl_movement", "closing_balance"),
                   ("bank_audit_fx_position", "net_position"),
                   ("bank_audit_repricing", "cumulative_gap"),
                   ("bank_audit_free_provision", "free_provision"),
                   ("bank_audit_stages", "total_ecl"),
                   ("bank_audit_loans_by_sector", "ecl_amount"),
                   ("bank_audit_credit_quality", "total_amount"),
                   ("bank_audit_equity_change", "total_equity")]:
        assert col in U.money_columns(t), f"{t}.{col} must be scaled"


def test_thirteen_tables_carry_money_and_seven_carry_none():
    """13 + 7 = the 20 audit tables. Pinned as a count so adding a table forces
    a deliberate classification rather than a silent default to not-money."""
    money = set(U.MONEY_COLUMNS)
    none = {"bank_audit_liquidity", "bank_audit_profile", "bank_audit_opinion",
            "bank_audit_validation", "bank_audit_extractions",
            "bank_audit_pl_roles", "bank_audit_prose"}
    assert len(money) == 13
    assert len(none) == 7
    assert money | none == set(AUDIT_TABLES)
    for t in none:
        assert U.money_columns(t) == frozenset()


# --- old audits must be untouched --------------------------------------------

@pytest.mark.parametrize("period", [
    "2022Q1", "2023Q4", "2024Q2", "2025Q4", "2026Q1"])
def test_pre_switch_periods_resolve_to_bin_without_reading_the_pdf(period):
    """THE old-audit guarantee. The July sweep read 550 filings and found no
    pre-2026Q2 filing using millions, so these resolve without opening anything
    — a detector regression cannot rescale 4.5 years of stored data, and a
    re-extraction of an old partition stores exactly what it stored before."""
    assert U.within_sweep(period)
    assert U.resolve_unit(period, pdf_path=None) == "bin"
    assert U.scale_factor(U.resolve_unit(period)) == 1


def test_a_bin_filing_scales_by_one_and_changes_nothing():
    row = {"amount_tl": 1234.5, "amount_fc": None, "item_order": 7}
    assert U.scale_mapping("bank_audit_balance_sheet", row, 1) == row


@pytest.mark.parametrize("period,expected", [
    ("2026Q1", True), ("2026Q2", False), ("2026Q3", False), ("2027Q1", False),
    ("2025Q4", True), ("2021Q4", True)])
def test_the_sweep_horizon_is_the_boundary(period, expected):
    assert U.within_sweep(period) is expected


def test_period_ordering_crosses_the_year_boundary():
    assert U.within_sweep("2025Q4") and not U.within_sweep("2026Q2")
    assert U._period_key("2026Q1") > U._period_key("2025Q4")


# --- the new regime -----------------------------------------------------------

def test_a_milyon_filing_scales_money_by_a_thousand():
    assert U.scale_factor("milyon") == 1_000
    row = {"amount_tl": 5.0, "amount_fc": 2.5, "amount_total": 7.5, "item_order": 3}
    out = U.scale_mapping("bank_audit_balance_sheet", row, 1_000)
    assert out == {"amount_tl": 5000.0, "amount_fc": 2500.0,
                   "amount_total": 7500.0, "item_order": 3}


def test_scaling_leaves_ratios_and_ordinals_alone():
    row = {"cet1_capital": 12.0, "cet1_ratio": 15.4,
           "capital_adequacy_ratio": 21.2, "source_page": 88}
    out = U.scale_mapping("bank_audit_capital", row, 1_000)
    assert out["cet1_capital"] == 12_000.0
    assert out["cet1_ratio"] == 15.4
    assert out["capital_adequacy_ratio"] == 21.2
    assert out["source_page"] == 88


def test_a_liquidity_row_is_never_scaled():
    row = {"lcr_total": 152.3, "lcr_fc": 210.0, "nsfr": 130.1,
           "leverage_ratio": 8.4, "source_page": 5}
    assert U.scale_mapping("bank_audit_liquidity", row, 1_000) == row


def test_null_stays_null_and_zero_stays_zero():
    """`null` is not `0`: a disclosure never made must not become a figure, and
    a disclosed zero is still zero at any scale."""
    row = {"amount": None}
    assert U.scale_mapping("bank_audit_profit_loss", row, 1_000)["amount"] is None
    assert U.scale_mapping("bank_audit_profit_loss", {"amount": 0}, 1_000)["amount"] == 0


def test_negative_amounts_scale_with_their_sign():
    """Deduction lines carry negative amounts; the sign must survive."""
    out = U.scale_mapping("bank_audit_profit_loss", {"amount": -4.5}, 1_000)
    assert out["amount"] == -4500.0


def test_the_positional_variant_agrees_with_the_mapping_one():
    cols = ["bank_ticker", "amount_tl", "item_order"]
    row = ("AKBNK", 2.0, 9)
    assert U.scale_sequence("bank_audit_balance_sheet", cols, row, 1_000) == \
        ("AKBNK", 2000.0, 9)


def test_milyar_is_recognised_even_though_no_filing_uses_it_yet():
    assert U.scale_factor("milyar") == 1_000_000


# --- refuse, never guess ------------------------------------------------------

def test_an_unknown_unit_refuses():
    """UNKNOWN means 'look at this filing', never 'assume thousands'."""
    with pytest.raises(ValueError, match="UNKNOWN"):
        U.scale_factor(None)


def test_an_unrecognised_unit_refuses():
    with pytest.raises(ValueError, match="unrecognised"):
        U.scale_factor("kurus")


def test_a_post_switch_period_with_no_pdf_is_unknown():
    assert U.resolve_unit("2026Q2", pdf_path=None) is None
    with pytest.raises(ValueError, match="UNKNOWN"):
        U.scale_factor(U.resolve_unit("2026Q2", pdf_path=None))


# --- the detector itself ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Tutarlar Bin Türk Lirası olarak ifade edilmiştir", "bin"),
    ("Amounts are expressed in Thousands of Turkish Lira", "bin"),
    ("Tutarlar Milyon Türk Lirası olarak", "milyon"),
    ("expressed in Million Turkish Lira", "milyon"),
    ("Milyar Türk Lirası", "milyar"),
    ("MILYON TURK LIRASI", "milyon"),
])
def test_the_declaration_is_read_in_either_language(text, expected):
    assert U.regex_unit([text]) == expected


def test_a_declaration_deep_in_the_front_matter_is_still_found():
    """Q4 filings hide it on p7-p17 behind the full annual opinion — the reason
    the window is 22 pages and not 8."""
    pages = ["cover"] * 16 + ["Tutarlar Milyon Türk Lirası olarak ifade edilmiştir"]
    assert U.regex_unit(pages) == "milyon"


def test_a_declaration_past_the_window_is_not_found():
    pages = ["cover"] * 30 + ["Milyon Türk Lirası"]
    assert U.regex_unit(pages) is None


def test_no_declaration_is_unknown_not_bin():
    assert U.regex_unit(["balance sheet", "cash flow"]) is None
