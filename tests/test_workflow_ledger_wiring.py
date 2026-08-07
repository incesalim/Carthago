"""D1_RUN_LEDGER is load-bearing, so its wiring is gated like any invariant.

The 250,000 emergency cap only bounds a RUN if every push in that run reads and
writes the same ledger file. Miss it on one step and the cap silently reverts to
per-invocation — which is the bug it was added to fix, restored without a test
failing anywhere.

`check_docs_sync.py` does not cover this: it checks workflows, `secrets.*` and
Worker bindings, and the ledger is none of those. That is the gap, not a reason
to skip it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
LEDGER = "D1_RUN_LEDGER"

# A step that reaches D1 through push_to_d1 — directly, or through a script that
# shells out to it. sync_audit_expected.py runs push_to_d1 as a subprocess and
# inherits the environment, so the ledger has to be on ITS step too.
_PUSHES_TO_D1 = re.compile(
    r"push_to_d1\.py|sync_audit_expected\.py[^\n]*--push|audit_d1\.py")


def _steps(path: Path):
    if yaml is None:
        pytest.skip("pyyaml not installed")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job in (doc.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            yield step


def _pushing_steps(path: Path):
    return [s for s in _steps(path)
            if _PUSHES_TO_D1.search(str(s.get("run") or ""))]


def test_refresh_audit_batches_everything_into_one_budgeted_push():
    """The old two-push run bypassed the per-run intent of the cap."""
    wf = WORKFLOWS / "refresh-audit.yml"
    steps = _pushing_steps(wf)
    assert len(steps) == 1, [s.get("name") for s in steps]
    assert LEDGER in (steps[0].get("env") or {})


def test_the_ledger_path_is_run_scoped_not_shared_between_runs():
    """A path outside the runner's temp would carry spend across runs on a
    self-hosted runner and refuse a legitimate push tomorrow."""
    wf = WORKFLOWS / "refresh-audit.yml"
    for s in _pushing_steps(wf):
        value = (s.get("env") or {})[LEDGER]
        assert "runner.temp" in value or "RUNNER_TEMP" in value, (
            f"step {s.get('name')!r} ledger {value!r} is not run-scoped")


def test_every_workflow_that_pushes_more_than_once_carries_a_ledger():
    """Guards the guard: a NEW workflow with two pushes has the same problem,
    and nothing else in CI would notice."""
    offenders = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        steps = _pushing_steps(wf)
        if len(steps) < 2:
            continue
        missing = [s.get("name") for s in steps
                   if LEDGER not in (s.get("env") or {})]
        if missing:
            offenders.append((wf.name, missing))
    assert not offenders, (
        "these workflows push to D1 more than once without a shared run "
        f"ledger, so the cap bounds each push and not the run: {offenders}")


def test_the_reader_and_the_workflow_agree_on_the_variable_name():
    """A rename on one side only would disable the ledger silently."""
    src = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    assert f'RUN_LEDGER_ENV = "{LEDGER}"' in src
    assert LEDGER in (REPO / "scripts" / "audit_d1.py").read_text(encoding="utf-8"), \
        "audit_d1 decides retryability from the ledger; it must read the same name"
