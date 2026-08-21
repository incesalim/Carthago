"""The shared numbered-template machinery, and the leverage lane built on it.

What these pin beyond the LCR/NSFR suites (which now run through the same
module and pass unchanged): the wrap adoption — a numbered row with no values
takes the preceding unnumbered row's (GARAN's leverage row 1) — the per-
template percent-repair floor (leverage "9,127" is 9.127%, below the LCR's
10,000 floor), and the leverage template's own roles and identity.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import numbered_template as NT  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build_leverage_full", REPO / "scripts" / "build_leverage_full.py")
LV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LV)

KEY = ("TESTBK", "2026Q2", "consolidated")

DDL = """
CREATE TABLE bank_audit_document_tables (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, block_id INTEGER,
  section_no INTEGER, section_role TEXT, item_no INTEGER, item_title TEXT,
  heading TEXT, declared_unit TEXT, n_cols INTEGER, row_count INTEGER,
  cell_count INTEGER, col_labels_json TEXT, grid_json TEXT, notes_json TEXT,
  unplaced_json TEXT);
"""


def _db(tmp: Path, blocks) -> sqlite3.Connection:
    c = sqlite3.connect(tmp / "tables.db")
    c.executescript(DDL)
    for pg, bid, unit, rows in blocks:
        grid = [{"label": lab, "cells": cells} for lab, cells in rows]
        c.execute("INSERT INTO bank_audit_document_tables VALUES "
                  "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (*KEY, pg, bid, 4, "risk", None, None, None, unit, 3,
                   len(grid), 0, "[]",
                   json.dumps(grid, ensure_ascii=False), "[]", "[]"))
    c.commit()
    return c


def test_repair_floor_is_per_template():
    assert NT.repair_percent([186610.0, 34221.52]) == [186.61, 34221.52]
    assert NT.repair_percent([9127.0], floor=1000) == [9.127]
    assert NT.repair_percent([9127.0]) == [9127.0]        # LCR floor leaves it


def test_wrapped_first_row_adopts_the_values_printed_above(tmp_path):
    """GARAN prints "ON-BALANCE SHEET ITEMS (EXCLUDING…" with the values on an
    UNNUMBERED line and the number on the label's continuation below it."""
    db = _db(tmp_path, [
        (79, 1, "bin", [
            ("On-balance sheet items (excluding derivative financial instr",
             [None, 4669806356.0, 4376807111.0]),
            ("1 derivatives but including collateral)", [None, None, None]),
            ("2 (Assets deducted in determining Tier I capital)",
             [None, -8875106.0, -7817810.0]),
            ("13 Tier I Capital", [None, 442678378.0, 424256900.0]),
            ("14 Total risks (sum of lines 3, 6, 9 and 12)",
             [None, 8663744336.0, 7990914240.0]),
            ("15 Leverage ratio", [None, 5.11, 5.31]),
        ]),
    ])
    got = LV.assemble(db, KEY)
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[1]["amount"] == 4669806356.0               # adopted from above
    assert cur[1]["role"] == "on_balance_sheet_assets"
    assert cur[2]["amount"] == -8875106.0                  # signed deduction
    assert cur[15]["amount"] == 5.11 and cur[15]["amount_prior"] == 5.31
    # the identity the dry-run reports
    assert abs(cur[13]["amount"] / cur[14]["amount"] * 100
               - cur[15]["amount"]) < 0.05


def test_leverage_scales_money_not_the_ratio_and_repairs_its_floor(tmp_path):
    db = _db(tmp_path, [
        (52, 1, "milyon", [
            ("1 Bilanço içi varlıklar", [1.0, 3514.0, 3326.0]),
            ("13 Ana sermaye", [13.0, 341.0, 309.0]),
            ("14 Toplam risk tutarı (3, 6, 9 ve 12 nci satırların toplamı)",
             [14.0, 6187.0, 5663.0]),
            ("15 Kaldıraç oranı", [15.0, 9127.0, 5.46]),   # "9,127" misparse
        ]),
    ])
    cur = {x["template_row"]: x
           for x in LV.assemble(db, KEY)["instances"]["current"]}
    assert cur[1]["amount"] == 3_514_000.0                 # milyon -> bin
    assert cur[13]["role"] == "tier1_capital"
    assert cur[15]["amount"] == 9.127                       # repaired
    assert cur[15]["amount_prior"] == 5.46                  # untouched


def test_one_signature_row_is_not_a_table(tmp_path):
    db = _db(tmp_path, [(60, 1, "bin", [("15 Kaldıraç oranı", [15.0, 5.5, 5.4])])])
    assert LV.assemble(db, KEY) is None
