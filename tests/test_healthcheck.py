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
