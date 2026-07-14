#!/usr/bin/env python3
"""Guard: the /pipeline graph stays in sync with the GitHub Actions workflows.

`web/app/lib/pipeline-graph.ts` hand-authors the data-lineage topology shown on
the /pipeline tab; each ingestion node names its workflow via `workflowFile: "...".`
It's easy to add or rename a workflow and forget to update the graph, so this
check enforces the invariant bi-directionally:

  * every `.github/workflows/*.yml` is referenced by a `workflowFile:` in the graph
  * every `workflowFile:` in the graph points at a workflow file that exists

It also checks the OTHER end of the topology — that every page node's `href:`
resolves to a route the app actually serves. Retiring a route (/weekly) or
parking one under an underscore dir (/franchise) updates the nav and the sitemap
but not this hand-authored graph, so /pipeline shipped two links that 404'd.

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
WEB_APP_DIR = REPO_ROOT / "web" / "app"

_REF_RE = re.compile(r'workflowFile:\s*["\']([^"\']+)["\']')
_HREF_RE = re.compile(r'href:\s*["\']([^"\']+)["\']')


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


def routes() -> set[str]:
    """The static routes the Next App Router actually serves.

    web/app/page.tsx -> "/", web/app/a/b/page.tsx -> "/a/b". Two segment kinds
    never yield a static route:

      * "_foo" — a private folder. Next does NOT route it. This is exactly how
        /franchise and /valuation were parked, and why linking to them 404s.
      * "[param]" — dynamic, so there is no static path to compare an href to.
        (No page node links to one: the bank-detail node correctly points at the
        static /banks.)

    A "(group)" segment is organisational and contributes no path segment.
    """
    found: set[str] = set()
    for page in WEB_APP_DIR.rglob("page.tsx"):
        segments = page.relative_to(WEB_APP_DIR).parts[:-1]
        if any(s.startswith(("_", "[")) for s in segments):
            continue
        segments = tuple(s for s in segments if not (s.startswith("(") and s.endswith(")")))
        found.add("/" + "/".join(segments) if segments else "/")
    return found


def dead_hrefs() -> set[str]:
    """Graph hrefs that resolve to no route — i.e. a dead link on /pipeline.

    Forward direction only. The reverse (every route has a node) is deliberately
    NOT asserted: /sector, /market-risk and /disclosures have lived as routes
    without a lineage node, and that is a legitimate authoring choice.
    """
    live = routes()
    hrefs = set(_HREF_RE.findall(GRAPH_FILE.read_text(encoding="utf-8")))
    return {h for h in hrefs if h.split("?")[0].split("#")[0] not in live}


def main() -> int:
    if not GRAPH_FILE.exists():
        print(f"pipeline graph not found: {GRAPH_FILE}", file=sys.stderr)
        return 1
    missing, dangling = check()
    dead = dead_hrefs()
    if not missing and not dangling and not dead:
        print(
            f"pipeline graph in sync ({len(workflow_files())} workflows, "
            f"{len(routes())} routes)."
        )
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
    if dead:
        print(
            "pipeline-graph.ts page nodes link to routes that don't exist "
            "(the route was retired, or parked under an _underscore dir). Drop "
            "the href key to render the node as a non-clickable card, or delete "
            "the node:",
            file=sys.stderr,
        )
        for href in sorted(dead):
            print(f"  - {href}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
