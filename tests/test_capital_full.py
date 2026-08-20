"""The capital pilot: assembling the full own-funds table from the document
layer.

What these pin: both seed dialects (the tasfiyesi opener and the bare-header
form, with the min-rows guard that keeps 4-row summary snippets out), the
page-gap chain stop that excludes the look-alike reconciliation table, the
second-template truncation, role mapping in both languages including the
ILAVE/ANA and roman/digit TIER traps, mint-time unit scaling with the ratio
exemption, and "-" staying NULL.
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
    "build_capital_full", REPO / "scripts" / "build_capital_full.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

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
    """blocks: [(page, block_id, unit, [(label, cells), ...])]"""
    c = sqlite3.connect(tmp / "tables.db")
    c.executescript(DDL)
    for pg, bid, unit, rows in blocks:
        grid = [{"label": lab, "cells": cells} for lab, cells in rows]
        n_cols = max((len(r["cells"]) for r in grid), default=0)
        c.execute("INSERT INTO bank_audit_document_tables VALUES "
                  "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (*KEY, pg, bid, 4, "risk", None, None, None, unit, n_cols,
                   len(grid), 0, "[]",
                   json.dumps(grid, ensure_ascii=False), "[]", "[]"))
    c.commit()
    return c


OPENER_TR = ("Bankanın tasfiyesi hâlinde alacak hakkı açısından diğer tüm "
             "alacaklardan sonra gelen ödenmiş sermaye")


def test_tr_template_roles_scaling_and_dash(tmp_path):
    """A Milyon filing: money rows scale ×1000, the ratio row does not, and a
    printed "-" stays NULL rather than becoming 0."""
    db = _db(tmp_path, [
        (30, 1, "milyon", [
            (OPENER_TR, [7000.0, 7000.0]),
            ("Hisse senedi ihraç primleri", ["-", "-"]),
            ("Çekirdek Sermayeden Yapılan İndirimler Toplamı", [70.0, 40.0]),
            ("Çekirdek Sermaye Toplamı", [280.0, 300.0]),
        ]),
        (31, 1, "milyon", [
            ("İlave Ana Sermaye Toplamı", [50.0, 25.0]),
            ("Ana Sermaye Toplamı (Ana Sermaye= Çekirdek Sermaye + İlave "
             "Ana Sermaye)", [330.0, 325.0]),
            ("Katkı Sermaye Toplamı", [60.0, 55.0]),
            ("TOPLAM ÖZKAYNAK (ANA SERMAYE VE KATKI SERMAYE TOPLAMI)",
             [390.0, 380.0]),
            ("Toplam Özkaynak", [388.0, 378.0]),
            ("Toplam risk ağırlıklı tutarlar", [2425.0, 2375.0]),
            ("Sermaye Yeterliliği Standart Oranı (%)", [16.0, 15.9]),
        ]),
    ])
    got = C.assemble(db, KEY)
    roles = {r.get("role"): r for r in got["rows"] if r.get("role")}
    assert roles["paid_in_capital"]["cur"] == 7_000_000.0        # ×1000
    assert roles["share_premium"]["cur"] is None                 # "-" not 0
    assert roles["cet1_total"]["cur"] == 280_000.0
    assert roles["at1_total"]["cur"] == 50_000.0
    assert roles["tier1_total"]["cur"] == 330_000.0
    assert roles["tier2_total"]["cur"] == 60_000.0
    assert roles["total_own_funds"]["cur"] == 390_000.0          # the sum row
    assert roles["total_own_funds_final"]["cur"] == 388_000.0    # the final
    assert roles["total_rwa"]["cur"] == 2_425_000.0
    assert roles["capital_adequacy_ratio"]["cur"] == 16.0        # NOT scaled


def test_en_digit_tier_dialect_and_header_seed(tmp_path):
    """YKBNK-style: no tasfiyesi opener — the bare header row seeds a LARGE
    block — and TIER is written with digits, not romans."""
    filler = [(f"Deduction item {i} from capital", ["-", "-"])
              for i in range(12)]
    db = _db(tmp_path, [
        (36, 1, "bin", [
            ("Common Equity Tier 1 Capital", [None, None]),
            ("Paid-in Capital", [4972554.0, 4972554.0]),
            *filler,
            ("Total Common Equity Tier 1 Capital", [442232565.0, 438100969.0]),
            ("Total Additional Tier 1 Capital", [10.0, 10.0]),
            ("Total Tier 1 Capital", [442232575.0, 438100979.0]),
            ("Total Tier 2 Capital", [50000.0, 40000.0]),
            ("Total Capital (The sum of Tier 1 Capital and Tier 2 Capital)",
             [442282575.0, 438140979.0]),
        ]),
    ])
    got = C.assemble(db, KEY)
    assert got is not None                         # header dialect seeded
    roles = {r.get("role"): r for r in got["rows"] if r.get("role")}
    assert roles["cet1_total"]["cur"] == 442232565.0
    assert roles["at1_total"]["cur"] == 10.0
    assert roles["tier1_total"]["cur"] == 442232575.0
    assert roles["tier2_total"]["cur"] == 50000.0
    assert roles["total_own_funds"]["cur"] == 442282575.0


def test_a_small_header_block_does_not_seed(tmp_path):
    """The 4-row reconciliation snippet in the notes opens with the same
    header; the min-rows guard keeps it from seeding a phantom table."""
    db = _db(tmp_path, [
        (77, 1, "bin", [
            ("Common Equity Tier 1 Capital", [100.0, 90.0]),
            ("Total Capital", [120.0, 110.0]),
        ]),
    ])
    assert C.assemble(db, KEY) is None


def test_chain_stops_at_page_gap_before_the_lookalike(tmp_path):
    """GARAN prints an equity reconciliation table pages later that reuses
    CET1 vocabulary; the page gap is what keeps it out."""
    db = _db(tmp_path, [
        (45, 1, "bin", [
            (OPENER_TR, [100.0, 90.0]),
            ("Çekirdek Sermaye Toplamı", [95.0, 85.0]),
        ]),
        (60, 1, "bin", [                       # gap: p46-59 hold no blocks
            ("Common Equity Tier 1 Capital", [999.0, 999.0]),
            ("Deductions from Common Equity Tier 1 Capital", [1.0, 1.0]),
        ]),
    ])
    got = C.assemble(db, KEY)
    assert {r["page"] for r in got["rows"]} == {45}
    assert all(r["cur"] != 999.0 for r in got["rows"])


def test_second_template_truncates(tmp_path):
    """Some filers print the whole template twice — current then prior. The
    second opener truncates, so last-match roles stay on the CURRENT table."""
    db = _db(tmp_path, [
        (40, 1, "bin", [
            (OPENER_TR, [100.0]),
            ("Filler capital row one", [1.0]),
            ("Filler capital row two", [2.0]),
            ("Filler capital row three", [3.0]),
            ("Filler capital row four", [4.0]),
            ("Filler capital row five", [5.0]),
            ("Çekirdek Sermaye Toplamı", [95.0]),
        ]),
        (41, 1, "bin", [
            (OPENER_TR, [90.0]),               # the PRIOR-period copy
            ("Çekirdek Sermaye Toplamı", [85.0]),
        ]),
    ])
    got = C.assemble(db, KEY)
    roles = {r.get("role"): r for r in got["rows"] if r.get("role")}
    assert roles["cet1_total"]["cur"] == 95.0      # not the copy's 85
    assert all(r["page"] == 40 for r in got["rows"])


def test_bonus_shares_does_not_steal_net_profit(tmp_path):
    db = _db(tmp_path, [
        (30, 1, "bin", [
            (OPENER_TR, [100.0, 90.0]),
            ("Net Current Period Profit", [10.0, 9.0]),
            ("Bonus Shares from Associates, Subsidiaries and Joint-Ventures "
             "Not Accounted in Current Period's Profit", [1.0, 1.0]),
        ]),
    ])
    got = C.assemble(db, KEY)
    roles = {r.get("role"): r["cur"] for r in got["rows"] if r.get("role")}
    assert roles["net_profit"] == 10.0
    assert roles["bonus_shares"] == 1.0
