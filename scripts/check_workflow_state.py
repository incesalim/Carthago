#!/usr/bin/env python3
"""Guard: a workflow's enabled/disabled state must be written down.

THE HOLE THIS CLOSES

`gh workflow disable <file>` leaves **no trace in git**. The state lives in
GitHub, so nothing in the repository can see it. On 2026-08-01 ten scheduled
workflows were disabled — including `healthcheck.yml`, the only monitor — and
every gate in this repo still reported green while the `schedule:` blocks in
those YAML files were fiction. `check_docs_sync.py` verified the workflows were
*documented*; nothing verified they were *running*.

That is the same class of defect as a stated rule with no gate, and it is worse
than a plain outage: an outage is loud, and this was silent by construction.

WHAT IT CHECKS

  1. Every workflow file on disk appears in `data/workflow_state.json`.
  2. Every entry in that file still corresponds to a real workflow.
  3. The live state from the GitHub API matches the recorded state — so a
     freeze (or a thaw) has to be committed to pass CI.
  4. A disabled workflow carries a `reason`. "Off" without a reason is how a
     temporary freeze becomes permanent by forgetting.
  5. If an entry sets `review_by` (YYYY-MM-DD) and that date has passed, the
     check fails. Nothing else enforces a re-enable date — the 2026-08-11 date
     in OPERATIONS.md was prose, and prose does not fire.

It also PRINTS the frozen set on every run, so the state is visible in the log
of every CI job rather than only when someone goes looking.

WHERE IT RUNS

CI, where `GITHUB_TOKEN` is present. Locally it needs an authenticated `gh`; if
there isn't one it SKIPS with a notice — but in CI (`GITHUB_ACTIONS=true`) an
unavailable API is a FAILURE, not a skip. A gate that quietly no-ops in CI is
decoration, which is the anti-pattern this repo already learned once when 86
extractor tests silently skipped for want of a dependency.

    python scripts/check_workflow_state.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "data" / "workflow_state.json"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Managed by GitHub, not by us — it has no file in .github/workflows.
IGNORE = {"dependabot-updates"}


def live_state() -> dict[str, str] | None:
    """{file: state} from the API, or None when `gh` cannot answer."""
    try:
        proc = subprocess.run(
            ["gh", "workflow", "list", "--all", "--json", "state,path"],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return {r["path"].split("/")[-1]: r["state"] for r in rows}


def main() -> int:
    if not REGISTRY.exists():
        print(f"check_workflow_state: missing {REGISTRY.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["workflows"]
    on_disk = {p.name for p in WORKFLOW_DIR.glob("*.yml")} | {p.name for p in WORKFLOW_DIR.glob("*.yaml")}
    problems: list[str] = []

    # 1 + 2 — the registry and the directory must describe the same set.
    for f in sorted(on_disk - set(registry)):
        problems.append(
            f"{f} exists but is not in data/workflow_state.json — add it with its state "
            f"(and a `reason` if it is disabled)"
        )
    for f in sorted(set(registry) - on_disk - IGNORE):
        problems.append(f"data/workflow_state.json lists {f}, which no longer exists — remove it")

    # 4 + 5 — a disabled entry must justify itself, and honour its own deadline.
    today = dt.date.today()
    for f, entry in sorted(registry.items()):
        if entry.get("state") == "active":
            continue
        if not entry.get("reason"):
            problems.append(f"{f} is recorded as {entry.get('state')} with no `reason`")
        by = entry.get("review_by")
        if by:
            try:
                due = dt.date.fromisoformat(by)
            except ValueError:
                problems.append(f"{f}: review_by '{by}' is not a YYYY-MM-DD date")
                continue
            if today > due:
                problems.append(
                    f"{f} was due for review on {by} and is still {entry.get('state')} — "
                    f"re-enable it, or move the date deliberately"
                )

    # 3 — the recorded state must match reality.
    live = live_state()
    if live is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("check_workflow_state FAILED: the GitHub API is unreachable in CI, so the "
                  "recorded state cannot be verified. This check must not pass blind.",
                  file=sys.stderr)
            return 1
        print("check_workflow_state: no authenticated `gh` — SKIPPING the live comparison.\n"
              "  (Structure checks below still ran. CI verifies the live state.)")
    else:
        for f, entry in sorted(registry.items()):
            if f in IGNORE:
                continue
            actual = live.get(f)
            if actual is None:
                problems.append(f"{f} is in the registry but the API does not know it")
            elif actual != entry.get("state"):
                problems.append(
                    f"{f}: recorded {entry.get('state')!r} but GitHub says {actual!r} — "
                    f"someone changed it without committing the change"
                )
        for f in sorted(set(live) - set(registry) - IGNORE):
            problems.append(f"{f} is live on GitHub but absent from the registry")

    frozen = {f: e for f, e in sorted(registry.items()) if e.get("state") != "active"}
    if frozen:
        print(f"\n[!] {len(frozen)} workflow(s) deliberately NOT running:")
        for f, e in frozen.items():
            since = e.get("frozen_since", "?")
            by = e.get("review_by")
            print(f"   - {f}  (since {since}{', review by ' + by if by else ', no review date'})")

    if problems:
        print("\ncheck_workflow_state FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"\nworkflow state in sync ({len(registry)} workflows, {len(frozen)} frozen and recorded).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
