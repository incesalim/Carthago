"""Scheduled refreshes poll by source cadence and stay write-free when quiet."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evds_frequency_groups_follow_the_series_metadata():
    e = _module("evds_cadence", "src/scrapers/evds_scraper.py")
    daily = e.parse_frequency_groups("daily")
    assert daily == {e.evds.FREQ_DAILY, e.evds.FREQ_WORKDAY}
    assert e.parse_frequency_groups("weekly,monthly") == {
        e.evds.FREQ_WEEKLY, e.evds.FREQ_BIWEEKLY, e.evds.FREQ_MONTHLY,
    }
    assert e.parse_frequency_groups("all") is None


def test_quiet_refresh_skips_packaging_and_reports_false(tmp_path, monkeypatch):
    r = _module("refresh_quiet", "scripts/refresh.py")
    db = tmp_path / "snapshot.db"
    db.write_bytes(b"stable sqlite placeholder")
    change_file = tmp_path / "changed.txt"
    monkeypatch.setattr(r, "DB_PATH", db)
    monkeypatch.setattr(r, "DB_GZ", tmp_path / "snapshot.db.gz")
    monkeypatch.setattr(r, "_run_step", lambda *a, **k: None)
    packed: list[str] = []
    monkeypatch.setattr(r, "vacuum", lambda: packed.append("vacuum"))
    monkeypatch.setattr(r, "gzip_db", lambda: packed.append("gzip"))
    monkeypatch.setattr(sys, "argv", ["refresh.py", "--change-file", str(change_file)])

    r.main()

    assert change_file.read_text(encoding="utf-8") == "false"
    assert packed == []


def test_the_daily_evds_workflow_cannot_run_slow_or_unrelated_lanes():
    wf = (REPO / ".github/workflows" / "refresh-evds-daily.yml").read_text(
        encoding="utf-8")
    assert "--evds-frequencies daily" in wf
    for flag in ("--skip-nonbank", "--skip-tbb", "--skip-tkbb", "--skip-kap",
                 "--skip-tefas", "--skip-faaliyet", "--skip-tuik"):
        assert flag in wf
    assert wf.count("steps.refresh.outputs.changed == 'true'") >= 3


def test_audit_is_scheduled_only_in_filing_windows_and_acquire_is_manual():
    refresh = (REPO / ".github/workflows" / "refresh-audit.yml").read_text(
        encoding="utf-8")
    acquire = (REPO / ".github/workflows" / "acquire-audit.yml").read_text(
        encoding="utf-8")
    assert 'cron: "0 4 20-31 1,4,7,10 *"' in refresh
    assert 'cron: "0 4 1-29 2 *"' in refresh
    assert 'cron: "0 4 1-20 5,8,11 *"' in refresh
    assert 'cron: "0 4 1-15 3 *"' in refresh
    assert "  schedule:" not in acquire


def test_bddk_drops_the_saturday_backstop_and_daily_monthly_poll():
    wf = (REPO / ".github/workflows" / "refresh-bddk-bulletins.yml").read_text(
        encoding="utf-8")
    assert 'cron: "0 2 * * 6"' not in wf
    assert 'cron: "0 13 * * *"' not in wf
    assert 'cron: "0 13 1-5 * *"' in wf


def test_changed_bulletin_runs_build_then_push_once_then_package():
    for name in ("refresh-bddk-bulletins.yml", "refresh-data.yml"):
        wf = (REPO / ".github/workflows" / name).read_text(encoding="utf-8")
        build = wf.index("python scripts/build_api_catalog.py")
        push = wf.index("python scripts/push_to_d1.py")
        package = wf.rindex("gzip.open(gz")
        assert build < push < package
        assert wf.count("python scripts/push_to_d1.py") == 1


def test_evds_packages_confirmed_push_state_not_the_pre_push_database():
    wf = (REPO / ".github/workflows" / "refresh-evds-daily.yml").read_text(
        encoding="utf-8")
    assert wf.index("python scripts/push_to_d1.py") < wf.rindex("gzip.open(gz")
    assert "--defer-packaging" in wf
