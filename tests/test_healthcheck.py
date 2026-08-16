"""Tests for scripts/healthcheck.py timestamp parsing — D1 returns timestamps in
two shapes ("YYYY-MM-DD HH:MM:SS" and ISO with Z), and staleness math depends on
parsing both correctly."""
import healthcheck  # on sys.path via pyproject pythonpath


def test_hours_since_parses_space_format():
    h = healthcheck.hours_since("2026-06-04 18:00:00")
    assert h is not None and h > 0


def test_hours_since_parses_iso_z():
    h = healthcheck.hours_since("2026-06-05T06:00:00Z")
    assert h is not None and h > 0


def test_hours_since_none_and_garbage():
    assert healthcheck.hours_since(None) is None
    assert healthcheck.hours_since("not-a-date") is None


def test_recent_timestamp_is_small_age(monkeypatch):
    # A timestamp ~2h ago should read as roughly 2 hours, not negative/huge.
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    h = healthcheck.hours_since(ts)
    assert 1.5 < h < 2.5


# --- schedule-aware monthly freshness (the false-alarm fix) -----------------

def test_next_monthly_due_is_day12_of_month_plus_3():
    # Month M's bulletin lands ~12th of M+2, so the month AFTER `period` is due
    # ~12th of period.month + 3. Mirrors nextMonthlyBulletinDue in ahead.ts.
    from datetime import date
    assert healthcheck.next_monthly_due("2026-05") == date(2026, 8, 12)


def test_next_monthly_due_rolls_the_year():
    from datetime import date
    assert healthcheck.next_monthly_due("2026-11") == date(2027, 2, 12)
    assert healthcheck.next_monthly_due("2026-12") == date(2027, 3, 12)


def test_fresh_when_bddk_has_not_published_the_next_month():
    # THE fix: ask BDDK, don't guess. If BDDK hasn't published the next month, we
    # hold the latest data that exists → silent, no daily "stale" alarm.
    assert healthcheck.monthly_problem("2026-05", probe=lambda y, m: False) is None


def test_alerts_when_next_month_is_published_but_missing():
    # BDDK published the next month and we don't have it → the extractor missed it.
    msg = healthcheck.monthly_problem("2026-05", probe=lambda y, m: True)
    assert msg and "2026-06 is published by BDDK" in msg


def test_probe_asks_about_the_month_after_the_one_we_hold():
    seen = []
    healthcheck.monthly_problem("2026-12", probe=lambda y, m: seen.append((y, m)) or False)
    assert seen == [(2027, 1)]  # rolls the year


def test_probe_failure_falls_back_to_the_schedule(monkeypatch):
    # BDDK unreachable → schedule backstop; overdue past grace still surfaces.
    import datetime as _dt

    class FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 15)

    def boom(y, m):
        raise RuntimeError("bddk down")

    monkeypatch.setattr(healthcheck, "date", FixedDate)
    # Held March: next (April) due ~12 Jun, mid-July → overdue → alert via backstop.
    assert healthcheck.monthly_problem("2026-03", probe=boom)
    # Held May: next (June) due ~12 Aug, still future → fresh even with probe down.
    assert healthcheck.monthly_problem("2026-05", probe=boom) is None


def test_missing_monthly_data_alerts():
    assert healthcheck.monthly_problem(None) == "Monthly bulletin: no data"


def test_monthly_freshness_shape_for_the_admin_panel():
    # The /admin panel + the source_freshness write depend on this dict shape.
    fresh = healthcheck.monthly_freshness("2026-05", probe=lambda y, m: False)
    assert fresh == {
        "status": "fresh",
        "latest_period": "2026-05",
        "next_period": "2026-06",
        "note": "2026-06 not yet published by BDDK",
    }
    stale = healthcheck.monthly_freshness("2026-05", probe=lambda y, m: True)
    assert stale["status"] == "stale"
    assert "missed a release" in stale["note"]


# --- the filing-season gap ---------------------------------------------------
#
# Every other check here asks whether data we HAVE went stale, and none of them
# could see 2026Q2: thirteen banks had published, the audit lane held none of
# them, and each daily run exited green because `new=0` is also what a quarter
# nobody filed looks like. The gap between a KAP results_filing and an
# extraction is the one comparison that separates those two worlds.
from datetime import date  # noqa: E402


def _gap_row(ticker, filed_on, period="2026Q2"):
    return {"ticker": ticker, "period": period, "filed_on": filed_on}


def test_no_gap_is_silent():
    assert healthcheck.filing_gap_problem([], today=date(2026, 8, 16)) is None


def test_a_bank_that_filed_and_was_not_acquired_alerts():
    msg = healthcheck.filing_gap_problem(
        [_gap_row("ISCTR", "2026-08-03")], today=date(2026, 8, 16))
    assert msg and "ISCTR" in msg and "2026Q2" in msg and "13d" in msg


def test_a_filing_inside_the_grace_window_is_not_yet_a_problem():
    """KAP precedes the bank's own IR page — TEB filed 07-23, the PDF appeared
    07-26. Alerting on the filing day would fire on every bank every quarter."""
    today = date(2026, 8, 16)
    assert healthcheck.filing_gap_problem(
        [_gap_row("KUVEYT", "2026-08-14")], today=today) is None
    assert healthcheck.filing_gap_problem(
        [_gap_row("KUVEYT", "2026-08-12")], today=today) is not None


def test_the_oldest_gap_is_named_first():
    msg = healthcheck.filing_gap_problem(
        [_gap_row("ICBCT", "2026-08-10"), _gap_row("TSKB", "2026-07-29")],
        today=date(2026, 8, 16))
    assert msg.index("TSKB") < msg.index("ICBCT"), msg
    assert "2 bank(s)" in msg


def test_a_broken_filed_on_never_takes_the_health_check_down():
    assert healthcheck.filing_gap_problem(
        [_gap_row("X", None), _gap_row("Y", "not-a-date")],
        today=date(2026, 8, 16)) is None


def test_the_query_is_flattened_before_it_reaches_wrangler(monkeypatch):
    """`wrangler d1 execute --command` does not survive an embedded newline;
    the readable triple-quoted SQL below would fail every run."""
    seen = {}

    class _Res:
        returncode = 0
        stdout = '[{"results": []}]'
        stderr = ""

    def _run(cmd, **kw):
        seen["cmd"] = cmd
        return _Res()

    monkeypatch.setattr(healthcheck.subprocess, "run", _run)
    healthcheck.query_d1_rows(healthcheck.FILING_GAP_SQL)
    assert "\n" not in seen["cmd"][-1]
    assert "bank_earnings" in seen["cmd"][-1]
