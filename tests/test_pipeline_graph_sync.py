"""The /pipeline graph must stay in sync with the GitHub Actions workflows.

Thin pytest wrapper around scripts/check_pipeline_graph_sync.py so drift fails
CI (the python job already runs pytest) as well as a standalone run.
"""

from check_pipeline_graph_sync import check, workflow_files


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
