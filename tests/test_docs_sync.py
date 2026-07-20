"""The ops docs must stay in sync with the workflows and the Worker env.

Thin pytest wrapper around scripts/check_docs_sync.py so drift fails CI (the
python job already runs pytest) as well as a standalone run. Sibling of
tests/test_pipeline_graph_sync.py.
"""

from check_docs_sync import (
    check_env_keys,
    check_secrets,
    check_workflow_docs,
    check_workflows,
    env_keys,
    referenced_secrets,
    workflow_files,
)


def test_every_workflow_doc_names_every_workflow():
    """Not just OPERATIONS. Guarding one doc certifies that doc, not the docs:
    OPERATIONS stayed perfect while ARCHITECTURE quietly lost 8 of 18 workflows,
    4 of them scheduled lanes writing D1 on a cron."""
    gaps = check_workflow_docs()
    assert not gaps, "workflows missing from docs: " + "; ".join(
        f"{doc}: {', '.join(sorted(names))}" for doc, names in sorted(gaps.items())
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


def test_no_control_chars_in_source():
    """No stray control characters in the scripts we edit programmatically.

    A patch script wrote a literal 0x08 into check_briefing_facts.py where a
    regex word boundary was meant: `\b` survived the shell but not the Python
    string layer. grep and every editor rendered it as ordinary text, the regex
    silently never matched, and the fact it guarded read PASS on a briefing that
    should have failed. Cheap to assert, invisible otherwise.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    bad = []
    for path in list((root / "scripts").rglob("*.py")) + list((root / "src").rglob("*.py")):
        text = path.read_bytes()
        for ch in (b"\x08", b"\x0b", b"\x0c", b"\x00"):
            if ch in text:
                bad.append(f"{path.relative_to(root)}: contains {ch!r}")
    assert not bad, "control characters in source:\n" + "\n".join(bad)
