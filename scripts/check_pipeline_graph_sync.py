#!/usr/bin/env python3
"""Guard: the /pipeline graph stays in sync with the GitHub Actions workflows.

`web/app/lib/pipeline-graph.ts` hand-authors the data-lineage topology shown on
the /pipeline tab; each ingestion node names its workflow via `workflowFile: "...".`
It's easy to add or rename a workflow and forget to update the graph, so this
check enforces the invariant bi-directionally:

  * every `.github/workflows/*.yml` is referenced by a `workflowFile:` in the graph
  * every `workflowFile:` in the graph points at a workflow file that exists

Run standalone (`python scripts/check_pipeline_graph_sync.py`) — exits non-zero
with a diff on drift — or via `pytest` (tests/test_pipeline_graph_sync.py). No
third-party deps: pure stdlib regex over both sides.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
GRAPH_FILE = REPO_ROOT / "web" / "app" / "lib" / "pipeline-graph.ts"

_REF_RE = re.compile(r'workflowFile:\s*["\']([^"\']+)["\']')


def workflow_files() -> set[str]:
    """Names of all workflow definitions on disk."""
    return {
        p.name
        for p in WORKFLOWS_DIR.iterdir()
        if p.suffix in (".yml", ".yaml") and p.is_file()
    }


def referenced_workflows() -> set[str]:
    """Workflow file names referenced by the pipeline graph."""
    return set(_REF_RE.findall(GRAPH_FILE.read_text(encoding="utf-8")))


def check() -> tuple[set[str], set[str]]:
    """Return (missing_from_graph, dangling_in_graph)."""
    on_disk = workflow_files()
    in_graph = referenced_workflows()
    return on_disk - in_graph, in_graph - on_disk


def main() -> int:
    if not GRAPH_FILE.exists():
        print(f"pipeline graph not found: {GRAPH_FILE}", file=sys.stderr)
        return 1
    missing, dangling = check()
    if not missing and not dangling:
        print(f"pipeline graph in sync ({len(workflow_files())} workflows).")
        return 0
    if missing:
        print(
            "Workflows missing from web/app/lib/pipeline-graph.ts "
            "(add a node with workflowFile: \"<name>\"):",
            file=sys.stderr,
        )
        for name in sorted(missing):
            print(f"  - {name}", file=sys.stderr)
    if dangling:
        print(
            "pipeline-graph.ts references workflow files that don't exist "
            "(fix the workflowFile or restore the workflow):",
            file=sys.stderr,
        )
        for name in sorted(dangling):
            print(f"  - {name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
