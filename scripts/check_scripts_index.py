#!/usr/bin/env python3
"""Guard: scripts/README.md stays a complete, truthful index of scripts/.

Sibling of `check_docs_sync.py` — same disease, same cure. The four-class
scheme (pipeline / operational / diagnostic / archived) was documented in
scripts/README.md and then silently drifted 47 files behind reality (audited
2026-08-16): every newer CI gate, the whole scratch_ family and three finished
one-shots had no row, and one indexed file (verify_stage_coverage.py) no
longer existed. In this repo an inventory holds exactly as long as a gate
diffs it against the world; this is that gate.

Two invariants:

  1. every ``*.py`` under scripts/ (recursively; ``__init__.py`` and
     ``__pycache__`` excluded) is mentioned by basename in scripts/README.md —
     archive/ files count too, their index being the prose paragraph at the
     bottom;
  2. every ``*.py`` basename the README mentions exists somewhere under
     scripts/ — a row whose file is gone describes a ghost.

Deliberately NOT checked: whether a description is accurate (unlintable), and
``.py`` names the README cites that live outside scripts/ (none today; add to
``_EXTERNAL`` if a legitimate one appears).

Run standalone (``python scripts/check_scripts_index.py``) — exits non-zero
with the diff — or in CI (`ci.yml`, step "Scripts index"). Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
README = SCRIPTS_DIR / "README.md"

# ``.py`` basenames the README may legitimately cite that do not live under
# scripts/ (e.g. a src/ module named for context). Justify every entry.
_EXTERNAL: frozenset[str] = frozenset({
    # OPERATIONS-style context in the test-openrouter row: the Kimi client the
    # A/B repoints, which lives in src/news/.
    "kimi.py",
    "free_llm.py",
    # The briefing fact checklist + citation gate the check_briefing_facts row
    # cites — shared generator/checker instruments, live in src/news/.
    "briefing_facts.py",
    "briefing_citations.py",
    # The shared sectioning module the build_document_tables and viewer rows
    # cite — lives in src/audit_reports/.
    "document_sections.py",
    # The shared numbered-template machinery the LCR/NSFR/leverage rows cite —
    # lives in src/audit_reports/.
    "numbered_template.py",
})

_PY_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*\.py)\b")


def main() -> int:
    text = README.read_text(encoding="utf-8")
    mentioned = set(_PY_NAME.findall(text)) - _EXTERNAL
    actual = {
        p.name
        for p in SCRIPTS_DIR.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    }

    missing_rows = sorted(actual - mentioned)
    ghosts = sorted(mentioned - actual)

    ok = True
    if missing_rows:
        ok = False
        print(f"scripts with no row in scripts/README.md ({len(missing_rows)}):")
        for name in missing_rows:
            print(f"  - {name}")
    if ghosts:
        ok = False
        print(f"scripts/README.md names scripts that do not exist ({len(ghosts)}):")
        for name in ghosts:
            print(f"  - {name}")
    if ok:
        print(f"scripts index in sync ({len(actual)} scripts, all indexed; no ghosts).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
