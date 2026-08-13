"""Reconciling stored figures against the cells a filing printed.

The scenario that matters is TEB 2026Q2: a filing that declares Milyon and is
ingested at factor 1 stores figures matching the printed page exactly, so every
internal identity foots and every cell reads `ok`. Only an external anchor sees
it, which is what these tests pin.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "check_capture_reconcile", REPO / "scripts" / "check_capture_reconcile.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

KEY = ("TESTBK", "2026Q2", "consolidated")
BIN_DECL = "(Para birimi: Bin Türk Lirası olarak ifade edilmiştir.)"
MILYON_DECL = "(Para birimi: Milyon Türk Lirası olarak ifade edilmiştir.)"

CAPTURE_DDL = """
CREATE TABLE bank_audit_document_pages (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER,
  text_layer TEXT NOT NULL DEFAULT 'text');
CREATE TABLE bank_audit_document_lines (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER,
  line_order INTEGER, text TEXT);
CREATE TABLE bank_audit_document_cells (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, line_order INTEGER,
  cell_index INTEGER, col_index INTEGER, x0 REAL, x1 REAL, text TEXT,
  is_numeric INTEGER, value REAL);
"""
AUDIT_DDL = """
CREATE TABLE bank_audit_balance_sheet (
  bank_ticker TEXT, period TEXT, kind TEXT, statement TEXT, item_order INTEGER,
  hierarchy TEXT, item_name TEXT, footnote TEXT,
  amount_tl REAL, amount_fc REAL, amount_total REAL);
"""

# A scale finding needs SCALE_MIN_HITS (20) figures behind it, so a couple of
# coincidental round numbers cannot raise one. The fixture is sized past that
# rather than the production threshold being lowered to meet it.
AS_PRINTED = [(1_500_000.0 + i, 2_500_000.0 + i, 4_000_000.0 + 2 * i)
              for i in range(10)]
PRINTED = [v for row in AS_PRINTED for v in row]


def _capture(tmp: Path, declaration: str, printed=PRINTED, vector_pages=0) -> Path:
    p = tmp / "cap.db"
    c = sqlite3.connect(p)
    c.executescript(CAPTURE_DDL)
    c.execute("INSERT INTO bank_audit_document_pages VALUES (?,?,?,1,'text')", KEY)
    for i in range(vector_pages):
        c.execute("INSERT INTO bank_audit_document_pages VALUES (?,?,?,?,'vector')",
                  (*KEY, 2 + i))
    c.execute("INSERT INTO bank_audit_document_lines VALUES (?,?,?,1,1,?)",
              (*KEY, declaration))
    for i, v in enumerate(printed):
        c.execute("INSERT INTO bank_audit_document_cells "
                  "VALUES (?,?,?,1,?,0,0,0,0,?,1,?)", (*KEY, 10 + i, str(v), v))
    c.commit()
    return p


def _audit(tmp: Path, rows) -> Path:
    p = tmp / "aud.db"
    c = sqlite3.connect(p)
    c.executescript(AUDIT_DDL)
    for i, (tl, fc, tot) in enumerate(rows):
        c.execute("INSERT INTO bank_audit_balance_sheet VALUES "
                  "(?,?,?,'assets',?,'I.','x',NULL,?,?,?)", (*KEY, i, tl, fc, tot))
    c.commit()
    return p


def _run(cap: Path, aud: Path) -> dict:
    capc = sqlite3.connect(cap)
    audc = sqlite3.connect(aud)
    r = R.reconcile_one(capc, audc, KEY, R._tables(audc))
    r["findings"] = R.findings_for(r)
    return r


SCALED_X1000 = [tuple(v * 1000 for v in row) for row in AS_PRINTED]


def test_a_thousands_filing_stored_as_printed_reconciles(tmp_path):
    r = _run(_capture(tmp_path, BIN_DECL), _audit(tmp_path, AS_PRINTED))
    assert r["unit"] == "bin"
    assert r["expected_factor"] == 1
    assert r["rate"] == 1.0
    assert r["findings"] == []


def test_a_millions_filing_scaled_to_canonical_reconciles(tmp_path):
    """The healthy millions case: stored is printed x1000, and that is CORRECT.

    An earlier draft of this check read that as the error and would have failed
    every properly ingested Milyon filing.
    """
    r = _run(_capture(tmp_path, MILYON_DECL), _audit(tmp_path, SCALED_X1000))
    assert r["unit"] == "milyon"
    assert r["expected_factor"] == 1000
    assert r["rate"] == 1.0
    assert r["findings"] == []


def test_the_teb_failure_is_caught(tmp_path):
    """Declares Milyon, ingested at factor 1 — 1000x small, every identity foots."""
    r = _run(_capture(tmp_path, MILYON_DECL), _audit(tmp_path, AS_PRINTED))
    codes = [f["code"] for f in r["findings"]]
    assert codes == ["unit_scale"]
    assert r["findings"][0]["severity"] == "error"
    assert "1000× small" in r["findings"][0]["detail"]
    assert r["best_factor"] == 1 and r["expected_factor"] == 1000


def test_the_opposite_over_scaling_is_caught_too(tmp_path):
    r = _run(_capture(tmp_path, BIN_DECL), _audit(tmp_path, SCALED_X1000))
    assert [f["code"] for f in r["findings"]] == ["unit_scale"]
    assert "1000× large" in r["findings"][0]["detail"]


def test_a_drawn_page_is_reported_as_a_capture_gap_not_a_data_defect(tmp_path):
    """FIBA's statement pages are vector outlines, so its rows were never
    captured. Blaming the extractor for that would be blaming it for a hole in
    the evidence."""
    cap = _capture(tmp_path, BIN_DECL, printed=[1_500_000.0], vector_pages=3)
    r = _run(cap, _audit(tmp_path, AS_PRINTED))
    assert [f["code"] for f in r["findings"]] == ["capture_incomplete"]
    assert r["findings"][0]["severity"] == "info"


def test_figures_absent_from_the_filing_are_an_error(tmp_path):
    cap = _capture(tmp_path, BIN_DECL, printed=[9_999_999.0])
    r = _run(cap, _audit(tmp_path, AS_PRINTED))
    assert [f["code"] for f in r["findings"]] == ["figures_absent"]
    assert r["findings"][0]["severity"] == "error"


def test_zero_and_null_are_not_figures_to_look_for(tmp_path):
    """`null` is not `0`, and a disclosed zero prints as "-" rather than as a
    cell — neither is evidence, so neither may count against the rate."""
    rows = AS_PRINTED + [(0.0, None, 0.0)]
    r = _run(_capture(tmp_path, BIN_DECL), _audit(tmp_path, rows))
    assert r["stored"] == len(PRINTED)   # the zero row contributes nothing
    assert r["rate"] == 1.0
    assert r["findings"] == []


def test_an_unreadable_declaration_withholds_the_scale_verdict(tmp_path):
    r = _run(_capture(tmp_path, "no unit stated here"), _audit(tmp_path, AS_PRINTED))
    assert r["expected_factor"] is None
    assert [f["code"] for f in r["findings"]] == ["unit_unknown"]
    assert all(f["severity"] == "info" for f in r["findings"])


def test_sign_is_ignored_because_deductions_print_unsigned(tmp_path):
    """BRSA prints deduction rows as "(-)" labels while the extractor stores
    them signed; comparing signs would fail rows that are perfectly correct."""
    rows = [(-1_500_000.0, 2_500_000.0, 4_000_000.0), AS_PRINTED[1]]
    r = _run(_capture(tmp_path, BIN_DECL), _audit(tmp_path, rows))
    assert r["rate"] == 1.0


@pytest.mark.parametrize("factor,label", [(1000, "milyon"), (1_000_000, "milyar")])
def test_every_declarable_unit_has_a_scale(factor, label):
    from src.audit_reports import units as U
    assert U.UNIT_SCALE[label] == factor
    assert factor in R.FACTORS
