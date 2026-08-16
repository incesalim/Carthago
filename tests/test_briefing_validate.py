"""The briefing contradiction gate (src/news/briefing_validate.py).

The load-bearing case is the one the live 2026-08-16 briefing shipped: a
transition bullet ("overdraft … is 1%, down from 2%") beside a separate bare
bullet ("a limit of 2% has been introduced for overdraft"). The old raw-set
comparison saw {1,2} ∩ {2} and called it agreement; transition-aware current
values ({1} vs {2}) call it the conflict a reader experiences. The other
tests pin the documented false-positive shapes that made earlier versions of
this gate unusable — they must stay green forever.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.news.briefing_validate import (  # noqa: E402
    _transition_stale_values,
    find_contradictions,
)

# The live 2026-08-16 Loan Growth Caps section, verbatim.
LIVE_LOAN_BULLETS = [
    "The eight-week growth limit for general-purpose loans extended to consumers is 3%, down from 4%.",
    "The eight-week growth limit for vehicle loans extended to consumers is 3%, down from 4%.",
    "The eight-week growth limit for overdraft account limits extended to consumers is 1%, down from 2%.",
    "The eight-week growth limit for Turkish lira loans extended to SMEs is 4.5%, down from 5%.",
    "The eight-week growth limit for Turkish lira loans extended to non-SME enterprises is 2%, down from 3%.",
    "The eight-week growth limit for foreign currency loans is 0.5%.",
    "An eight-week growth limit of 2% has been introduced for overdraft account limits allocated to consumers.",
]


def test_transition_stale_values_reads_the_from_clause():
    assert _transition_stale_values("is 1%, down from 2%.") == {"2"}
    assert _transition_stale_values("raised from 30% to 32%") == {"30"}
    assert _transition_stale_values("the cap is 3%") == set()


def test_live_2026_08_16_overdraft_pair_is_a_conflict():
    """The exact shape that shipped: the raw sets intersect on the superseded
    2, so the old comparison passed it. Current-value comparison must not."""
    conflicts = find_contradictions(LIVE_LOAN_BULLETS)
    assert len(conflicts) == 1, conflicts
    assert conflicts[0]["subject"] == "loan:overdraft"
    assert conflicts[0]["a_pcts"] == ["1"]
    assert conflicts[0]["b_pcts"] == ["2"]


def test_stripping_the_stale_bullet_clears_the_section():
    assert find_contradictions(LIVE_LOAN_BULLETS[:-1]) == []


def test_transition_bullet_alone_is_not_a_conflict():
    assert find_contradictions(
        ["The overdraft growth limit is 1%, down from 2%."]) == []


def test_bare_bullet_agreeing_on_the_current_value_is_fine():
    assert find_contradictions([
        "The overdraft growth limit is 1%, down from 2%.",
        "Overdraft account limits may grow at most 1% over eight weeks.",
    ]) == []


def test_documented_exclusion_false_positive_stays_fixed():
    """'commercial loans (excluding overdraft) adjusted to 4.5%' must not read
    as an overdraft rule — the false positive that once withheld a correct
    2026-07-12 briefing (see _EXCLUSION_RE)."""
    assert find_contradictions([
        "The growth limit for commercial loans (excluding overdraft accounts) was adjusted to 4.5%.",
        "The eight-week growth limit for overdraft account limits extended to consumers is 1%, down from 2%.",
    ]) == []


def test_rr_bullets_stay_unflagged():
    """The base FX ratio and the terminated 2.5% surcharge share their whole
    vocabulary — the 3-part RR key must keep them apart (the false-positive
    class that made three flat-regex gate versions unusable)."""
    assert find_contradictions([
        "The reserve requirement ratio for foreign currency deposits/participation funds has been revised to 32% for demand deposits and deposits with maturities up to 1 month, and 28% for deposits with longer maturities.",
        "The additional Turkish lira reserve requirement ratio for FX deposits/participation funds, which was introduced in 2023 and applied at 2.5%, has been terminated.",
    ]) == []


def test_distinct_rules_with_different_values_do_not_collide():
    """general-purpose 3% vs overdraft 1% are different rules — the collision
    that made the original generic-vocabulary approach unusable."""
    assert find_contradictions([
        "The eight-week growth limit for general-purpose loans is 3%.",
        "The eight-week growth limit for overdraft account limits is 1%.",
    ]) == []
