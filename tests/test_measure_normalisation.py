"""The measurement must normalise before it compares, or it invents movers.

`classify_free_provision` reads what the PAGE prints. Since 2026Q2 that page is
Milyon TL, and `upsert_free_provision` multiplies by the filing's factor on the
way into the row. Diffing a raw read against a canonical `bin` row therefore
reports every non-overridden Q2 disclosure as a 1000x mover — i.e. as a
regression of the very fix being measured.

ENPARA 2026Q2 is the live example: the filing prints "2.500 TL", the row holds
2,500,000.

These run without R2 or a PDF: the normalisation is a pure function of the
classifier's result, the period and the filing's unit.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.audit_reports.free_provision import FreeProvision  # noqa: E402
from src.audit_reports.units import UnitContext  # noqa: E402


def _measure():
    spec = importlib.util.spec_from_file_location(
        "measure_fp", REPO / "scripts" / "measure_free_provision_change.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _scaled(res, period, unit_name, factor):
    """`_canonical` without the PDF: same scale_rows call, injected context."""
    M = _measure()
    row = UnitContext(unit_name, factor).scale_rows(
        "bank_audit_free_provision", M._FP_COLS,
        [("X", period, "unconsolidated", res.free_provision,
          res.free_provision_prior, res.source_page, res.snippet or "")])[0]
    return row[3], row[4]


def test_a_milyon_read_is_scaled_to_the_stored_canonical_value():
    """ENPARA 2026Q2: page says 2.500, the row holds 2,500,000."""
    res = FreeProvision(free_provision=2_500, disclosed=True, source_page=35)
    assert _scaled(res, "2026Q2", "milyon", 1_000) == (2_500_000, None)


def test_without_normalisation_enpara_would_read_as_a_1000x_mover():
    """States the bug the fix removes, so it cannot quietly come back."""
    raw = 2_500
    stored = 2_500_000
    assert raw != stored
    assert _scaled(FreeProvision(free_provision=raw, disclosed=True),
                   "2026Q2", "milyon", 1_000)[0] == stored


def test_a_bin_filing_is_left_alone():
    """Every pre-2026Q2 filing must compare exactly as before."""
    res = FreeProvision(free_provision=1_108_135, free_provision_prior=1_230_000,
                        disclosed=True, source_page=73)
    assert _scaled(res, "2026Q1", "bin", 1) == (1_108_135, 1_230_000)


def test_the_prior_is_scaled_too():
    """A prior read off the same Milyon page needs the same factor — TEB 2026Q2
    would otherwise store 368,000 against a prior of 1,230."""
    res = FreeProvision(free_provision=368, free_provision_prior=1_230,
                        disclosed=True)
    assert _scaled(res, "2026Q2", "milyon", 1_000) == (368_000, 1_230_000)


@pytest.mark.parametrize("value", [0, None])
def test_zero_and_null_survive_scaling_unchanged(value):
    """0 (the bank holds none) and null (we don't know) are different facts and
    neither may be invented or destroyed by a multiplication."""
    res = FreeProvision(free_provision=value, disclosed=True)
    assert _scaled(res, "2026Q2", "milyon", 1_000)[0] == value


def test_the_measurement_uses_the_same_columns_as_the_writer():
    """If MONEY_COLUMNS moves, the measurement must follow production rather
    than drift from it."""
    import inspect

    from src.audit_reports import free_provision as FP
    M = _measure()
    writer = inspect.getsource(FP.upsert_free_provision)
    for col in M._FP_COLS:
        assert f'"{col}"' in writer, f"{col} is not what the writer scales"


def test_the_corpus_size_is_stated_correctly():
    """The docstring said ~580 — that is the number of free-provision ROWS, not
    the number of PDFs the run pulls."""
    src = (REPO / "scripts" / "measure_free_provision_change.py").read_text(
        encoding="utf-8")
    assert "1,061" in src and "~580 PDFs" not in src
    wf = (REPO / ".github" / "workflows" / "measure-free-provision.yml").read_text(
        encoding="utf-8")
    assert "~580 PDFs" not in wf
