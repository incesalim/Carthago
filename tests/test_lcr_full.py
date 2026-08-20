"""The LCR graduation: assembling the numbered template from the document
layer.

What these pin: template-row identity from the printed row number (the
cross-bank join key), the current/prior instance split on a number restart,
the prior instance meaning prior YEAR-END, mint-time scaling with row 23 (the
percent row) exempt, the integer-guarded three-decimal repair that fixes
ALBRK's misparse without touching ENPARA's genuinely enormous LCR, the
row-number cell never leaking into value slots, and the signature test that
keeps the NSFR template and the monthly-averages mini table out.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "build_lcr_full", REPO / "scripts" / "build_lcr_full.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

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
                  (*KEY, pg, bid, 4, "risk", None, None, None, unit, 5,
                   len(grid), 0, "[]",
                   json.dumps(grid, ensure_ascii=False), "[]", "[]"))
    c.commit()
    return c


def _lcr_rows(top_label, tail_ratio, base=100.0):
    """A minimal numbered LCR table: rows 1, 2, 21, 22, 23."""
    return [
        (f"1 {top_label}", [1.0, None, None, base * 7.0, base * 3.0]),
        ("2 Gerçek Kişi Mevduat ve Perakende Mevduat",
         [2.0, base * 13.0, base * 5.0, base * 1.3, base * 0.5]),
        ("21 TOPLAM YKLV STOKU", [21.0, None, None, base * 7.0, base * 3.0]),
        ("22 TOPLAM NET NAKİT ÇIKIŞLARI",
         [22.0, None, None, base * 5.0, base * 1.5]),
        ("23 LİKİDİTE KARŞILAMA ORANI (%)",
         [23.0, None, None, tail_ratio[0], tail_ratio[1]]),
    ]


def test_two_instances_roles_scaling_and_percent_exemption(tmp_path):
    """A Milyon filing: current + prior tables split on the number restart;
    money scales ×1000, row 23 does not; the row-number cell never lands in a
    value slot."""
    db = _db(tmp_path, [
        (46, 1, "milyon", _lcr_rows("YÜKSEK KALİTELİ LİKİT VARLIKLAR (YKLV)",
                                    (140.0, 200.0))),
        (47, 1, "milyon", _lcr_rows("YÜKSEK KALİTELİ LİKİT VARLIKLAR (YKLV)",
                                    (151.64, 250.24), base=90.0)),
    ])
    got = L.assemble(db, KEY)
    assert set(got["instances"]) == {"current", "prior"}
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[1]["role"] == "hqla"
    assert cur[1]["w_total"] == 700_000.0          # 700 × 1000 (milyon → bin)
    assert cur[2]["uw_total"] == 1_300_000.0
    assert cur[2]["uw_fc"] == 500_000.0            # not the row number
    assert cur[23]["w_total"] == 140.0             # percent row: never scaled
    assert cur[23]["role"] == "lcr"
    pri = {x["template_row"]: x for x in got["instances"]["prior"]}
    assert pri[23]["w_total"] == 151.64
    assert cur[1]["label"].startswith("YÜKSEK")    # number prefix stripped


def test_integer_misparse_repaired_but_genuine_huge_lcr_kept(tmp_path):
    """ALBRK prints "186,610" (meaning 186.610%) and the capture read a bare
    integer; ENPARA's 34,221.52% is real and carries decimals. Only the
    integer form divides."""
    db = _db(tmp_path, [
        (46, 1, "bin", _lcr_rows("HIGH QUALITY LIQUID ASSETS",
                                 (186610.0, 34221.52))),
    ])
    cur = {x["template_row"]: x
           for x in L.assemble(db, KEY)["instances"]["current"]}
    assert cur[23]["w_total"] == 186.61            # misparse repaired
    assert cur[23]["w_fc"] == 34221.52             # genuine, untouched


def test_nsfr_and_monthly_tables_do_not_match(tmp_path):
    """The NSFR template is numbered too (to 34) but its rows 21-23 are not
    the LCR rows; the monthly-averages table has no numbered rows at all."""
    db = _db(tmp_path, [
        (50, 1, "bin", [
            ("1 ÖZKAYNAK UNSURLARI", [1.0, 100.0, "-", "-", 100.0]),
            ("21 İkinci kalite likit varlıklar dışında kalanlar",
             [21.0, 5.0, "-", "-", 5.0]),
            ("22 Diğer yükümlülükler", [22.0, 7.0, "-", "-", 7.0]),
            ("23 Karşılıklı yükümlülükler", [23.0, 9.0, "-", "-", 9.0]),
            ("34 NET İSTİKRARLI FONLAMA ORANI (%)",
             [34.0, None, None, None, 113.93]),
        ]),
        (48, 1, "bin", [
            ("OCAK", [143.13, None, 221.6]),
            ("ŞUBAT", [134.35, None, 206.31]),
        ]),
    ])
    assert L.assemble(db, KEY) is None


def test_prior_maps_to_year_end(tmp_path):
    """The template's Önceki Dönem re-prints December — the fx lane's
    documented BRSA convention — so Q2/Q3/Q4 all anchor (year-1)Q4."""
    assert L._prior_year_end("2026Q1") == "2025Q4"
    assert L._prior_year_end("2026Q3") == "2025Q4"


def test_a_lone_signature_row_is_not_a_table(tmp_path):
    """A cross-reference block quoting one LCR row must not detect."""
    db = _db(tmp_path, [
        (60, 1, "bin", [
            ("23 LİKİDİTE KARŞILAMA ORANI (%)", [23.0, None, None, 140.0, 200.0]),
        ]),
    ])
    assert L.assemble(db, KEY) is None
