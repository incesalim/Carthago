"""A restated comparative requires its exact, independently disclosed adjustment."""
from copy import deepcopy

import pytest

from src.audit_reports import equity_opening_scope as scope
from src.audit_reports.validator import check_equity_change


def source_rows():
    review = scope._reviews()[0]
    current = [dict(hierarchy=h, period_type="current", **deepcopy(values))
               for h, values in review["current"].items()]
    prior = dict(hierarchy="", item_name="Balances at end of the period",
                 period_type="prior", **deepcopy(review["prior_closing"]))
    return current, prior


def opening_failures(current, prior, bank="EXIM", period="2025Q4", kind="unconsolidated"):
    result = check_equity_change(
        [*current, prior], period=period, bank_ticker=bank, kind=kind)
    return [f for f in result.failures if f["check"] == "eq_open_close"]


def test_explicit_policy_adjustment_reconciles_restated_prior_without_changing_data():
    current, prior = source_rows()
    before = deepcopy((current, prior))
    assert opening_failures(current, prior, bank=None)
    assert scope.reviewed_adjusted_opening(
        current, prior, bank_ticker="EXIM", period="2025Q4", kind="unconsolidated") == 93824944
    assert not opening_failures(current, prior)
    assert (current, prior) == before
    assert current[0]["total_equity"] == 93006644


@pytest.mark.parametrize("bank,period,kind", [
    ("EXIM", "2024Q4", "unconsolidated"),
    ("EXIM", "2025Q4", "consolidated"),
    ("OTHER", "2025Q4", "unconsolidated"),
    (None, "2025Q4", "unconsolidated"),
    ("EXIM", "2025Q4", None),
])
def test_other_or_missing_partition_keeps_original_warning(bank, period, kind):
    current, prior = source_rows()
    assert opening_failures(current, prior, bank, period, kind)


@pytest.mark.parametrize("h,field", [
    ("I", "paid_in_capital"),
    ("II", "prior_period_profit_loss"),
    ("2.2", "total_equity"),
    ("2.2", "paid_in_capital"),
    ("III", "prior_period_profit_loss"),
])
@pytest.mark.parametrize("mutation", ["null", "changed", "missing"])
def test_each_independent_operand_remains_required(h, field, mutation):
    current, prior = source_rows()
    row = next(r for r in current if r["hierarchy"] == h)
    if mutation == "missing":
        del row[field]
    else:
        row[field] = None if mutation == "null" else row[field] + 1
    assert opening_failures(current, prior)


def test_prior_component_change_or_missing_adjustment_row_cannot_inherit_review():
    current, prior = source_rows()
    prior["period_net_profit_loss"] = None
    assert opening_failures(current, prior)
    current, prior = source_rows()
    assert opening_failures([r for r in current if r["hierarchy"] != "2.2"], prior)
    assert opening_failures([*current, deepcopy(current[1])], prior)


def test_changed_inputs_with_same_difference_are_not_treated_as_a_reviewed_residual():
    current, prior = source_rows()
    for row in current:
        if row["hierarchy"] in {"I", "III"}:
            row["prior_period_profit_loss"] += 1
            row["total_equity"] += 1
    prior["prior_period_profit_loss"] += 1
    prior["total_equity"] += 1
    assert opening_failures(current, prior)


def test_only_the_printed_adjustment_can_be_used(monkeypatch):
    current, prior = source_rows()
    reviews = deepcopy(scope._reviews())
    reviews[0]["adjustment"] = 818301
    monkeypatch.setattr(scope, "_reviews", lambda: reviews)
    assert opening_failures(current, prior)
