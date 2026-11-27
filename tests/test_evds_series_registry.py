"""The curated EVDS list: what the scraper polls, and which workflow polls it.

The 41 Bank Loans Tendency Survey series and the BIST overnight repo rate were
each read from EVDS on 2026-11-27 before being added (latest observations
2026-Q3 and 2026-11-26). These tests keep the list internally consistent; they
make no network calls.
"""
import collections

from src.scrapers import evds_client as evds
from src.scrapers import evds_scraper as es


def _survey():
    return [s for s in es.SERIES if s.code.startswith("TP.BKEA.")]


def test_no_series_is_listed_twice():
    dupes = [c for c, n in collections.Counter(s.code for s in es.SERIES).items() if n > 1]
    assert not dupes, dupes


def test_every_series_is_polled_by_a_workflow():
    # A frequency no cadence group names is fetched by neither the daily nor
    # the Saturday run: declared, and never arriving.
    polled = set().union(*es.FREQUENCY_GROUPS.values())
    orphans = [s.code for s in es.SERIES if s.freq not in polled]
    assert not orphans, orphans


def test_the_overnight_repo_rate_is_polled_every_workday():
    s = next(s for s in es.SERIES if s.code == "TP.AOFOBAP")
    assert s.freq == evds.FREQ_WORKDAY
    assert s.freq in es.FREQUENCY_GROUPS["daily"]


def test_the_credit_survey_is_quarterly_and_waits_for_saturday():
    survey = _survey()
    assert 30 <= len(survey) <= 50, len(survey)
    assert {s.freq for s in survey} == {evds.FREQ_QUARTERLY}
    assert all(s.freq not in es.FREQUENCY_GROUPS["daily"] for s in survey)
    for s in survey:                      # a real question of the 128 asked
        n = int(s.code.rsplit(".S", 1)[1])
        assert 1 <= n <= 128, s.code


def test_survey_labels_do_not_assert_a_sign():
    # Which direction is positive is stated in TCMB's report table, not in the
    # EVDS metadata. A label reading "tightening" would assert it unverified.
    for s in _survey():
        low = s.label.lower()
        for word in ("tighten", "easing", "stronger", "weaker", "increase", "decrease"):
            assert word not in low, (s.code, s.label)
