"""Scope reviews reconcile disclosed movements without hiding later corruption."""
from copy import deepcopy

import pytest

from src.audit_reports import equity_oci_scope as scope
from src.audit_reports.validator import check_equity_change


TARGETS = [
    ("ING", "2022Q1", "consolidated", 590540),
    ("ING", "2022Q1", "unconsolidated", 590540),
    ("KUVEYT", "2022Q1", "consolidated", 3684903),
]


def source_rows(bank, period, kind):
    review = next(r for r in scope._reviews()
                  if (r["bank_ticker"], r["period"], r["kind"]) == (bank, period, kind))
    eq = [dict(hierarchy=h, period_type="current", **deepcopy(values))
          for h, values in review["equity"].items()]
    oci = [dict(hierarchy=h, amount=amount) for h, amount in review["oci"].items()]
    return eq, oci


def cross_failures(eq, oci, bank, period, kind):
    return [f for f in check_equity_change(
        eq, oci, period=period, bank_ticker=bank, kind=kind).failures
            if f["check"] == "eq_oci_cross"]


@pytest.mark.parametrize("bank,period,kind,expected", TARGETS)
def test_exact_source_comparison_reconciles_without_mutating_figures(bank, period, kind, expected):
    eq, oci = source_rows(bank, period, kind)
    before = deepcopy((eq, oci))
    assert cross_failures(eq, oci, None, period, kind)
    assert scope.reviewed_equity_oci_total(
        eq, oci, bank_ticker=bank, period=period, kind=kind) == expected
    assert not cross_failures(eq, oci, bank, period, kind)
    assert (eq, oci) == before


@pytest.mark.parametrize("bank,period,kind,expected", TARGETS)
@pytest.mark.parametrize("context", [
    ("OTHER", "2022Q1", "consolidated"),
    ("ING", "2022Q2", "consolidated"),
    ("KUVEYT", "2022Q1", "unconsolidated"),
    (None, "2022Q1", "consolidated"),
])
def test_review_never_applies_to_another_or_missing_partition(bank, period, kind, expected, context):
    eq, oci = source_rows(bank, period, kind)
    assert cross_failures(eq, oci, *context)


@pytest.mark.parametrize("new_value", [None, 1])
@pytest.mark.parametrize("row_h,field", [
    ("IV", "oci_reclassified_1"),
    ("X", "paid_in_capital"),
    ("X", "period_net_profit_loss"),
])
def test_translation_review_requires_source_zero_and_fx_only_other_movement(row_h, field, new_value):
    eq, oci = source_rows("ING", "2022Q1", "consolidated")
    next(r for r in eq if r["hierarchy"] == row_h)[field] = new_value
    assert cross_failures(eq, oci, "ING", "2022Q1", "consolidated")


@pytest.mark.parametrize("new_value", [None, 26315])
def test_translation_review_requires_independent_oci_translation(new_value):
    eq, oci = source_rows("ING", "2022Q1", "consolidated")
    next(r for r in oci if r["hierarchy"] == "2.2.1")["amount"] = new_value
    assert cross_failures(eq, oci, "ING", "2022Q1", "consolidated")


@pytest.mark.parametrize("bank,period,kind,expected", TARGETS)
def test_missing_or_duplicate_operands_leave_cross_warning(bank, period, kind, expected):
    eq, oci = source_rows(bank, period, kind)
    assert cross_failures(eq, oci[1:], bank, period, kind)
    assert cross_failures(eq, [*oci, deepcopy(oci[0])], bank, period, kind)
    assert cross_failures([*eq, deepcopy(eq[0])], oci, bank, period, kind)
    eq[0]["period_net_profit_loss"] = None
    assert cross_failures(eq, oci, bank, period, kind)


def test_participant_fund_is_not_recalculated_as_a_residual():
    eq, oci = source_rows("KUVEYT", "2022Q1", "consolidated")
    # Preserve I+II=III and the same EQ-to-OCI difference while changing the
    # source profit and equity inputs. A residual-based rule would wrongly pass.
    for r in oci:
        if r["hierarchy"] in {"I", "III"}:
            r["amount"] += 1
    for field in ("period_net_profit_loss", "total_equity", "total_equity_incl_minority"):
        eq[0][field] += 1
    assert cross_failures(eq, oci, "KUVEYT", "2022Q1", "consolidated")


def test_participant_fund_uses_the_printed_amount_only(monkeypatch):
    eq, oci = source_rows("KUVEYT", "2022Q1", "consolidated")
    reviews = deepcopy(scope._reviews())
    next(r for r in reviews if r["bank_ticker"] == "KUVEYT")["adjustment"] = 76672
    monkeypatch.setattr(scope, "_reviews", lambda: reviews)
    assert cross_failures(eq, oci, "KUVEYT", "2022Q1", "consolidated")


@pytest.mark.parametrize("bank,period,eq_amount,oci_amount", [
    ("ALBRK", "2026Q2", 4071000, 4073000),
    ("ATBANK", "2023Q4", 307687, -307687),
    ("EMLAK", "2024Q4", 7771081, 7776953),
])
def test_unresolved_printed_discrepancies_still_alert(bank, period, eq_amount, oci_amount):
    eq = [{"hierarchy": "IV", "period_type": "current", "total_equity": eq_amount}]
    oci = [{"hierarchy": "III", "amount": oci_amount}]
    assert cross_failures(eq, oci, bank, period, "consolidated" if bank == "ALBRK" else "unconsolidated")
