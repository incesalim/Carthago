"""The hand-typed forward dates must not quietly run out.

Thin pytest wrapper around scripts/check_calendar_fresh.py, so the MPC calendar
running dry fails CI rather than silently dropping a row from five pages.
Sibling of tests/test_docs_sync.py.
"""

from datetime import date

from check_calendar_fresh import MIN_RUNWAY_DAYS, baseline_as_of, check, mpc_dates


def test_the_calendar_has_runway():
    problems = check()
    assert not problems, "\n".join(problems)


def test_mpc_dates_are_sorted_and_well_formed():
    dates = mpc_dates()
    assert dates, "no MPC dates parsed — check the regex against ahead.ts"
    assert dates == sorted(dates)
    assert all(len(d) == 10 for d in dates)


def test_it_fails_once_the_calendar_runs_dry():
    # The whole point: a schedule that has run out must SAY so, not vanish.
    last = date.fromisoformat(mpc_dates()[-1])
    problems = check(today=last)
    assert any("runs out" in p for p in problems)
    assert str(MIN_RUNWAY_DAYS) in "\n".join(problems)


def test_the_bbva_baseline_declares_its_vintage():
    # /economy carries it as a dated third-party scenario; the gate ages it out.
    assert baseline_as_of(), "BBVA_BASELINE.asOf not found in economy.ts"
