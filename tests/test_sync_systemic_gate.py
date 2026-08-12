"""The scrape alarm fired on healthy runs, and firing destroyed good work.

`sync_audit_reports.main()` ends with a systemic-failure guard meant to catch
"the scrape is broken" (a dead config, no network, rotated IR URLs). Between
2026-08-08 and 2026-08-12 it fired on five consecutive `refresh-audit.yml` runs
and each one exited before the D1 push and the R2 snapshot upload, so the same
eight 2026Q2 partitions were extracted and thrown away every morning.

Two independent defects, one test file:

1. **`pending` was missing from the scrape denominator.** A `not-a-report`
   verdict is a SUCCESSFUL fetch — the PDF downloaded and was inspected, it just
   is not a filing yet. Counting only `failed + new` measures the ratio over the
   few targets that resolved to a download, so with the corpus complete
   (`new` ~ 0) four permanently-unreachable URLs are 100% of a "batch" of four.

2. **The alarm exited 1, mid-job.** It is raised after extraction has already
   written the local DB, so a plain failure discards work the scrape problem
   never touched. It now exits `EXIT_SYSTEMIC` (8) and the workflows persist
   first and re-raise at the end.

The real numbers from the runs it broke are used as the fixtures below, so a
regression reproduces the actual outage rather than a hypothetical one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "sync_audit_gate", REPO / "scripts" / "sync_audit_reports.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(monkeypatch, tmp_path, scrape, extract, argv=()):
    """Drive main() with canned scrape/extract counts. Returns the exit code."""
    M = _mod()
    monkeypatch.setattr(M, "scrape_to_r2", lambda **kw: dict(scrape))
    monkeypatch.setattr(M, "extract_from_r2", lambda **kw: dict(extract))
    monkeypatch.setattr(
        sys, "argv",
        ["sync_audit_reports.py", "--db", str(tmp_path / "audit.db"), *argv])
    with pytest.raises(SystemExit) as e:
        M.main()
    # main() returns None on the happy path; pytest.raises would then fail, so
    # the happy path is expressed as an explicit exit below.
    return e.value.code


def _ok(monkeypatch, tmp_path, scrape, extract, argv=()):
    """Same, but for runs that are expected NOT to raise the alarm."""
    M = _mod()
    monkeypatch.setattr(M, "scrape_to_r2", lambda **kw: dict(scrape))
    monkeypatch.setattr(M, "extract_from_r2", lambda **kw: dict(extract))
    monkeypatch.setattr(
        sys, "argv",
        ["sync_audit_reports.py", "--db", str(tmp_path / "audit.db"), *argv])
    try:
        M.main()
    except SystemExit as e:            # a 0/None exit is still "did not alarm"
        assert not e.code, f"expected no alarm, got exit {e.code}"


CLEAN_EXTRACT = {"ok": 11, "fail": 0, "not_a_report": 2}


# --- 1. the denominator ------------------------------------------------------

@pytest.mark.parametrize("day,scrape", [
    # (date, the run's real [scrape] line)
    ("2026-08-10", {"new": 0, "pending": 104, "failed": 5, "skipped": 962}),
    ("2026-08-11", {"new": 0, "pending": 103, "failed": 6, "skipped": 962}),
    ("2026-08-12", {"new": 2, "pending": 104, "failed": 5, "skipped": 962}),
    # acquire-audit.yml, same day, same four dead URLs
    ("2026-08-12b", {"new": 3, "pending": 103, "failed": 6, "skipped": 964}),
])
def test_a_handful_of_dead_urls_is_not_a_systemic_failure(
        monkeypatch, tmp_path, day, scrape):
    """Every one of these fired before the fix and stalled the lane for a day.
    Worst case here is 6 of 112 — 5.4%, nowhere near the 25% threshold."""
    _ok(monkeypatch, tmp_path, scrape, CLEAN_EXTRACT)


def test_pending_is_counted_because_it_is_a_successful_fetch(monkeypatch, tmp_path):
    """THE fix. Identical failures; the only difference is whether the 103
    downloaded-and-inspected PDFs count as attempts. They do."""
    M = _mod()
    scrape = {"new": 0, "pending": 103, "failed": 6, "skipped": 962}
    denom = (scrape["failed"] + scrape["new"] + scrape["pending"])
    assert denom == 109
    assert scrape["failed"] / denom < 0.25          # correct: not systemic
    assert scrape["failed"] / (scrape["failed"] + scrape["new"]) == 1.0  # old: 100%
    assert M.EXIT_SYSTEMIC == 8
    _ok(monkeypatch, tmp_path, scrape, CLEAN_EXTRACT)


def test_a_truly_broken_scrape_still_fires(monkeypatch, tmp_path):
    """Network gone or config rotated: nothing downloads, so nothing lands in
    `pending` either and the ratio is 100% of everything attempted."""
    code = _run(monkeypatch, tmp_path,
                {"new": 0, "pending": 0, "failed": 40, "skipped": 0},
                CLEAN_EXTRACT)
    assert code == 8


def test_a_mostly_broken_scrape_fires_even_with_some_pending(monkeypatch, tmp_path):
    """Half the fleet unreachable is systemic whatever the pending count."""
    code = _run(monkeypatch, tmp_path,
                {"new": 2, "pending": 10, "failed": 40, "skipped": 0},
                CLEAN_EXTRACT)
    assert code == 8


def test_a_tiny_batch_still_cannot_trip_it(monkeypatch, tmp_path):
    """The >=4 floor is unchanged: one failure on a three-target run is noise."""
    _ok(monkeypatch, tmp_path,
        {"new": 1, "pending": 1, "failed": 1, "skipped": 900}, CLEAN_EXTRACT)


# --- 2. the exit code --------------------------------------------------------

def test_the_alarm_exits_8_not_1(monkeypatch, tmp_path):
    """1 means the run CRASHED and nothing may be persisted. 8 means the run
    finished and the numbers look wrong — the caller must still push and upload
    the snapshot before failing the job. Conflating them is what discarded six
    days of extraction."""
    code = _run(monkeypatch, tmp_path,
                {"new": 0, "pending": 0, "failed": 40, "skipped": 0},
                CLEAN_EXTRACT)
    assert code == 8, "a systemic alarm must be distinguishable from a crash"


def test_the_extract_gate_also_uses_the_systemic_code(monkeypatch, tmp_path):
    """A bad extraction batch is equally 'finished but wrong', and equally must
    not be silently pushed — but the caller, not this script, decides that."""
    code = _run(monkeypatch, tmp_path,
                {"new": 0, "pending": 100, "failed": 0, "skipped": 900},
                {"ok": 2, "fail": 8, "not_a_report": 0})
    assert code == 8


def test_a_clean_run_exits_zero(monkeypatch, tmp_path):
    _ok(monkeypatch, tmp_path,
        {"new": 3, "pending": 103, "failed": 6, "skipped": 964}, CLEAN_EXTRACT)


# --- 3. both workflows persist before re-raising -----------------------------

@pytest.mark.parametrize("wf,step_id", [
    ("refresh-audit.yml", "sync"),
    ("acquire-audit.yml", "scrape"),
])
def test_the_workflow_swallows_exit_8_and_re_raises_at_the_end(wf, step_id):
    """Without this the fix is half-applied: the script would report the alarm
    politely and the workflow would still skip the persistence steps."""
    text = (REPO / ".github" / "workflows" / wf).read_text(encoding="utf-8")
    assert '"$rc" -eq 8' in text, f"{wf} must special-case the systemic code"
    assert f"steps.{step_id}.outputs.systemic == 'true'" in text, \
        f"{wf} must re-raise the alarm in a later step"
    # The re-raise has to come after the persisting steps, or nothing changed.
    reraise = text.index("outputs.systemic == 'true'")
    for persists in ("Upload audit snapshot back to R2", "Refresh coverage spine in D1"):
        if persists in text:
            assert text.index(persists) < reraise, \
                f"{wf}: '{persists}' must run BEFORE the alarm is re-raised"


def test_a_real_crash_still_stops_the_workflow_immediately():
    """Exit 1 from a half-written sync must never reach the D1 push."""
    for wf in ("refresh-audit.yml", "acquire-audit.yml"):
        text = (REPO / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert 'elif [ "$rc" -ne 0 ]; then' in text and 'exit "$rc"' in text, \
            f"{wf} must still fail immediately on any non-alarm exit code"
