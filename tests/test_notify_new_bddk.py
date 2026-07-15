"""The 'new BDDK data' notification must fire only when a period actually advanced
— a routine run that fetched nothing new must stay quiet (no spam)."""
import notify_new_bddk as n


def test_weekly_advance_notifies():
    msgs = n.new_messages("2026-07-03", 202605, "2026-07-10", 202605)
    assert msgs == ["Weekly bulletin — week ending 2026-07-10"]


def test_monthly_advance_notifies_with_readable_period():
    msgs = n.new_messages("2026-07-10", 202605, "2026-07-10", 202606)
    assert msgs == ["Monthly bulletin — 2026-06"]


def test_both_advancing_reports_both():
    msgs = n.new_messages("2026-07-03", 202605, "2026-07-17", 202606)
    assert msgs == [
        "Weekly bulletin — week ending 2026-07-17",
        "Monthly bulletin — 2026-06",
    ]


def test_nothing_new_is_silent():
    assert n.new_messages("2026-07-10", 202606, "2026-07-10", 202606) == []


def test_never_notifies_on_a_regression_or_empty():
    # A smaller/empty "now" (shouldn't happen, but must not ping) stays quiet.
    assert n.new_messages("2026-07-10", 202606, "", 0) == []
    assert n.new_messages("2026-07-10", 202606, "2026-07-03", 202605) == []
