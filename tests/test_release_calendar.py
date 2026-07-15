"""The TCMB calendar parser must turn the published table into clean ISO events.

Runs against a saved copy of the calendar page (tests/fixtures/tcmb_calendar.html,
captured 2026-07-15) so it is deterministic and offline — no network in CI.
Stdlib + lxml (both CI deps). Sibling of the other pure-parser tests.
"""

from pathlib import Path

from src.release_calendar.scraper import parse_calendar, parse_date

FIXTURE = Path(__file__).parent / "fixtures" / "tcmb_calendar.html"


def test_parse_date_handles_the_published_format():
    assert parse_date("January 22, 2026") == "2026-01-22"
    assert parse_date("December 10, 2026") == "2026-12-10"
    assert parse_date("  July 3, 2027 ") == "2027-07-03"
    # Blank / junk cells yield no date, so a sparse column just produces no event.
    assert parse_date("") is None
    assert parse_date("—") is None
    assert parse_date("TBD") is None


def test_parses_the_four_event_kinds_from_the_fixture():
    events = parse_calendar(FIXTURE.read_text(encoding="utf-8"))
    kinds = {e["kind"] for e in events}
    assert kinds == {
        "mpc_decision",
        "mpc_minutes",
        "inflation_report",
        "financial_stability_report",
    }
    # Every event is ('tcmb', kind, ISO date, title, url), sorted by date.
    assert all(e["source"] == "tcmb" for e in events)
    assert all(len(e["event_date"]) == 10 and e["event_date"][4] == "-" for e in events)
    assert events == sorted(events, key=lambda e: (e["event_date"], e["kind"]))


def test_the_mpc_decision_dates_match_the_published_calendar():
    events = parse_calendar(FIXTURE.read_text(encoding="utf-8"))
    mpc = [e["event_date"] for e in events if e["kind"] == "mpc_decision"]
    # These are exactly the dates that were hand-transcribed into ahead.ts's
    # MPC_DATES — the scrape reproduces them, which is why it can replace them.
    assert mpc[:8] == [
        "2026-01-22", "2026-03-12", "2026-04-22", "2026-06-11",
        "2026-07-23", "2026-09-10", "2026-10-22", "2026-12-10",
    ]


def test_a_dateless_page_yields_no_events_rather_than_garbage():
    # If TCMB serves the WCM shell without the table (the failure the browserless
    # fetch used to hit), the parser returns [] so main() can fail loudly instead
    # of wiping good rows.
    assert parse_calendar("<html><body><p>no table here</p></body></html>") == []
