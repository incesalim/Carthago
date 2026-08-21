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


# --- the RWA overview (OV1) lane, same module -------------------------------

_spec_rwa = importlib.util.spec_from_file_location(
    "build_rwa_full", REPO / "scripts" / "build_rwa_full.py")
RW = importlib.util.module_from_spec(_spec_rwa)
_spec_rwa.loader.exec_module(RW)


def test_rwa_overview_anchored_signatures_and_three_columns(tmp_path):
    """Signatures are matched on the label WITHOUT its number prefix, so the
    template may anchor at ^ ("1 KREDI RISKI" -> "KREDI RISKI"); the three
    printed columns land as rwa / rwa_prior / min_capital with GARAN's phantom
    column dropped; and minimum capital is 8% of RWA."""
    db = _db(tmp_path, [
        (82, 1, "bin", [
            ("1 Credit risk (excluding counterparty credit risk) (CCR)",
             [1.0, None, 3086068416.0, 2558296083.0, 246885473.0]),
            ("2 Of which standardised approach (SA)",
             [2.0, None, 3086068416.0, 2558296083.0, 246885473.0]),
            ("16 Market risk", [16.0, None, 82033338.0, 87751576.0, 6562667.0]),
            ("19 Operational risk",
             [19.0, None, 494412896.0, 337670689.0, 39553032.0]),
            ("25 Total (1+4+7+8+9+10+11+12+16+19+23+24)",
             [25.0, None, 3693979683.0, 3009107943.0, 295518374.0]),
        ]),
    ])
    got = RW.assemble(db, KEY)
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[1]["role"] == "credit_risk" and cur[25]["role"] == "total_rwa"
    assert cur[25]["rwa"] == 3693979683.0
    assert cur[25]["rwa_prior"] == 3009107943.0
    assert cur[25]["min_capital"] == 295518374.0
    assert abs(cur[25]["min_capital"] / cur[25]["rwa"] - 0.08) < 0.0015
    assert RW._close(423588045.0, 423588063.0)      # cross-table rounding
    assert not RW._close(10499959.0, 10498199.0)    # a real disagreement


# --- the CR4 exposure-class lane: percent COLUMN, shape filter, mint gate ----

_spec_cr4 = importlib.util.spec_from_file_location(
    "build_exposure_class_full", REPO / "scripts" / "build_exposure_class_full.py")
CR = importlib.util.module_from_spec(_spec_cr4)
_spec_cr4.loader.exec_module(CR)


def test_cr4_percent_column_shape_filter_and_mint_gate(tmp_path):
    """A Milyon CR4 block: five money columns scale, the density COLUMN does
    not; a 12-column CR5 block numbering the same rows is filtered by shape;
    and an instance whose total row fails the density identity is gated out
    at mint rather than stored."""
    cr4 = [
        ("1 Merkezi yönetimlerden alacaklar",
         [1.0, 1073.0, 152.0, 1075.0, 151.0, 1512.0, 0.14]),
        ("7 Kurumsal alacaklar", [7.0, 793.0, 540.0, 778.0, 238.0, 821.0, 80.7]),
        ("8 Perakende alacaklar", [8.0, 787.0, 1594.0, 783.0, 38.0, 616.0, 75.0]),
        ("18 TOPLAM", [18.0, 3132.0, 2274.0, 3116.0, 310.0, 1775.0, 51.81]),
    ]
    cr5 = [(lab, [cells[0]] + [1.0] * 12) for lab, cells in cr4]
    bad = [(lab, cells[:-1] + [999.0]) for lab, cells in cr4]   # density wrong
    db = _db(tmp_path, [(82, 1, "milyon", cr4), (83, 1, "milyon", cr5),
                        (84, 1, "milyon", bad)])
    got = CR.assemble(db, KEY)
    assert set(got["instances"]) == {"current", "prior"}   # cr5 filtered out
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[18]["rwa"] == 1_775_000.0                    # scaled
    assert cur[18]["rwa_density"] == 51.81                  # percent column: not
    assert cur[7]["role"] == "corporates"
    assert CR._identity_holds(got["instances"]["current"])
    assert not CR._identity_holds(got["instances"]["prior"])   # the 'bad' copy


# --- the loans-by-type notes family: label registry + identity gate ---------

_spec_lt = importlib.util.spec_from_file_location(
    "build_loan_type_full", REPO / "scripts" / "build_loan_type_full.py")
LT = importlib.util.module_from_spec(_spec_lt)
_spec_lt.loader.exec_module(LT)


def test_loan_type_registry_wrap_merge_and_identity_gate(tmp_path):
    """A Milyon instance: TR labels with the financial-sector row wrapped over
    two captured rows ("Mali Kesime" / "Verilen Krediler"), an EN-variant
    working-capital label, "Diğer (*)"; the identities hold and the rows
    scale. A second instance whose sub-types do not sum is gated out."""
    def rows(ns, wc, ex, fs, co, cc, ot, sp, orc, tot):
        return [
            ("İhtisas Dışı Krediler", [ns, 1.0, 2.0, "-"]),
            ("Corporation Loans", [wc, "-", "-", "-"]),
            ("İhracat Kredileri", [ex, "-", "-", "-"]),
            ("İthalat Kredileri", ["-", "-", "-", "-"]),
            ("Mali Kesime", [None, None, None, None]),           # wrapped head
            ("Verilen Krediler", [fs, "-", "-", "-"]),           # wrapped tail
            ("Tüketici Kredileri", [co, "-", "-", "-"]),
            ("Kredi Kartları", [cc, "-", "-", "-"]),
            ("Diğer (*)", [ot, "-", "-", "-"]),
            ("İhtisas Kredileri", [sp, "-", "-", "-"]),
            ("Diğer Alacaklar", [orc, "-", "-", "-"]),
            ("Toplam", [tot, 1.0, 2.0, "-"]),
        ]
    good = rows(100.0, 10.0, 20.0, 30.0, 15.0, 5.0, 20.0, 7.0, 3.0, 110.0)
    bad = rows(100.0, 10.0, 20.0, 30.0, 15.0, 5.0, 99.0, 7.0, 3.0, 110.0)
    db = _db(tmp_path, [(64, 2, "milyon", good), (64, 3, "milyon", bad)])
    got = LT.assemble(db, KEY)
    cur, pri = got["instances"]["current"], got["instances"]["prior"]
    assert LT._identities_hold(cur) and not LT._identities_hold(pri)
    by = {r["role"]: r for r in cur}
    assert by["financial_sector"]["standard"] == 30_000.0     # wrap merged, scaled
    assert by["working_capital"]["standard"] == 10_000.0      # EN variant
    assert by["other"]["standard"] == 20_000.0                # "Diğer (*)"
    assert by["non_specialised"]["watch_modified"] == 2_000.0
