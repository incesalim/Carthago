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


# --- the regulator's registry, and the red tier (2026-11-27) ------------------
#
# The KAP diff above can only name banks that file on KAP: three of the 38
# never do, and through 2026Q3 it reported 17 gaps against 24 reports the
# registry held. The registry half closes that. And a gap that old now fails
# the run instead of sharing one amber list with "TEFAS funds: stale".

import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from src.audit_reports import document_origin_listing as listing  # noqa: E402


def _listing_html(*rows):
    """The regulator's results panel: one row per (name, year, month, basis)."""
    cells = "".join(
        f"<tr><td>{name}</td><td>{year}</td><td>{month}</td><td>{basis}</td>"
        '<td><a href="/BdrUyg/Home/DosyaIndir?raporUrl=x">indir</a></td></tr>'
        for name, year, month, basis in rows)
    return f'<div id="divTab_raporlar"><table>{cells}</table></div>'.encode("utf-8")


def _wire_registry(monkeypatch, tmp_path, body, held, first_filed):
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"banks": {
        "ATBANK": "ARAP TÜRK BANKASI A.Ş.", "QNBFB": "QNB FİNANSBANK A.Ş."}}),
        encoding="utf-8")
    monkeypatch.setattr(listing, "fetch_listing", lambda: (body, {}))
    monkeypatch.setattr(listing, "NAMES_PATH", names)

    def _query(sql):
        if "GROUP BY period" in sql:
            return [{"period": "2026Q3", "filed_on": first_filed}]
        assert "2026Q3" in sql          # only the registry's newest period
        return [{"ticker": t} for t in held]
    monkeypatch.setattr(healthcheck, "query_d1_rows", _query)


def test_the_registry_names_a_filed_report_the_lane_does_not_hold(monkeypatch, tmp_path):
    _wire_registry(monkeypatch, tmp_path, _listing_html(
        ("QNB FİNANSBANK A.Ş.", "2026", "9", "SOLO"),
        ("ARAP TÜRK BANKASI A.Ş.", "2026", "9", "SOLO"),
        # An older period is still listed; only the newest one is a gap.
        ("QNB FİNANSBANK A.Ş.", "2026", "6", "SOLO")), held=["QNBFB"],
        first_filed="2026-10-27")
    # ATBANK never files on KAP, so the KAP diff cannot see it at all.
    assert healthcheck.registry_gap_rows([]) == [
        {"ticker": "ATBANK", "period": "2026Q3", "filed_on": "2026-10-27",
         "source": "registry"}]


def test_a_bank_the_kap_half_already_named_is_not_listed_twice(monkeypatch, tmp_path):
    _wire_registry(monkeypatch, tmp_path, _listing_html(
        ("ARAP TÜRK BANKASI A.Ş.", "2026", "9", "SOLO")), held=[],
        first_filed="2026-10-27")
    assert healthcheck.registry_gap_rows(
        [_gap_row("ATBANK", "2026-10-30", period="2026Q3")]) == []


def test_an_unreadable_registry_leaves_the_kap_half_standing(monkeypatch, tmp_path, capsys):
    def _boom():
        raise ConnectionError("listing down")
    monkeypatch.setattr(listing, "fetch_listing", _boom)
    assert healthcheck.registry_gap_rows([]) == []
    assert "registry filing-gap check unavailable" in capsys.readouterr().err


def test_an_undated_registry_filing_is_listed_but_never_red():
    rows = [{"ticker": "ATBANK", "period": "2026Q3", "filed_on": None,
             "source": "registry"}]
    msg = healthcheck.filing_gap_problem(rows, today=date(2026, 12, 1))
    assert msg and "ATBANK (undated, registry)" in msg
    assert healthcheck.filing_gap_red(rows, today=date(2026, 12, 1)) is False


def test_a_filing_unheld_for_ten_days_is_red_not_amber():
    today = date(2026, 11, 27)
    nine = [_gap_row("QNBFB", "2026-11-18", period="2026Q3")]
    ten = [_gap_row("QNBFB", "2026-11-17", period="2026Q3")]
    assert healthcheck.filing_gap_problem(nine, today=today) is not None
    assert healthcheck.filing_gap_red(nine, today=today) is False
    assert healthcheck.filing_gap_red(ten, today=today) is True


def _run_main(monkeypatch, capsys, gap_rows):
    """main() over a healthy D1 with only the filing gap varying."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sent = []
    monkeypatch.setattr(healthcheck, "query_d1", lambda sql=None: {
        "monthly_period": "2099-12", "weekly": now, "evds": now, "news": now,
        "tefas": now, "audit": now, "audit_failed": 0})
    monkeypatch.setattr(healthcheck, "monthly_freshness", lambda period, probe=None: {
        "latest_period": "2099-12", "status": "fresh", "note": ""})
    for name in ("write_freshness", "write_coverage_trend"):
        monkeypatch.setattr(healthcheck, name, lambda *a: None)
    monkeypatch.setattr(healthcheck, "d1_spend_problem", lambda used=None: None)
    monkeypatch.setattr(healthcheck, "audit_spine_problem", lambda *a, **k: None)
    monkeypatch.setattr(healthcheck, "load_filing_gap_rows", lambda: list(gap_rows))
    monkeypatch.setattr(healthcheck, "notify", sent.append)
    return healthcheck.main(), sent, capsys.readouterr().out


def test_a_ten_day_gap_fails_the_run_in_red(monkeypatch, capsys):
    today = datetime.now(timezone.utc).date()
    code, sent, out = _run_main(monkeypatch, capsys, [
        _gap_row("QNBFB", (today - timedelta(days=10)).isoformat(), period="2026Q3")])
    assert code == 1
    assert sent[0].startswith("🔴 BDDK data health")
    assert "QNBFB" in out


def test_a_younger_gap_stays_amber_and_the_run_stays_green(monkeypatch, capsys):
    today = datetime.now(timezone.utc).date()
    code, sent, _ = _run_main(monkeypatch, capsys, [
        _gap_row("QNBFB", (today - timedelta(days=6)).isoformat(), period="2026Q3")])
    assert code == 0
    assert sent[0].startswith("🟡 BDDK data health")


def test_tefas_limit_tolerates_the_weekly_cadence():
    # Only the Saturday run fetches TEFAS, so a Friday data date is 8.1 days
    # old when the next one starts. At the old 120h that fired every Wed–Fri.
    limit = dict((k, h) for k, _label, h in healthcheck.THRESHOLDS)["tefas"]
    assert limit > 8.1 * 24


# --- the coverage spine marker + fleet trend (2026-09-18) --------------------
#
# push_to_d1 stamps source_freshness 'audit_spine' on every spine push; the
# health check alerts when the marker is missing, D1 holds fewer lanes than the
# registry declares, or the spine has frozen. The trend write is telemetry and
# must never take the check down.


def _spine_row(checked_ago_h=None, declared=20, in_d1=20):
    checked = (
        (datetime.now(timezone.utc) - timedelta(hours=checked_ago_h))
        .strftime("%Y-%m-%d %H:%M:%S")
        if checked_ago_h is not None else None
    )
    return [{"checked_at": checked, "lanes_declared": str(declared) if declared else None,
             "lanes_in_d1": in_d1}]


def test_spine_check_alerts_when_no_marker():
    assert healthcheck.audit_spine_problem(rows=_spine_row(checked_ago_h=None), registry_lanes=20) \
        == "Coverage spine: no sync marker — sync_audit_expected has never pushed"


def test_spine_check_alerts_on_lane_parity_gap():
    # The risk_profile blind spot: 20 lanes registered, 19 in D1.
    msg = healthcheck.audit_spine_problem(rows=_spine_row(checked_ago_h=2, declared=20, in_d1=19),
                                          registry_lanes=20)
    assert msg is not None and "D1 holds 19" in msg and "20 lanes" in msg


def test_spine_check_alerts_when_the_sync_predates_a_new_lane():
    # Marker shipped 19 lanes; the registry has since grown to 20 — the last
    # sync predates the new lane even though D1 matches the marker.
    msg = healthcheck.audit_spine_problem(rows=_spine_row(checked_ago_h=2, declared=19, in_d1=19),
                                          registry_lanes=20)
    assert msg is not None and "last sync shipped 19" in msg


def test_spine_check_alerts_when_frozen():
    msg = healthcheck.audit_spine_problem(
        rows=_spine_row(checked_ago_h=(healthcheck.SPINE_STALE_DAYS + 2) * 24, declared=20, in_d1=20),
        registry_lanes=20)
    assert msg is not None and "last sync" in msg and "d ago" in msg


def test_spine_check_is_quiet_when_healthy():
    assert healthcheck.audit_spine_problem(rows=_spine_row(checked_ago_h=3, declared=20, in_d1=20),
                                           registry_lanes=20) is None


def test_spine_check_never_takes_the_run_down(monkeypatch):
    def boom(_sql):
        raise RuntimeError("d1 down")
    monkeypatch.setattr(healthcheck, "query_d1_rows", boom)
    assert healthcheck.audit_spine_problem(registry_lanes=20) is None


def test_coverage_trend_writes_one_row(monkeypatch):
    queries, writes = [], []

    def fake_rows(sql):
        queries.append(" ".join(sql.split()))
        if "GROUP BY status" in queries[-1]:
            return [{"status": "ok", "n": 900}, {"status": "error", "n": 41},
                    {"status": "missing", "n": 12}]
        return [{"lanes": 20}]

    monkeypatch.setattr(healthcheck, "query_d1_rows", fake_rows)
    monkeypatch.setattr(healthcheck, "execute_d1", lambda sql: writes.append(sql) or True)
    healthcheck.write_coverage_trend()
    assert len(writes) == 1
    assert writes[0].startswith("INSERT INTO coverage_trend")
    # columns in declared order: ok, manual, error, missing, not_expected, lanes
    assert "900, 0, 41, 12, 0, 20" in writes[0]


def test_coverage_trend_is_non_fatal(monkeypatch):
    def boom(_sql):
        raise RuntimeError("d1 down")
    monkeypatch.setattr(healthcheck, "query_d1_rows", boom)
    monkeypatch.setattr(healthcheck, "execute_d1", lambda sql: True)
    healthcheck.write_coverage_trend()  # must not raise
