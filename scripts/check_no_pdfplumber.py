#!/usr/bin/env python3
"""Guard: the PDF extractors are fitz (PyMuPDF) only — nothing re-introduces pdfplumber.

pdfplumber was removed from the whole codebase on 2026-07-15: fitz is ~60-85x
faster per page and `_fitz_page_text`'s coordinate reconstruction is a strict
superset of pdfplumber's layout-repair (rotation-aware, digit-merge; see
docs/AUDIT_EXTRACTION_GUIDE.md → "Engine"). Because pdfplumber is no longer in
requirements.txt, an `import pdfplumber` that slips back would fail at runtime
ONLY on whatever code path a test happens to exercise — silent everywhere else.
This gate moves that failure forward to PR time, and also blocks pdfplumber
creeping back into the dependency manifests.

Scope: every `.py` under src/, scripts/, tests/ (scripts/archive/ is frozen,
not-run historical code and is excluded), plus requirements.txt and this repo's
`.github/workflows/ci.yml` pip-install line. Pure stdlib. Exits non-zero on any
violation. Run standalone (`python scripts/check_no_pdfplumber.py`) or via
tests/test_no_pdfplumber.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories whose .py files must never import pdfplumber.
SCAN_DIRS = ("src", "scripts", "tests")
# Frozen, not-run historical scripts, superseded by the live fitz extractor.
# Excluded so we don't rewrite archived code (it isn't importable/runnable now
# that pdfplumber is uninstalled, which is fine — nothing calls it).
EXCLUDE_DIRS = (REPO_ROOT / "scripts" / "archive",)

# An ACTUAL import of the module (module- or function-level). Anchored to the
# line start so historical *mentions* of pdfplumber in comments/docstrings — of
# which the fitz code has many ("pdfplumber's column-flatten", etc.) — don't trip.
_IMPORT_RX = re.compile(r"^\s*(?:import\s+pdfplumber\b|from\s+pdfplumber\b)")

GUIDE = "docs/AUDIT_EXTRACTION_GUIDE.md"


def _is_excluded(path: Path) -> bool:
    return any(exc in path.parents for exc in EXCLUDE_DIRS)


def scan_python_imports(text: str) -> list[int]:
    """1-indexed line numbers on which `text` imports pdfplumber (empty if none)."""
    return [i for i, ln in enumerate(text.splitlines(), 1) if _IMPORT_RX.match(ln)]


def _py_violations() -> list[str]:
    out: list[str] = []
    for d in SCAN_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if _is_excluded(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            out += [f"{rel}:{ln}: imports pdfplumber" for ln in scan_python_imports(text)]
    return out


def _requirements_violations() -> list[str]:
    req = REPO_ROOT / "requirements.txt"
    if not req.exists():
        return []
    return [
        f"requirements.txt:{i}: pdfplumber is a declared dependency"
        for i, ln in enumerate(req.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"^\s*pdfplumber\b", ln)  # a dependency line, not a `#` comment
    ]


def _ci_violations() -> list[str]:
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not ci.exists():
        return []
    return [
        f".github/workflows/ci.yml:{i}: pip install includes pdfplumber"
        for i, ln in enumerate(ci.read_text(encoding="utf-8").splitlines(), 1)
        if not ln.lstrip().startswith("#")  # skip YAML comments (may name it on purpose)
        and "pip install" in ln and re.search(r"\bpdfplumber\b", ln)
    ]


def main() -> int:
    violations = _py_violations() + _requirements_violations() + _ci_violations()
    if violations:
        print("pdfplumber is BANNED - the PDF extractors are fitz (PyMuPDF) only.")
        print(f"See {GUIDE} (Engine). Read pages with `_fitz_page_text` / fitz "
              "`get_text`, never pdfplumber.\n")
        for v in violations:
            print(f"  {v}")
        print(f"\n{len(violations)} violation(s).")
        return 1
    print("no pdfplumber: PDF extraction is fitz-only across src/scripts/tests + manifests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
