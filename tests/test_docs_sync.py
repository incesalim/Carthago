"""The ops docs must stay in sync with the workflows and the Worker env.

Thin pytest wrapper around scripts/check_docs_sync.py so drift fails CI (the
python job already runs pytest) as well as a standalone run. Sibling of
tests/test_pipeline_graph_sync.py.
"""

from check_docs_sync import (
    check_env_keys,
    check_secrets,
    check_workflows,
    env_keys,
    referenced_secrets,
    workflow_files,
)


def test_operations_doc_lists_every_workflow():
    missing, dangling = check_workflows()
    assert not missing, (
        "workflows missing from docs/OPERATIONS.md: " + ", ".join(sorted(missing))
    )
    assert not dangling, (
        "docs/OPERATIONS.md names non-existent workflows: " + ", ".join(sorted(dangling))
    )


def test_every_workflow_secret_is_documented():
    missing = check_secrets()
    assert not missing, (
        "secrets/vars read by a workflow but undocumented in docs/OPERATIONS.md "
        "(an undocumented secret is lost on re-provision): " + ", ".join(sorted(missing))
    )


def test_every_worker_env_key_is_documented():
    missing = check_env_keys()
    assert not missing, (
        "CloudflareEnv keys undocumented in OPERATIONS.md / ADMIN.md / "
        "TELEGRAM_BOT.md: " + ", ".join(sorted(missing))
    )


def test_there_is_something_to_check():
    # Guard against the checks silently passing because a glob/regex found nothing.
    assert workflow_files(), "no workflow files discovered — check the path"
    assert referenced_secrets(), "no secrets discovered — check the regex"
    assert env_keys(), "no CloudflareEnv keys discovered — check the regex"
