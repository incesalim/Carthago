#!/usr/bin/env python3
"""Guard: the ops docs stay in sync with the workflows and the Worker env.

Sibling of `check_pipeline_graph_sync.py`, applying the same idea to `docs/`.
That guard is why the /pipeline tab never falls behind the workflow files —
and its absence here is why `docs/OPERATIONS.md` silently drifted six
workflows and nine secrets behind the code (audited 2026-07-08).

Three invariants, all cheap to keep and expensive to rediscover:

  1. every `.github/workflows/*.yml` is named in docs/OPERATIONS.md
     (and every `*.yml` OPERATIONS names actually exists)
  2. every `secrets.X` / `vars.X` a workflow reads is named in docs/OPERATIONS.md
     — this is the one that catches a secret whose *repo* name differs from the
     env var it feeds (`KIMI_API_TOKEN` → `KIMI_API_KEY`), where a re-provision
     silently loses a lane
  3. every optional key in web/cloudflare-env.d.ts is named in OPERATIONS.md,
     ADMIN.md, or TELEGRAM_BOT.md

Deliberately NOT checked: CHANGELOG freshness (would fail every PR) and prose
accuracy (unlintable). This guards the inventories, not the narrative.

Run standalone (`python scripts/check_docs_sync.py`) — exits non-zero with a
diff on drift — or via `pytest` (tests/test_docs_sync.py). No third-party deps:
the CI python job installs only ruff/pytest/lxml/requests, so we regex the YAML
as text rather than importing PyYAML.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
OPERATIONS_DOC = REPO_ROOT / "docs" / "OPERATIONS.md"
ARCHITECTURE_DOC = REPO_ROOT / "docs" / "ARCHITECTURE.md"
PROJECT_STATE_DOC = REPO_ROOT / "docs" / "PROJECT_STATE.md"
ENV_DOCS = (
    OPERATIONS_DOC,
    REPO_ROOT / "docs" / "ADMIN.md",
    REPO_ROOT / "docs" / "TELEGRAM_BOT.md",
)
CF_ENV_FILE = REPO_ROOT / "web" / "cloudflare-env.d.ts"

# `${{ secrets.FOO }}` / `${{ vars.BAR }}` anywhere in a workflow.
_SECRET_RE = re.compile(r"\bsecrets\.([A-Z0-9_]+)")
_VARS_RE = re.compile(r"\bvars\.([A-Z0-9_]+)")
# A backticked workflow filename in the docs: `refresh-data.yml`.
_DOC_WORKFLOW_RE = re.compile(r"`([a-z0-9][a-z0-9._-]*\.ya?ml)`")
# `  FOO?: string;` — the optional (i.e. secret/var) keys of CloudflareEnv.
_ENV_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\?:", re.MULTILINE)

# Names that are legitimately absent from the docs. Justify every entry.
_ALLOW_SECRETS = frozenset(
    {
        # Injected by GitHub Actions itself; nothing to provision.
        "GITHUB_TOKEN",
    }
)
_ALLOW_ENV_KEYS = frozenset(
    {
        # Bindings declared in wrangler.jsonc, not secrets an operator sets.
        "DB",
        "ASSETS",
    }
)

# Docs that must name every workflow, and the workflows each may legitimately omit.
#
# For a long time only OPERATIONS.md was guarded — so it stayed perfect while
# ARCHITECTURE.md quietly lost track of 8 of 18 workflows (4 of them scheduled
# lanes writing D1 daily). A gate pointed at one file certifies that file, not
# the docs.
_WORKFLOW_DOCS: dict[Path, frozenset[str]] = {
    # The runbook and the inventory: no exceptions, every workflow appears.
    OPERATIONS_DOC: frozenset(),
    PROJECT_STATE_DOC: frozenset(),
    # ARCHITECTURE narrates the *scheduled* topology. The manual one-shot
    # backfills are genuinely out of that scope (they live in OPERATIONS +
    # PROJECT_STATE); everything that runs on a cron must be described here.
    ARCHITECTURE_DOC: frozenset(
        {
            "backfill-audit.yml",
            "backfill-faaliyet.yml",
            "backfill-nonbank.yml",
            "backfill-tefas.yml",
            # A scratch credential probe — writes nothing, reads no data source,
            # and is meant to be deleted. It is in OPERATIONS + PROJECT_STATE
            # (which inventory *everything*); the architecture has no node for it.
            "test-openrouter.yml",
        }
    ),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def workflow_files() -> set[str]:
    """Names of all workflow definitions on disk."""
    return {
        p.name
        for p in WORKFLOWS_DIR.iterdir()
        if p.suffix in (".yml", ".yaml") and p.is_file()
    }


def workflow_text() -> str:
    """Every workflow definition concatenated, for cheap name scanning."""
    return "\n".join(
        _read(WORKFLOWS_DIR / name) for name in sorted(workflow_files())
    )


def referenced_secrets() -> set[str]:
    """`secrets.X` / `vars.X` names read by any workflow."""
    text = workflow_text()
    names = set(_SECRET_RE.findall(text)) | set(_VARS_RE.findall(text))
    return names - _ALLOW_SECRETS


def env_keys() -> set[str]:
    """Optional keys of the CloudflareEnv interface (secrets + vars)."""
    return set(_ENV_KEY_RE.findall(_read(CF_ENV_FILE))) - _ALLOW_ENV_KEYS


def check_workflows() -> tuple[set[str], set[str]]:
    """Return (missing_from_docs, dangling_in_docs)."""
    on_disk = workflow_files()
    doc_text = _read(OPERATIONS_DOC)
    documented = {name for name in on_disk if name in doc_text}
    named_in_doc = set(_DOC_WORKFLOW_RE.findall(doc_text))
    return on_disk - documented, named_in_doc - on_disk


def check_workflow_docs() -> dict[str, set[str]]:
    """Workflows each doc in _WORKFLOW_DOCS fails to name, keyed by doc name.

    Forward direction only. The reverse ("dangling") check stays in
    check_workflows() for OPERATIONS alone, because _DOC_WORKFLOW_RE matches a
    backticked bare filename and ARCHITECTURE writes the full
    `.github/workflows/x.yml` path — applying it there would silently pass while
    catching nothing.
    """
    on_disk = workflow_files()
    gaps: dict[str, set[str]] = {}
    for doc, allowed in _WORKFLOW_DOCS.items():
        if not doc.exists():
            gaps[doc.name] = on_disk
            continue
        text = _read(doc)
        missing = {name for name in on_disk - allowed if name not in text}
        if missing:
            gaps[doc.name] = missing
    return gaps


def check_secrets() -> set[str]:
    """Secrets/vars a workflow reads but OPERATIONS.md never names."""
    doc_text = _read(OPERATIONS_DOC)
    return {name for name in referenced_secrets() if name not in doc_text}


def check_env_keys() -> set[str]:
    """CloudflareEnv keys no ops doc names."""
    docs = "\n".join(_read(p) for p in ENV_DOCS if p.exists())
    return {name for name in env_keys() if name not in docs}


def _report(title: str, names: set[str], hint: str) -> None:
    print(f"{title}\n  ({hint})", file=sys.stderr)
    for name in sorted(names):
        print(f"  - {name}", file=sys.stderr)


def main() -> int:
    for path in (OPERATIONS_DOC, CF_ENV_FILE):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1

    missing_wf, dangling_wf = check_workflows()
    doc_gaps = check_workflow_docs()
    missing_secrets = check_secrets()
    missing_env = check_env_keys()

    if not (missing_wf or dangling_wf or doc_gaps or missing_secrets or missing_env):
        print(
            f"docs in sync ({len(workflow_files())} workflows across "
            f"{len(_WORKFLOW_DOCS)} docs, {len(referenced_secrets())} secrets, "
            f"{len(env_keys())} env keys)."
        )
        return 0

    for doc_name, names in sorted(doc_gaps.items()):
        if doc_name == OPERATIONS_DOC.name and missing_wf:
            continue  # already reported below, with its own hint
        _report(
            f"Workflows missing from docs/{doc_name}:",
            names,
            "a lane nobody documents is a lane nobody knows is running",
        )

    if missing_wf:
        _report(
            "Workflows missing from docs/OPERATIONS.md:",
            missing_wf,
            "add a row to the Schedules table",
        )
    if dangling_wf:
        _report(
            "docs/OPERATIONS.md names workflow files that don't exist:",
            dangling_wf,
            "fix the name or restore the workflow",
        )
    if missing_secrets:
        _report(
            "Secrets/vars read by a workflow but missing from docs/OPERATIONS.md:",
            missing_secrets,
            "add a row to the Secrets table; an undocumented secret is lost on re-provision",
        )
    if missing_env:
        _report(
            "CloudflareEnv keys missing from OPERATIONS.md / ADMIN.md / TELEGRAM_BOT.md:",
            missing_env,
            "document the Worker secret or add it to _ALLOW_ENV_KEYS with a reason",
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
