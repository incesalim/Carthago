"""The fitz-only guard (scripts/check_no_pdfplumber.py) detects re-introductions
of pdfplumber, ignores historical mentions, and passes on the current tree.

Pure stdlib; runs in CI's minimal-deps job. `scripts/` is on sys.path via
pyproject `[tool.pytest.ini_options].pythonpath`.
"""
from __future__ import annotations

import check_no_pdfplumber as guard


def test_flags_real_imports():
    # module-level, function-level (indented, with a trailing comment), and from-import
    assert guard.scan_python_imports("import pdfplumber\n") == [1]
    assert guard.scan_python_imports("    import pdfplumber  # noqa\n") == [1]
    assert guard.scan_python_imports("from pdfplumber import open\n") == [1]
    assert guard.scan_python_imports("x = 1\nimport pdfplumber\n") == [2]


def test_ignores_historical_mentions():
    # The fitz code is full of comments/docstrings naming pdfplumber; none is an import.
    assert guard.scan_python_imports("# import pdfplumber one day\n") == []
    assert guard.scan_python_imports("y = 2  # pdfplumber was removed 2026-07-15\n") == []
    assert guard.scan_python_imports('"""pdfplumber column-flatten dropped labels."""\n') == []
    assert guard.scan_python_imports("s = 'import pdfplumber'  # a string, not code\n") == []


def test_current_tree_is_clean():
    # No import in src/scripts/tests (bar frozen scripts/archive), and pdfplumber is
    # absent from requirements.txt and ci.yml. Guard returns 0.
    assert guard.main() == 0
