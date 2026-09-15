import pytest
from scripts.check_release import eligible

A, B = "a" * 40, "b" * 40


def run(sha=A, conclusion="success", status="completed", attempt=1):
    return dict(head_sha=sha, event="push", status=status, conclusion=conclusion,
                run_number=1, run_attempt=attempt)


def test_stale_successful_release_is_skipped():
    assert eligible(A, B, [run()])[0] is False
    assert eligible(B, B, [run(B)])[0] is True


@pytest.mark.parametrize("runs", [[], [run(B)], [run(conclusion="failure")],
                                   [run(), run(status="in_progress", attempt=2)]])
def test_missing_failed_or_rerunning_ci_cannot_release(runs):
    with pytest.raises(ValueError):
        eligible(A, A, runs)


def test_rollback_requires_previous_successful_release():
    with pytest.raises(ValueError):
        eligible(A, B, [run()], rollback=True)
    assert eligible(A, B, [run()], rollback=True,
                    releases=[dict(display_title=f"Release {A}", conclusion="success", verified=True)])[0]


def test_invalid_sha_is_rejected():
    with pytest.raises(ValueError):
        eligible("master", B, [run()])


def test_green_superseded_run_is_not_a_rollback_target():
    from scripts.check_release import verified_jobs
    skipped = {"conclusion": "success", "steps": [
        {"name": "Deploy the verified artifact", "conclusion": "skipped"},
        {"name": "Check deployed pages and APIs", "conclusion": "skipped"},
    ]}
    assert not verified_jobs([skipped])
    with pytest.raises(ValueError):
        eligible(A, B, [run()], rollback=True,
                 releases=[dict(display_title=f"Release {A}", conclusion="success", verified=False)])
    for step in skipped["steps"]:
        step["conclusion"] = "success"
    assert verified_jobs([skipped])
    skipped["steps"][1]["conclusion"] = "failure"
    assert not verified_jobs([skipped])
