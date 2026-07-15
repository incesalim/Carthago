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


def test_holding_the_latest_month_is_fresh_between_releases(monkeypatch):
    # THE fix: with May held and the next bulletin not due until 12 Aug, an early
    # July check must be silent — no daily "stale" alarm while the data is current.
    import datetime as _dt

    class FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 15)

    monkeypatch.setattr(healthcheck, "date", FixedDate)
    assert healthcheck.monthly_problem("2026-05") is None


def test_a_genuinely_overdue_month_still_alerts(monkeypatch):
    # Stuck two months back (next was due ~12 Jun, it's mid-July) → real miss.
    import datetime as _dt

    class FixedDate(_dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 15)

    monkeypatch.setattr(healthcheck, "date", FixedDate)
    msg = healthcheck.monthly_problem("2026-03")
    assert msg and "due" in msg


def test_missing_monthly_data_alerts():
    assert healthcheck.monthly_problem(None) == "Monthly bulletin: no data"
