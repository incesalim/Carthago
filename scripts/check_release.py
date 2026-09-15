"""Check exact-SHA release eligibility; fail closed before production writes."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def eligible(sha: str, master: str, ci_runs: list[dict],
             *, rollback: bool = False, releases: list[dict] | tuple = ()) -> tuple[bool, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("release SHA must be 40 lowercase hexadecimal characters")
    matching = [r for r in ci_runs if r.get("head_sha") == sha and r.get("event") == "push"]
    latest = max(matching, key=lambda r: (r.get("run_number", 0), r.get("run_attempt", 0)), default={})
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("the exact release SHA has no current successful push CI run")
    if rollback:
        if not any(r.get("display_title") == f"Release {sha}" and
                   r.get("conclusion") == "success" and r.get("verified") is True for r in releases):
            raise ValueError("rollback target has no successful verified release")
    elif sha != master:
        return False, "superseded by the current master commit"
    return True, "exact SHA passed CI" + ("; verified rollback target" if rollback else " and is current master")


def github(path: str) -> dict:
    result = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True, timeout=45)
    return json.loads(result.stdout)


def verified_jobs(jobs: list[dict]) -> bool:
    """A superseded no-op run is green too; require successful publication steps."""
    required = {"Deploy the verified artifact", "Check deployed pages and APIs"}
    return any(required <= {step.get("name") for step in job.get("steps", [])
                            if step.get("conclusion") == "success"}
               for job in jobs if job.get("conclusion") == "success")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise SystemExit("invalid release SHA")
    master = github(f"repos/{repo}/commits/master")["sha"]
    runs = github(f"repos/{repo}/actions/workflows/ci.yml/runs?head_sha={args.sha}&event=push&per_page=100")["workflow_runs"]
    releases = github(f"repos/{repo}/actions/workflows/deploy-cloudflare.yml/runs?status=success&per_page=100")["workflow_runs"] if args.rollback else []
    for release in releases:
        if release.get("display_title") == f"Release {args.sha}":
            release["verified"] = verified_jobs(github(
                f"repos/{repo}/actions/runs/{release['id']}/jobs?per_page=100")["jobs"])
    ok, reason = eligible(args.sha, master, runs, rollback=args.rollback, releases=releases)
    print(f"Release {args.sha}: {reason}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as f:
            f.write(f"eligible={str(ok).lower()}\n")
    elif not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
