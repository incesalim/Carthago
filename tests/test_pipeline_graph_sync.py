"""The /pipeline graph must stay in sync with the GitHub Actions workflows.

Thin pytest wrapper around scripts/check_pipeline_graph_sync.py so drift fails
CI (the python job already runs pytest) as well as a standalone run.
"""

from check_pipeline_graph_sync import check, dead_hrefs, routes, workflow_files


def test_every_graph_href_resolves_to_a_real_route():
    """/pipeline shipped two links that 404'd: /weekly (route retired) and
    /franchise (parked under web/app/_franchise/, which Next does not serve).
    Nav and sitemap were updated both times; this hand-authored graph was not."""
    dead = dead_hrefs()
    assert not dead, (
        "pipeline-graph.ts links to routes that don't exist: " + ", ".join(sorted(dead))
    )


def test_route_discovery_understands_the_app_router():
    live = routes()
    assert {"/", "/banks", "/market-risk", "/economy/inflation"} <= live
    # The underscore prefix is what un-routes a page — the /franchise 404 in one line.
    assert "/franchise" not in live
    assert "/valuation" not in live


def test_pipeline_graph_lists_every_workflow():
    missing, dangling = check()
    assert not missing, (
        "workflows missing from web/app/lib/pipeline-graph.ts: " + ", ".join(sorted(missing))
    )
    assert not dangling, (
        "pipeline-graph.ts references non-existent workflows: " + ", ".join(sorted(dangling))
    )


def test_there_are_workflows_to_check():
    # Guard against the check silently passing because globbing found nothing.
    assert workflow_files(), "no workflow files discovered — check the path"
