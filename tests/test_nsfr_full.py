"""The NSFR graduation: the numbered 1-34 template from the document layer.

What these pin: the per-block column model (row-number column detected by
majority, phantom all-None columns dropped, the weighted total ALWAYS the
rightmost column — the rule that fixed AKBNK's ratio landing in a bucket
slot), row 14 carrying the asf_total role without any "total" word in its
label, the signature test that keeps an LCR-shaped block out, the
current/prior instance split, and the percent row's scaling exemption with
the integer-guarded three-decimal repair.
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
    "build_nsfr_full", REPO / "scripts" / "build_nsfr_full.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)

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
                  (*KEY, pg, bid, 6, "risk", None, None, None, unit, 6,
                   len(grid), 0, "[]",
                   json.dumps(grid, ensure_ascii=False), "[]", "[]"))
    c.commit()
    return c


def _nsfr_rows(ratio, base=100.0):
    """Rows 1, 4, 14, 33, 34 in GARAN's captured 7-column shape: a rowno
    column, four live buckets, a mid-table phantom (always-None) column, and
    the weighted total rightmost."""
    return [
        ("1 ÖZKAYNAK UNSURLARI",
         [1.0, base * 6.0, "-", None, "-", "-", base * 6.0]),
        ("4 GERÇEK KİŞİ VE PERAKENDE MÜŞTERİ MEVDUATI",
         [4.0, base * 10.0, base * 9.0, None, base * 5.0, base * 2.0,
          base * 17.0]),
        ("14 Available stable funding",
         [14.0, None, None, None, None, None, base * 23.0]),
        ("33 GEREKLİ İSTİKRARLI FON",
         [33.0, None, None, None, None, None, base * 20.0]),
        ("34 NET İSTİKRARLI FONLAMA ORANI (%)",
         [34.0, None, None, None, None, None, ratio]),
    ]


def test_columns_roles_scaling_and_instances(tmp_path):
    """Milyon filing, phantom column, rowno column: buckets land in order,
    the total is the rightmost column, row 34 never scales, row 14 carries
    asf_total with no 'total' in its label, and the second printing becomes
    the prior instance."""
    db = _db(tmp_path, [
        (50, 1, "milyon", _nsfr_rows(115.0)),
        (51, 1, "milyon", _nsfr_rows(111.6, base=90.0)),
    ])
    got = N.assemble(db, KEY)
    assert set(got["instances"]) == {"current", "prior"}
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[1]["role"] == "capital_items"
    assert cur[1]["weighted_total"] == 600_000.0       # milyon -> bin
    assert cur[4]["no_maturity"] == 1_000_000.0        # not the rowno
    assert cur[4]["maturity_lt_6m"] == 900_000.0       # phantom col dropped
    assert cur[4]["maturity_6m_1y"] == 500_000.0
    assert cur[4]["maturity_gte_1y"] == 200_000.0
    assert cur[14]["role"] == "asf_total"
    assert cur[34]["weighted_total"] == 115.0          # percent: never scaled
    pri = {x["template_row"]: x for x in got["instances"]["prior"]}
    assert pri[34]["weighted_total"] == 111.6
    # the identity the dry-run reports: asf/rsf*100 == row34
    assert abs(cur[14]["weighted_total"] / cur[33]["weighted_total"] * 100
               - cur[34]["weighted_total"]) < 0.5


def test_integer_misparse_repaired_on_the_ratio_row(tmp_path):
    db = _db(tmp_path, [(50, 1, "bin", _nsfr_rows(139890.0))])
    cur = {x["template_row"]: x
           for x in N.assemble(db, KEY)["instances"]["current"]}
    assert cur[34]["weighted_total"] == 139.89         # "139,890" misparse
    # money rows are untouched by the repair — only the percent row divides
    assert cur[14]["weighted_total"] == 2300.0


def test_lcr_shaped_block_does_not_match(tmp_path):
    """The LCR template is numbered too; its rows 1/33/34 never carry the
    NSFR signatures (row 33/34 do not exist in it at all)."""
    db = _db(tmp_path, [
        (46, 1, "bin", [
            ("1 YÜKSEK KALİTELİ LİKİT VARLIKLAR",
             [1.0, None, None, 700.0, 300.0]),
            ("21 TOPLAM YKLV STOKU", [21.0, None, None, 700.0, 300.0]),
            ("23 LİKİDİTE KARŞILAMA ORANI (%)",
             [23.0, None, None, 140.0, 200.0]),
        ]),
    ])
    assert N.assemble(db, KEY) is None


def test_a_lone_signature_row_is_not_a_table(tmp_path):
    db = _db(tmp_path, [
        (60, 1, "bin", [
            ("34 NET İSTİKRARLI FONLAMA ORANI (%)",
             [34.0, None, None, None, None, 113.9]),
        ]),
    ])
    assert N.assemble(db, KEY) is None
