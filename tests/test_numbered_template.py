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


def test_leverage_unnumbered_template_by_label_over_split_blocks(tmp_path):
    """BURGAN / ING / ZIRAAT print the fifteen rows without their numbers,
    with sub-headers, sometimes split over two blocks; the chain is read by
    label in template order, and gated on 15 = 13 / 14. The capital note's
    "Tier I capital" rows cannot open a chain."""
    head = [
        ("Bilanço içi varlıklar", [None, None]),
        ("Bilanço içi varlıklar (türev finansal araçlar ile kredi türevleri hariç, teminatlar dahil)", [194153.0, 159040.0]),
        ("(Ana sermayeden indirilen varlıklar)", [572.0, 517.0]),
        ("Bilanço içi varlıklara ilişkin toplam risk tutarı", [193581.0, 158523.0]),
        ("Türev finansal araçlar ile kredi türevleri", [None, None]),
        ("Türev finansal araçlar ile kredi türevlerinin yenileme maliyeti", [2188.0, 5353.0]),
        ("Türev finansal araçlar ile kredi türevlerinin potansiyel kredi risk tutarı", [1152.0, 1081.0]),
        ("Türev finansal araçlar ile kredi türevlerine ilişkin toplam risk tutarı", [3340.0, 6434.0]),
    ]
    tail = [
        ("Menkul kıymet veya emtia teminatlı finansman işlemlerinin risk tutarı", ["-", "-"]),
        ("Aracılık edilen işlemlerden kaynaklanan risk tutarı", ["-", "-"]),
        ("Menkul kıymet veya emtia teminatlı finansman işlemlerine ilişkin toplam risk tutarı", ["-", "-"]),
        ("Bilanço dışı işlemler", [None, None]),
        ("Bilanço dışı işlemlerin brüt nominal tutarı", [49542.0, 43833.0]),
        ("(Krediye dönüştürme oranları ile çarpımdan kaynaklanan düzeltme tutarı)", ["-", "-"]),
        ("Bilanço dışı işlemlere ilişkin toplam risk tutarı", [49542.0, 43833.0]),
        ("Sermaye ve toplam risk", [None, None]),
        ("Ana sermaye", [17414.0, 14396.0]),
        ("Toplam risk tutarı", [246463.0, 208790.0]),
        ("Kaldıraç oranı", [None, None]),
        ("Kaldıraç oranı", [7.07, 6.89]),
    ]
    capital = [
        ("Tier I capital", [20000.0, 18000.0]),
        ("Total deductions from Tier I capital", [100.0, 90.0]),
        ("Total capital", [25000.0, 22000.0]),
    ]
    db = _db(tmp_path, [(40, 1, "bin", capital), (72, 1, "bin", head), (72, 2, "bin", tail)])
    got = LV.assemble(db, KEY)
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert sorted(cur) == list(range(1, 16))
    assert cur[1]["amount"] == 194153.0 and cur[3]["amount_prior"] == 158523.0
    assert cur[13]["role"] == "tier1_capital" and cur[15]["amount"] == 7.07
    assert cur[9]["block_id"] == 2 and cur[6]["block_id"] == 1
    # the ratio off its own arithmetic is refused
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(grid_json, '7.07', '9.9') WHERE page=72")
    db.commit()
    assert LV.assemble(db, KEY) is None


def test_lcr_unnumbered_template_by_label_wrapped_rows_and_period_hints(tmp_path):
    """HALKB / ING / YKBNK print the 23 LCR rows without numbers, current
    and prior in separate blocks, with sub-headers and labels that wrap
    onto a values-only line; read by label through `assemble_by_label`."""
    LC = _load("build_lcr_full")

    def table(hqla, retail, stable, less, whole, op, nonop, other, out_, inflow, net, ratio):
        return [
            ("Total Unweighted Value (1)", [None, None, None, None]),
            ("High Quality Liquid Assets", [None, None, None, None]),
            ("High Quality Liquid Assets", [None, None, hqla, hqla / 2]),
            ("Cash Outflows", [None, None, None, None]),
            ("Retail and Small Business Customers Deposits", [retail, retail / 2, retail / 10, retail / 20]),
            ("Stable Deposits", [stable, "-", stable / 20, "-"]),
            ("Less Stable Deposits", [less, less / 2, less / 10, less / 20]),
            ("Unsecured Wholesale Funding", [whole, whole / 2, whole / 2, whole / 4]),
            ("Operational Deposits", [op, op / 2, op / 4, op / 8]),
            ("Non-Operational Deposits", [nonop, nonop / 2, nonop / 2, nonop / 4]),
            ("Other Unsecured Funding", [other, other / 2, other, other / 2]),
            ("Secured Funding", [None, None, "-", "-"]),
            ("Other Revocable Off-Balance Sheet Commitments and Contractual", [None, None, None, None]),
            ("Obligations", ["-", "-", "-", "-"]),
            ("Total Cash Outflows", [None, None, out_, out_ / 3]),
            ("Cash Inflows", [None, None, None, None]),
            ("Unsecured Lending", [inflow, inflow / 4, inflow / 2, inflow / 8]),
            ("Total Cash Inflows", [inflow, inflow / 4, inflow / 2, inflow / 8]),
            ("Total Adjusted Value", [None, None, None, None]),
            ("Total HQLA Stock", [None, None, hqla, hqla / 2]),
            ("Total Net Cash Outflows", [None, None, net, net / 3]),
            ("Liquidity Coverage Ratio (%)", [None, None, ratio, ratio * 1.3]),
        ]
    cur = table(1418220.0, 1693538.0, 333770.0, 1359768.0, 1781375.0, 303080.0, 1336934.0, 141361.0,
                1210772.0, 477547.0, 891262.0, 159.62)
    pri = table(1470902.0, 1570111.0, 294494.0, 1275617.0, 1577298.0, 315990.0, 1261308.0, 120000.0,
                1100000.0, 400000.0, 816463.0, 180.35)
    db = _db(tmp_path, [(52, 1, "bin", cur), (53, 1, "bin", pri)])
    db.execute("UPDATE bank_audit_document_tables SET heading=? WHERE page=53", ("Prior Period TRY+FC FC TRY+FC FC",))
    db.execute("UPDATE bank_audit_document_tables SET heading=? WHERE page=52", ("Current Period TRY+FC FC TRY+FC FC",))
    db.commit()
    got = LC.assemble(db, KEY)
    assert sorted(got["instances"]) == ["current", "prior"]
    c = {x["template_row"]: x for x in got["instances"]["current"]}
    assert c[1]["w_total"] == 1418220.0 and c[1]["uw_total"] is None
    assert c[14]["uw_total"] is None and c[14]["label"].startswith("Other Revocable")   # the wrapped "-" row
    assert c[23]["w_total"] == 159.62 and c[23]["role"] == "lcr" and c[20]["role"] == "total_cash_inflows"
    p_ = {x["template_row"]: x for x in got["instances"]["prior"]}
    assert p_[23]["w_total"] == 180.35 and p_[21]["w_total"] == 1470902.0
    # a ratio far off its own arithmetic is refused
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(grid_json, '159.62', '400.0') WHERE page=52")
    db.commit()
    assert list(LC.assemble(db, KEY)["instances"]) == ["prior"]


def test_nsfr_by_label_per_block_columns_and_the_prose_tail(tmp_path):
    """TEB prints the NSFR rows without numbers, over two blocks of DIFFERENT
    widths, and its last two rows ("Gerekli İstikrarlı Fon 364,384") are
    prose lines the capture kept out of the grid — supplied by `tail_of`
    and gated on 34 = 14 / 33."""
    NS = _load("build_nsfr_full")
    head = [                                   # six cells
        ("Mevcut İstikrarlı Fon", [None, None, None, None, None, None]),
        ("Özkaynak Unsurları", ["-", "-", None, "-", 111881.0, 111881.0]),
        ("Ana Sermaye ve Katkı Sermaye", ["-", "-", None, "-", 111881.0, 111881.0]),
        ("Diğer Özkaynak Unsurları", ["-", "-", None, "-", "-", "-"]),
        ("Gerçek Kişi ve Perakende Müşteri Mevduatı/Katılım Fonu", [136682.0, 219075.0, None, "-", "-", 326759.0]),
        ("İstikrarlı Mevduat/Katılım Fonu", [50000.0, 100000.0, None, "-", "-", 150000.0]),
        ("Düşük İstikrarlı Mevduat/Katılım Fonu", [86682.0, 119075.0, None, "-", "-", 176759.0]),
        ("Diğer Kişilere Borçlar", [10000.0, 20000.0, None, "-", "-", 30000.0]),
        ("Operasyonel Mevduat/Katılım Fonu", ["-", "-", None, "-", "-", "-"]),
        ("Diğer Borçlar", [10000.0, 20000.0, None, "-", "-", 30000.0]),
        ("Diğer Yükümlülükler", ["-", "-", None, "-", "-", 51514.0]),
        ("Türev Yükümlülükler", ["-", "-", None, "-", "-", "-"]),
        ("Mevcut İstikrarlı Fon", [None, None, None, None, None, 520154.0]),
        ("Gerekli İstikrarlı Fon", [None, None, None, None, None, None]),
        ("Yüksek Kaliteli Likit Varlıklar", [None, None, None, None, None, 12000.0]),
        ("Canlı Alacaklar", ["-", 39886.0, None, 273202.0, 219374.0, 295185.0]),
    ]
    tail = [                                   # seven cells: a different width
        ("%35 ya da daha düşük risk ağırlığına tabi alacaklar", [35.0, "-", "-", None, "-", 166233.0, 108051.0]),
        ("İkamet amaçlı gayrimenkul ipoteği ile teminatlandırılan alacaklar", [None, "-", "-", None, "-", 4050.0, 2632.0]),
        ("Diğer Varlıklar", [None, 42619.0, 2745.0, None, "-", 617.0, 45726.0]),
        ("Altın dahil fiziki teslimatlı emtia", [None, 1492.0, None, None, None, None, 1268.0]),
        ("Türev Varlıklar", [None, None, None, 2015.0, None, None, 2015.0]),
        ("Yukarıda yer almayan diğer varlıklar", [None, 41127.0, "-", None, "-", 617.0, 41744.0]),
        ("Bilanço Dışı Borçlar", [None, None, "-", None, "-", 430716.0, 21536.0]),
    ]
    db = _db(tmp_path, [(50, 1, "milyon", head), (50, 2, "milyon", tail)])
    db.commit()

    def prose_tail(page, block_id):            # what the ledger would supply
        return [(33, "Gerekli İstikrarlı Fon 364,384", [None, None, None, None, 364384.0]),
                (34, "Net İstikrarlı Fonlama Oranı (%) 142.75", [None, None, None, None, 142.75])]

    got = NT.assemble_by_label(
        db, KEY, labels=NS._BY_LABEL, n_values=5, percent_rows={34}, open_rows={1, 2},
        close_row=34, min_rows=14, role_of=NS._role_of,
        value_names=("no_maturity", "maturity_lt_6m", "maturity_6m_1y", "maturity_gte_1y", "weighted_total"),
        gate=NS._nsfr_gate, tail_of=prose_tail)
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[14]["weighted_total"] == 520_154_000.0        # milyon -> bin
    assert cur[33]["weighted_total"] == 364_384_000.0        # the prose row, scaled like the rest
    assert cur[34]["weighted_total"] == 142.75               # the percent row, never scaled
    assert cur[32]["weighted_total"] == 21_536_000.0         # the seven-cell block, read on ITS columns
    assert cur[1]["weighted_total"] == 111_881_000.0         # the six-cell block, on its own
    # the same chain with a ratio that does not follow from 14 / 33 is refused
    assert NT.assemble_by_label(
        db, KEY, labels=NS._BY_LABEL, n_values=5, percent_rows={34}, open_rows={1, 2},
        close_row=34, min_rows=14, role_of=NS._role_of,
        value_names=("no_maturity", "maturity_lt_6m", "maturity_6m_1y", "maturity_gte_1y", "weighted_total"),
        gate=NS._nsfr_gate,
        tail_of=lambda p, b: [(33, "Gerekli İstikrarlı Fon 364,384", [None] * 4 + [364384.0]),
                              (34, "Net İstikrarlı Fonlama Oranı (%) 999", [None] * 4 + [999.0])]) is None


def test_nsfr_parses_numbers_in_either_printed_convention():
    NS = _load("build_nsfr_full")
    assert NS.parse_printed("364,384") == 364384.0           # thousands, English convention
    assert NS.parse_printed("5.763.908") == 5763908.0        # thousands, Turkish
    assert NS.parse_printed("142.75") == 142.75              # decimals, English
    assert NS.parse_printed("119,90") == 119.90              # decimals, Turkish
    assert NS.parse_printed("1.234.567,89") == 1234567.89
    assert NS.parse_printed("1,234,567.89") == 1234567.89
    assert NS.parse_printed("-12,5") == -12.5
    assert NS.parse_printed("not a number") is None


# --- the RWA overview (OV1) lane, same module -------------------------------

_spec_rwa = importlib.util.spec_from_file_location(
    "build_rwa_full", REPO / "scripts" / "build_rwa_full.py")
RW = importlib.util.module_from_spec(_spec_rwa)
_spec_rwa.loader.exec_module(RW)


def test_rwa_overview_four_column_form(tmp_path):
    """HALKB and QNBFB print all four columns — RWA current / prior, minimum
    capital current / prior. Read as three the reader took the last three
    and shifted every figure one column left, so the total RWA came out as
    the PRIOR total (1,203,850,144 for 1,436,786,128). The 8% ratio on both
    period pairs is what tells the two forms apart."""
    four = [
        ("1 Kredi riski (karşı taraf kredi riski hariç)", [1.0, 1260787163.0, 1058316927.0, 100862973.0, 84665354.0]),
        ("2 Standart yaklaşım", [2.0, 1260787163.0, 1058316927.0, 100862973.0, 84665354.0]),
        ("16 Piyasa riski", [16.0, 70960450.0, 60000000.0, 5676836.0, 4800000.0]),
        ("19 Operasyonel Risk", [19.0, 66027862.0, 60000000.0, 5282229.0, 4800000.0]),
        ("25 Toplam (1+4+7+8+9+10+11+12+16+19+23+24)",
         [25.0, 1436786128.0, 1203850144.0, 114942890.0, 96308011.0]),
    ]
    db = _db(tmp_path, [(85, 1, "bin", four)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               (json.dumps(["", "Current Period", "Prior Period", "Current Period", "Prior Period"]),))
    db.commit()
    cur = {x["template_row"]: x for x in RW.assemble(db, KEY)["instances"]["current"]}
    assert cur[25]["rwa"] == 1436786128.0 and cur[25]["rwa_prior"] == 1203850144.0
    assert cur[25]["min_capital"] == 114942890.0 and cur[25]["min_capital_prior"] == 96308011.0

    # the three-column form still reads as three, with no prior minimum
    three = [
        ("1 Kredi riski (karşı taraf kredi riski hariç)", [1.0, 400000000.0, 380000000.0, 32000000.0]),
        ("16 Piyasa riski", [16.0, 50000000.0, 45000000.0, 4000000.0]),
        ("19 Operasyonel Risk", [19.0, 38583845.0, 35000000.0, 3086708.0]),
        ("25 Toplam (1+4+7+8+9+10+11+12+16+19+23+24)", [25.0, 488583845.0, 475307435.0, 39086708.0]),
    ]
    (tmp_path / "b").mkdir()
    db2 = _db(tmp_path / "b", [(60, 1, "bin", three)])
    db2.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
                (json.dumps(["", "Cari Dönem", "Önceki Dönem", "Asgari sermaye"]),))
    db2.commit()
    cur2 = {x["template_row"]: x for x in RW.assemble(db2, KEY)["instances"]["current"]}
    assert cur2[25]["rwa"] == 488583845.0 and cur2[25]["min_capital"] == 39086708.0
    assert cur2[25]["min_capital_prior"] is None


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


# --- the consumer-loans notes family: group/item roles + per-row identity ---

_spec_cl = importlib.util.spec_from_file_location(
    "build_consumer_loan_full", REPO / "scripts" / "build_consumer_loan_full.py")
CL = importlib.util.module_from_spec(_spec_cl)
_spec_cl.loader.exec_module(CL)


def test_consumer_loans_groups_items_and_row_identity_gate(tmp_path):
    good = [
        ("Tüketici Kredileri-TP", [802.0, 15721.0, 16523.0]),
        ("Konut Kredisi", [16.0, 14267.0, 14283.0]),
        ("Taşıt Kredisi", [150.0, 529.0, 679.0]),
        ("İhtiyaç Kredisi", [635.0, 924.0, 1559.0]),
        ("Diğer", ["-", "-", "-"]),
        ("Bireysel Kredi Kartları-TP", [100.0, "-", 100.0]),
        ("Taksitli", [40.0, "-", 40.0]),
        ("Taksitsiz", [60.0, "-", 60.0]),
        ("Toplam", [902.0, 15721.0, 16623.0]),
    ]
    bad = [(lab, cells[:2] + [999.0]) if lab != "Toplam" else (lab, cells)
           for lab, cells in good]
    db = _db(tmp_path, [(60, 1, "milyon", good), (61, 1, "milyon", bad)])
    got = CL.assemble(db, KEY)
    cur, pri = got["instances"]["current"], got["instances"]["prior"]
    assert CL._identity_holds(cur) and not CL._identity_holds(pri)
    by = {(r["group_role"], r["item_role"]): r for r in cur}
    assert by[("consumer_tl", "housing")]["long_term"] == 14_267_000.0
    assert by[("retail_cards_tl", "instalment")]["short_term"] == 40_000.0
    assert by[("consumer_tl", None)]["total"] == 16_523_000.0       # the group row
    assert by[(None, None)]["label"] == "Toplam"


def test_consumer_loans_header_row_title_row_and_label_variants(tmp_path):
    # AKBNK: a period header row above the first row; HALKB's "-TRY" suffix,
    # "Real Estate Loans", a bare "Installment", "Toplam Tüketici Kredileri"
    akbnk = [
        ("Cari Dönem – 31.12.2025", ["Kısa Vadeli", "Uzun Vadeli", "Toplam"]),
        ("Consumer Loans-TRY", [802.0, 15721.0, 16523.0]),
        ("Real Estate Loans", [16.0, 14267.0, 14283.0]),
        ("Vehicle Loans", [150.0, 529.0, 679.0]),
        ("Consumer Loans", [635.0, 924.0, 1559.0]),
        ("Other", ["-", "-", "-"]),
        ("Individual Credit Cards-TRY", [100.0, "-", 100.0]),
        ("Installment", [40.0, "-", 40.0]),
        ("Non- Installment", [60.0, "-", 60.0]),
        ("Overdraft Accounts-TRY (Retail Customers)(**)", [50.0, "-", 50.0]),
        ("Toplam Tüketici Kredileri", [952.0, 15721.0, 16673.0]),
    ]
    # DENIZ: the note title carries the consumer-TL figures, then a header
    # row, then the items
    deniz = [
        ("4. Tüketici Kredileri, Bireysel Kredi Kartları ve Personel Kredilerine İlişkin Bilgiler", [802.0, 15721.0, 16523.0]),
        ("Kısa Vadeli Orta ve Uzun Vadeli Toplam", [None, None, None]),
        ("Konut Kredisi", [16.0, 14267.0, 14283.0]),
        ("Taşıt Kredisi", [150.0, 529.0, 679.0]),
        ("İhtiyaç Kredisi", [635.0, 924.0, 1559.0]),
        ("Diğer", ["-", "-", "-"]),
        ("Kredili Müstakriz Hesabı-TP (Gerçek Kişi)", [50.0, "-", 50.0]),
        ("Kredili Mevduat Hesabı-TP (Personel)", [5.0, "-", 5.0]),
        ("Toplam(*)", [857.0, 15721.0, 16578.0]),
    ]
    db = _db(tmp_path, [(91, 1, "bin", akbnk), (97, 1, "bin", deniz)])
    got = CL.assemble(db, KEY)
    cur, pri = got["instances"]["current"], got["instances"]["prior"]
    assert CL._identity_holds(cur) and CL._identity_holds(pri)
    by = {(r["group_role"], r["item_role"]): r for r in cur}
    assert cur[0]["label"] == "Consumer Loans-TRY" and by[("consumer_tl", "housing")]["long_term"] == 14267.0
    assert by[("retail_cards_tl", "instalment")]["short_term"] == 40.0
    assert by[("retail_cards_tl", "non_instalment")]["short_term"] == 60.0
    assert by[("overdraft_tl", None)]["total"] == 50.0 and by[(None, None)]["label"] == "Toplam Tüketici Kredileri"
    d = {(r["group_role"], r["item_role"]): r for r in pri}
    assert pri[0]["label"] == "Tüketici Kredileri-TP" and pri[0]["total"] == 16523.0
    assert d[("consumer_tl", "vehicle")]["short_term"] == 150.0 and len(pri) == 8
    assert d[("overdraft_personnel_tl", None)]["short_term"] == 5.0


def test_consumer_loans_isctr_accruals_column_over_split_blocks(tmp_path):
    # ISCTR: short / long / accruals / total over three adjacent blocks, the
    # total in the last; a second filing prints no grand total at all and
    # the chain ends on the commercial-loans block
    head = [("Consumer Loans-TL", [100.0, 200.0, 10.0, 310.0]),
            ("Real Estate Loans", [10.0, 150.0, 5.0, 165.0]),
            ("Vehicle Loans", [20.0, 30.0, 1.0, 51.0]),
            ("General Purpose Consumer Loans", [70.0, 20.0, 4.0, 94.0]),
            ("Consumer Loans – FC Indexed", [None, 2.0, 1.0, 3.0]),
            ("Real Estate Loans", [None, 2.0, 1.0, 3.0])]
    mid = [("Short-Term", ["Term", "Accruals", "Total", None]),
           ("Retail Credit Cards-TL", [50.0, 5.0, 2.0, 57.0]),
           ("With Installments", [20.0, 5.0, 1.0, 26.0]),
           ("Without Installments", [30.0, None, 1.0, 31.0]),
           ("Personnel Loans-TL", [3.0, 4.0, None, 7.0]),
           ("General Purpose Consumer Loans", [3.0, 4.0, None, 7.0]),
           ("Overdraft Accounts – TL (real persons)", [40.0, None, 2.0, 42.0])]
    tail = [("Overdraft Accounts – FC (real persons)", [1.0, None, None, 1.0]),
            ("Total", [194.0, 211.0, 15.0, 420.0])]
    commercial = [("Commercial Loans With Installments-TL", [5.0, 6.0, 1.0, 12.0]),
                  ("Business Loans", [5.0, 6.0, 1.0, 12.0]), ("Other", [None, None, None, None]),
                  ("Total", [5.0, 6.0, 1.0, 12.0])]
    db = _db(tmp_path, [(108, 1, "bin", head), (108, 2, "bin", mid), (108, 3, "bin", tail),
                        (120, 1, "bin", head), (120, 2, "bin", mid), (120, 3, "bin", commercial)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               (json.dumps(["Short-Term", "Term", "Accruals", "Total"]),))
    db.commit()
    got = CL.assemble(db, KEY)
    cur, pri = got["instances"]["current"], got["instances"]["prior"]
    assert CL._identity_holds(cur) and CL._identity_holds(pri)
    assert [x["block_id"] for x in cur] == [1] * 6 + [2] * 6 + [3] * 2
    by = {(r["group_role"], r["item_role"]): r for r in cur}
    assert by[("consumer_tl", "housing")]["accruals"] == 5.0 and by[("consumer_tl", "housing")]["total"] == 165.0
    assert by[("retail_cards_tl", "non_instalment")]["long_term"] is None
    assert by[(None, None)]["total"] == 420.0
    assert len(pri) == 12 and not any(r["label"].startswith("Commercial") for r in pri)


# --- the derivatives notes family: context + Σ-instruments gate -------------

_spec_dv = importlib.util.spec_from_file_location(
    "build_derivative_full", REPO / "scripts" / "build_derivative_full.py")
DV = importlib.util.module_from_spec(_spec_dv)
_spec_dv.loader.exec_module(DV)


def test_derivatives_context_and_sum_gate():
    assert DV.context_of("a. Table of positive differences related to derivative "
                         "financial assets", "x") == "assets"
    assert DV.context_of("Current Period Prior Period TL FC",
                         "Konsolide pasif kalemlere ilişkin açıklamalar") == "liabilities"
    assert DV.context_of("Riskten korunma amaçlı türev finansal varlıklar",
                         None) == "hedging_assets"
    good = [{"role": r, "current_tl": v, "current_fc": None, "prior_tl": None,
             "prior_fc": None} for r, v in (("forward", 410.0), ("swap", 263.0),
                                            ("futures", None), ("options", 98.0),
                                            ("other", None), ("total", 771.0))]
    assert DV._identity_holds(good)
    good[-1]["current_tl"] = 999.0
    assert not DV._identity_holds(good)


def test_derivatives_header_rows_glued_forward_and_inline_instruments(tmp_path):
    # AKBNK / HSBC: a date row and a "TP YP TP YP" line above the first
    # instrument; QNBFB: the forward's figures glued onto the note title
    # above the header lines; ISCTR: valueless "Futures" / "Other" as inline
    # lines; BURGAN: the commitments note is not this family
    akbnk = [
        ("31 Mart 2022", [31.0, None, 31.0, None]),
        ("TP YP TP YP", [None, None, None, None]),
        ("Vadeli İşlemler", [2282941.0, 2388.0, 3902610.0, "-"]),
        ("Swap İşlemleri", [13524803.0, 2258776.0, 17767991.0, 2418025.0]),
        ("Futures İşlemleri", ["-", "-", "-", "-"]),
        ("Opsiyonlar", [62.0, 578506.0, 3788.0, 564064.0]),
        ("Diğer", ["-", "-", "-", "-"]),
        ("Toplam", [15807806.0, 2839670.0, 21674389.0, 2982089.0]),
    ]
    qnbfb = [
        ("Given as collateral/ blocked", ["-", 37354.0, "-", "-"]),
        ("Total", ["-", 37354.0, "-", "-"]),
        ("2.2 Positive differences related to derivative financial assets held for trading",
         [416758.0, 76419.0, 412983.0, 19352.0]),
        ("Current Period Prior Period", [None, None, None, None]),
        ("TL FC TL FC", [None, None, None, None]),
        ("Swap Transactions", [1197241.0, 8591037.0, 833727.0, 3216184.0]),
        ("Futures Transactions", ["-", "-", "-", "-"]),
        ("Options", [12163.0, 1239818.0, 911.0, 503741.0]),
        ("Others", ["-", "-", "-", "-"]),
        ("Total", [1626162.0, 9907274.0, 1247621.0, 3739277.0]),
    ]
    isctr = [
        ("Forward Transactions", [1558715.0, 400701.0, 312088.0, 661448.0]),
        ("Swap Transactions", [1061776.0, 14647323.0, 145386.0, 17376452.0]),
        ("Futures", [None, None, None, None]),
        ("Options", [698.0, 892386.0, 7615.0, 466813.0]),
        ("Other", [None, None, None, None]),
        ("Total", [2621189.0, 15940410.0, 465089.0, 18504713.0]),
    ]
    burgan = [
        ("Forward foreign exchange commitments", [None, None, 6057440.0, 1912509.0]),
        ("Time deposit buy-sell commitments", [None, None, 544185.0, None]),
        ("Forward securities purchase-sale commitments", [None, None, 428782.0, None]),
        ("Payment commitment for check settlements", [None, None, 100731.0, 81744.0]),
        ("Total", [None, None, 7131138.0, 1994253.0]),
    ]
    db = _db(tmp_path, [(69, 3, "bin", akbnk), (101, 3, "bin", qnbfb), (63, 1, "bin", isctr), (80, 1, "bin", burgan)])
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(replace(grid_json, ?, ?), ?, ?)",
               ('"label": "Futures", "cells": [null, null, null, null]}',
                '"label": "Futures", "cells": [null, null, null, null], "inline": true}',
                '"label": "Other", "cells": [null, null, null, null]}',
                '"label": "Other", "cells": [null, null, null, null], "inline": true}'))
    db.commit()
    got = DV.assemble(db, KEY)
    inst = {i["rows"][0]["page"]: i for i in got["instances"]}
    assert sorted(inst) == [63, 69, 101]
    assert all(DV._identity_holds(i["rows"]) for i in inst.values())
    assert [x["role"] for x in inst[69]["rows"]] == ["forward", "swap", "futures", "options", "other", "total"]
    assert inst[101]["rows"][0]["role"] == "forward" and inst[101]["rows"][0]["current_tl"] == 416758.0
    assert [x["role"] for x in inst[63]["rows"]] == ["forward", "swap", "futures", "options", "other", "total"]
    assert inst[63]["rows"][2]["current_tl"] is None


# --- the securities notes family: signed adjustments + head-or-children -----

_spec_sc = importlib.util.spec_from_file_location(
    "build_securities_full", REPO / "scripts" / "build_securities_full.py")
SC = importlib.util.module_from_spec(_spec_sc)
_spec_sc.loader.exec_module(SC)


def test_securities_identity_handles_both_sign_conventions(tmp_path):
    akbnk = [   # "(-)" label, positive figure: subtract
        ("Borçlanma Senetleri", [519.0, 526.0]),
        ("Borsada İşlem Gören (*)", [480.0, 496.0]),
        ("Borsada İşlem Görmeyen", [39.0, 30.0]),
        ("Hisse Senetleri", [1.0, 1.0]),
        ("Borsada İşlem Gören", [None, "-"]),
        ("Borsada İşlem Görmeyen", [1.0, 1.0]),
        ("Değer Azalma Karşılığı (-)", [20.0, 10.0]),
        ("Toplam", [500.0, 517.0]),
    ]
    garan = [   # a signed valuation that ADDS, and an unlisted group label
        ("Debt Securities", [334.0, 300.0]),
        ("Quoted at Stock Exchange", [334.0, 300.0]),
        ("Common Shares/Investment Fund", [38.0, 30.0]),
        ("Quoted at Stock Exchange", [4.0, 3.0]),
        ("Unquoted at Stock Exchange", [34.0, 27.0]),
        ("Value Increase/Impairment Loss", [30.0, 20.0]),
        ("Total", [402.0, 350.0]),
    ]
    db = _db(tmp_path, [(60, 3, "milyon", akbnk), (61, 2, "milyon", garan)])
    got = SC.assemble(db, KEY)
    a, g = got["instances"]
    assert SC._identity_holds(a["rows"]) and SC._identity_holds(g["rows"])
    rows = {(r["group_role"], r["item_role"]): r for r in g["rows"]}
    assert rows[("share_certificates", "group")]["current"] == 38_000.0
    assert rows[(None, "valuation")]["current"] == 30_000.0
    assert SC.portfolio_of("B. Detailed table of financial assets measured at fair "
                           "value through other comprehensive income", None) == "fvoci"


def test_securities_period_split_by_currency(tmp_path):
    """AKTIF prints TP YP TP YP — the period split by currency, not current
    and prior — and reading the second column as "prior" halved every figure
    against the balance sheet. The period totals are the sums; the halves
    are kept beside them."""
    rows = [
        ("31 Aralık 2022", [None, None, 31.0, None, None, 2022.0, None, 31.0, None, 2021.0, None]),
        ("TP YP TP YP", [None] * 11),
        ("Borçlanma Senetleri (*)", [None, None, None, 5717610.0, None, None, 5824065.0, None, 4186608.0, None, 4039398.0]),
        ("Borsada İşlem Gören", [None, None, None, 5717592.0, None, None, 5824065.0, None, 3817247.0, None, 4039398.0]),
        ("Borsada İşlem Görmeyen", [None, None, None, 18.0, None, None, "-", None, 369361.0, None, "-"]),
        ("Hisse Senetleri", [None, None, None, 1518.0, None, None, 19922.0, None, 1518.0, None, 615.0]),
        ("Borsada İşlem Gören", [None, None, None, "-", None, None, 19307.0, None, "-", None, "-"]),
        ("Borsada İşlem Görmeyen", [None, None, None, 1518.0, None, None, 615.0, None, 1518.0, None, 615.0]),
        ("Değer Azalma Karşılığı (-)", [None, None, None, 3364.0, None, None, 180283.0, None, 3364.0, None, 180283.0]),
        ("Toplam", [None, None, None, 5715764.0, None, None, 5663704.0, None, 4184762.0, None, 3859730.0]),
    ]
    db = _db(tmp_path, [(86, 1, "bin", rows)])
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(grid_json, ?, ?)",
               ('"label": "TP YP TP YP", "cells": [null, null, null, null, null, null, null, null, null, null, null]}',
                '"label": "TP YP TP YP", "cells": [null, null, null, null, null, null, null, null, null, null, null], '
                '"inline": true}'))
    db.commit()
    got = SC.assemble(db, KEY)
    total = [r for r in got["instances"][0]["rows"] if r["item_role"] == "total"][0]
    assert total["current"] == 5715764.0 + 5663704.0          # the period, not the TL half
    assert total["current_tl"] == 5715764.0 and total["current_fc"] == 5663704.0
    assert total["prior"] == 4184762.0 + 3859730.0
    assert SC._identity_holds(got["instances"][0]["rows"])


def test_securities_date_row_phantom_columns_glued_movement_other_and_accruals(tmp_path):
    # VAKBN: a date row above, the figures parked in columns 4 and 8 of a
    # nine-cell row, the amortised-cost movement table glued on below
    vakbn = [
        ("Cari Dönem - 31 Mart 2022 Önceki Dönem -", [None, "-", None, None, 2022.0, None, "-", 31.0, 2021.0]),
        ("Borçlanma Senetleri", [None, None, None, None, 500.0, None, None, None, 400.0]),
        ("Borsada İşlem Gören", [None, None, None, None, 480.0, None, None, None, 390.0]),
        ("Borsada İşlem Görmeyen", [None, None, None, None, 20.0, None, None, None, 10.0]),
        ("Değer Azalma Karşılığı (-)", [None, None, None, None, 5.0, None, None, None, 4.0]),
        ("Toplam", [None, None, None, None, 495.0, None, None, None, 396.0]),
        ("Dönem Başındaki Değer", [None, None, None, None, None, None, None, None, 300.0]),
        ("Dönem İçindeki Alımlar", [None, None, None, None, None, None, None, None, 100.0]),
        ("Dönem Sonu Toplamı", [None, None, None, None, None, None, None, None, 400.0]),
    ]
    # ISCTR: "Not-Quoted (1)", an "Other" that enters the total; TSKB-style
    # negative impairment; SKBNK's accruals, as printed
    isctr = [
        ("Debt Securities", [1000.0, 900.0]),
        ("Quoted on a Stock Exchange", [600.0, 500.0]),
        ("Not-Quoted (1)", [400.0, 400.0]),
        ("Share Certificates", [50.0, 40.0]),
        ("Quoted on a Stock Exchange", [10.0, 8.0]),
        ("Not-Quoted", [40.0, 32.0]),
        ("Impairment provision(-)", [-30.0, -20.0]),
        ("Accruals", [-6.0, -5.0]),
        ("Other", [12.0, 10.0]),
        ("Total", [1026.0, 925.0]),
    ]
    tier2 = [   # the capital note, not this family
        ("Debt instruments to be included in contributed capital", [None, 100.0]),
        ("Subordinated loans", [None, 100.0]),
        ("Subordinated debt instruments", [None, None]),
        ("Total", [None, 100.0]),
    ]
    db = _db(tmp_path, [(63, 1, "bin", vakbn), (70, 1, "bin", isctr), (80, 1, "bin", tier2)])
    got = SC.assemble(db, KEY)
    assert [(len(i["rows"]), SC._identity_holds(i["rows"])) for i in got["instances"]] == [(5, True), (10, True)]
    v = {(r["group_role"], r["item_role"]): r for r in got["instances"][0]["rows"]}
    assert v[("debt_securities", "group")]["current"] == 500.0 and v[("debt_securities", "group")]["prior"] == 400.0
    assert v[(None, "total")]["current"] == 495.0
    i = {(r["group_role"], r["item_role"]): r for r in got["instances"][1]["rows"]}
    assert i[("debt_securities", "unquoted")]["current"] == 400.0
    assert i[("other", "group")]["current"] == 12.0 and i[(None, "valuation")]["current"] == -6.0


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cr1_row_live_cells_unstagger_a_merged_block_and_cr2_is_dropped(tmp_path):
    CQ = _load("build_credit_quality_full")
    current = [
        ("1 Krediler", [1.0, 465313.0, 16102820.0, 412596.0, 16155537.0]),
        ("2 Borçlanma araçları", [2.0, "-", 2226078.0, 519.0, 2225559.0]),
        ("3 Bilanço dışı alacaklar", [3.0, "-", 4765678.0, 14636.0, 4751042.0]),
        ("4 Toplam", [4.0, 465313.0, 23094576.0, 427751.0, 23132138.0]),
    ]
    # AKTIF 2022Q2 p49 block 2: CR1 prior and CR2 captured as ONE six-column
    # grid. CR1 rows sit in columns 1-3 and 5, CR2 rows in 4-5.
    merged = [
        ("1 Krediler", [1.0, 448957.0, 14515241.0, 415427.0, None, 14548771.0]),
        ("2 Borçlanma araçları", [2.0, "-", 686520.0, 167.0, None, 686353.0]),
        ("3 Bilanço dışı alacaklar", [3.0, "-", 4466204.0, 13349.0, None, 4452855.0]),
        ("4 Toplam", [4.0, 448957.0, 19667965.0, 428943.0, None, 19687979.0]),
        ("1 Önceki raporlama dönemi sonundaki temerrüt", [1.0, None, None, None, 448957.0, 318636.0]),
        ("2 Son raporlama döneminden itibaren temerrüt", [2.0, None, None, None, 120768.0, 216863.0]),
        ("4 Aktiften silinen tutarlar", [4.0, None, None, None, -39867.0, -6763.0]),
        ("6 Raporlama dönemi sonundaki temerrüt", [6.0, None, None, None, 465313.0, 448957.0]),
    ]
    # CR3 look-alike: seven value columns, row 4 "Temerrüde düşmüş"
    cr3 = [
        ("1 Krediler", [1.0, 14680356.0, 1475181.0, 333841.0, "-", "-", "-", "-"]),
        ("2 Borçlanma araçları", [2.0, 2225559.0, "-", "-", "-", "-", "-", "-"]),
        ("3 Toplam", [3.0, 16905915.0, 1475181.0, 333841.0, "-", "-", "-", "-"]),
        ("4 Temerrüde düşmüş", [4.0, 465313.0, "-", "-", "-", "-", "-", "-"]),
    ]
    db = _db(tmp_path, [(49, 1, "bin", current), (49, 2, "bin", merged), (49, 3, "bin", cr3)])
    got = CQ.assemble(db, KEY)
    assert set(got["instances"]) == {"current", "prior"}      # CR2 split off and dropped
    assert got["gated"] == 0
    prior = {x["template_row"]: x for x in got["instances"]["prior"]}
    assert prior[1]["defaulted_gross"] == 448957.0
    assert prior[1]["allowances"] == 415427.0
    assert prior[1]["net"] == 14548771.0
    assert prior[2]["defaulted_gross"] is None                 # printed "-"
    assert all(CQ._net_holds(x) for x in prior.values())
    assert not CQ._is_cr1([{"label": l, "cells": c} for l, c in cr3])


def test_cr2_conventions_one_column_shift_and_mint_gate(tmp_path):
    DM = _load("build_defaulted_movement_full")
    akbnk = [   # every line positive; closing = 1 + 2 - 3 - 4 - 5
        ("30 Haziran 2022", [None, 2022.0, 2021.0]),
        ("1 Önceki raporlama dönemi sonundaki temerrüt etmiş krediler", [1.0, 18227817.0, 17880294.0]),
        ("2 Son raporlama döneminden itibaren temerrüt eden krediler", [2.0, 15247803.0, 4891485.0]),
        ("3 Tekrar temerrüt etmemiş durumuna gelen alacaklar", [3.0, 74780.0, 78299.0]),
        ("4 Aktiften silinen tutarlar", [4.0, 12735105.0, 1557732.0]),
        ("5 Diğer değişimler", [5.0, 2106483.0, 2907931.0]),
        ("6 Raporlama dönemi sonundaki temerrüt etmiş krediler", [6.0, 18559252.0, 18227817.0]),
    ]
    signed_one_col = [   # deductions printed negative, a single column
        ("1 Defaulted loans and debt securities at end of the previous reporting period", [1.0, 448957.0]),
        ("2 Loans and debt securities that have defaulted since the last reporting period", [2.0, 120768.0]),
        ("3 Returned to non-defaulted status", [3.0, "-"]),
        ("4 Amounts written off", [4.0, -39867.0]),
        ("5 Other changes", [5.0, -64545.0]),
        ("6 Defaulted loans and debt securities at end of the reporting period", [6.0, 465313.0]),
    ]
    broken = [r for r in signed_one_col]
    broken[5] = ("6 Defaulted loans and debt securities at end of the reporting period", [6.0, 999999.0])
    db = _db(tmp_path, [(50, 1, "bin", akbnk), (51, 1, "bin", signed_one_col), (52, 1, "bin", broken)])
    got = DM.assemble(db, KEY)
    assert set(got["instances"]) == {"current", "prior"} and got["gated"] == 1
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[6]["convention"] == "deductions_3_4_5"
    assert cur[4]["amount"] == 12735105.0 and cur[4]["amount_prior"] == 1557732.0
    assert DM.convention_of(got["instances"]["current"], "amount_prior") == "deductions_3_4_5"
    pri = {x["template_row"]: x for x in got["instances"]["prior"]}
    assert pri[1]["convention"] == "signed"
    assert pri[4]["amount"] == -39867.0 and pri[4]["amount_prior"] is None   # one column, shifted left
    assert pri[3]["amount"] is None


def test_cr5_column_model_reads_split_headers_and_label_roles(tmp_path):
    RW = _load("build_risk_weight_full")
    # ALBRK 2022Q2: the secured column's weight is on a header line above
    # ("35% secured by" / "mortgage"), the 250% column is printed "25" over
    # "0", the others column is labelled "%150 %250 Diğerleri".
    header_rows = [
        ("Current Period", [None, None, None, None, "35% secured by", None, None, None, None, 25.0, None, "Total risk amount"]),
        ("Property", [None, None, None, None, None, None, None, None, None, 0.0, None, "(post-CCF and"]),
        ("Risk Classes/Risk Weighted", [None, 0.0, 10.0, 20.0, "mortgage", 50.0, 75.0, 100.0, 150.0, "150% %", "Others", "CRM)"]),
    ]
    body = [
        ("1 Central governments or central banks", [1.0, 100.0, "-", "-", "-", "-", "-", "-", "-", "-", "-", 100.0]),
        ("6 Banks and intermediary institutions", [6.0, "-", "-", 40.0, "-", 60.0, "-", "-", "-", "-", "-", 100.0]),
        ("7 Corporates", [7.0, "-", "-", "-", "-", "-", "-", 500.0, "-", 10.0, 5.0, 515.0]),
        ("9 Secured by residential property", [9.0, "-", "-", "-", 30.0, "-", "-", "-", "-", "-", "-", 30.0]),
        ("17 Other receivables", [17.0, 7.0, "-", "-", "-", "-", "-", 3.0, "-", "-", "-", 10.0]),
        ("18 Total", [18.0, 107.0, "-", 40.0, 30.0, 60.0, "-", 503.0, "-", 10.0, 5.0, 755.0]),
    ]
    labels = ["", "0%", "10%", "20%", "secured by Property mortgage", "50%", "75%", "100%", "150%", "", "Others", "risk amount (post-CCF and CRM)"]
    db = _db(tmp_path, [(56, 1, "bin", header_rows + body)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?", (json.dumps(labels),))
    db.commit()
    got = RW.assemble(db, KEY)
    inst = got["instances"]["current"]
    assert RW._identity_holds(inst, got["step"])
    tot = {x["col_order"]: x for x in inst if x["role"] == "total"}
    model = [(x["col_role"], x["risk_weight"], x["secured_re"]) for x in tot.values()]
    assert model == [("weight", 0.0, 0), ("weight", 10.0, 0), ("weight", 20.0, 0),
                     ("weight", 35.0, 1), ("weight", 50.0, 0), ("weight", 75.0, 0),
                     ("weight", 100.0, 0), ("weight", 150.0, 0), ("weight", 250.0, 0),
                     ("other", None, 0), ("total", None, 0)]
    assert {x["role"] for x in inst if x["template_row"] == 9} == {"residential_mortgage"}
    assert {x["role"] for x in inst if x["template_row"] == 6} == {"banks_and_brokers"}
    # a 2016-vintage matrix totals on row 17 — the total is found by label
    old = [("1 Merkezi yönetimlerden alacaklar", [1.0, 5.0, "-", "-", "-", "-", "-", "-", "-", 5.0]),
           ("7 Kurumsal alacaklar", [7.0, "-", "-", 1.0, "-", 2.0, "-", 3.0, "-", 6.0]),
           ("8 Perakende alacaklar", [8.0, "-", "-", "-", "-", "-", 4.0, "-", "-", 4.0]),
           ("16 Diğer alacaklar", [16.0, 1.0, "-", "-", "-", "-", "-", 1.0, "-", 2.0]),
           ("17 Toplam", [17.0, 6.0, "-", 1.0, "-", 2.0, 4.0, 4.0, "-", 17.0])]
    labels2 = ["", "%0", "%10", "%20", "%35", "%50", "%75", "%100", "Diğerleri", "Toplam"]
    db2 = _db(tmp_path / "b", [(10, 1, "bin", old)]) if (tmp_path / "b").mkdir() is None else None
    db2.execute("UPDATE bank_audit_document_tables SET col_labels_json=?", (json.dumps(labels2),))
    db2.commit()
    got2 = RW.assemble(db2, KEY)
    assert RW._identity_holds(got2["instances"]["current"], got2["step"])
    # a filing in millions tolerates its own rounding once scaled
    assert RW._identity_holds([
        {"template_row": 1, "role": "x", "col_role": "weight", "col_order": 0, "amount": 1000.0},
        {"template_row": 1, "role": "x", "col_role": "total", "col_order": 1, "amount": 2000.0},
        {"template_row": 2, "role": "x", "col_role": "weight", "col_order": 0, "amount": 1000.0},
        {"template_row": 2, "role": "x", "col_role": "total", "col_order": 1, "amount": 1000.0},
        {"template_row": 3, "role": "x", "col_role": "weight", "col_order": 0, "amount": 1000.0},
        {"template_row": 3, "role": "x", "col_role": "total", "col_order": 1, "amount": 1000.0},
        {"template_row": 4, "role": "x", "col_role": "weight", "col_order": 0, "amount": 1000.0},
        {"template_row": 4, "role": "x", "col_role": "total", "col_order": 1, "amount": 1000.0},
        {"template_row": 18, "role": "total", "col_role": "weight", "col_order": 0, "amount": 4000.0},
        {"template_row": 18, "role": "total", "col_role": "total", "col_order": 1, "amount": 5000.0},
    ], step=1000.0)


def test_deposit_insurance_layouts_wraps_and_total_gate(tmp_path):
    DI = _load("build_deposit_insurance_full")
    standard = [   # covered (cur, prior), exceeding (cur, prior); a wrapped head
        ("Tasarruf Mevduatı", [100.0, 90.0, 300.0, 250.0]),
        ("Tasarruf Mevduatı Niteliğini Haiz DTH", [50.0, 40.0, 200.0, 150.0]),
        ("Tasarruf Mevduatı Niteliğini Haiz Diğ.H.", [10.0, 5.0, 20.0, 10.0]),
        ("Yurt Dışı Şubelerde Bulunan Yabancı Mercilerin", [None, None, None, None]),
        ("Sigortasına Tabi Hesaplar", ["-", "-", "-", "-"]),
        ("Toplam", [160.0, 135.0, 520.0, 410.0]),
    ]
    hsbc = [       # a year header row and a period-major layout
        ("Tasarruf Mevduatı", [2023.0, 2023.0, 2022.0, 2022.0]),
        ("Tasarruf Mevduatı", [100.0, 300.0, 90.0, 250.0]),
        ("DTH", [50.0, 200.0, 40.0, 150.0]),
        ("Diğ.H.", [10.0, 20.0, 5.0, 10.0]),
        ("Toplam (*)", [160.0, 520.0, 135.0, 410.0]),
    ]
    broken = [
        ("Saving Deposits", [100.0, 90.0, 300.0, 250.0]),
        ("Foreign Currency Saving Deposits", [50.0, 40.0, 200.0, 150.0]),
        ("Total", [999.0, 135.0, 520.0, 410.0]),
    ]
    db = _db(tmp_path, [(88, 1, "bin", standard), (89, 1, "bin", hsbc), (90, 1, "bin", broken)])
    db.execute("UPDATE bank_audit_document_tables SET heading='Mevduat Sigortası Kapsamında Bulunan ve Limitini Aşan'")
    db.commit()
    got = DI.assemble(db, KEY)
    a, b, c = got["instances"]
    assert DI.total_check(a) == "holds" and DI.total_check(b) == "holds" and DI.total_check(c) is None
    ra = {x["role"]: x for x in a}
    assert ra["foreign_branches"]["label"].endswith("Sigortasına Tabi Hesaplar")
    assert ra["foreign_branches"]["covered_current"] is None
    rb = {x["role"]: x for x in b}
    assert (rb["saving_tl"]["covered_current"], rb["saving_tl"]["covered_prior"],
            rb["saving_tl"]["exceeding_current"], rb["saving_tl"]["exceeding_prior"]) == (100.0, 90.0, 300.0, 250.0)
    assert rb["saving_fc"]["label"] == "DTH" and rb["saving_other"]["label"] == "Diğ.H."
    assert DI.columns_swapped(["Exceeding the insurance limit", "", "Under the guarantee of insurance", ""], None)
    assert not DI.columns_swapped(["Covered by Deposit Insurance", "", "Over Deposit Insurance Limit", ""], None)


def test_deposit_maturity_header_fragments_page_break_and_prior_total_column(tmp_path):
    DM = _load("build_deposit_maturity_full")
    # ZIRAAT-style: header fragments misaligned by one and two bands in one
    # cell ("Vadesiz İhbarlı", "3-6 Ay 6 Ay-1 Yıl"); matrix broken across
    # two blocks (the total row in the second, which has no header at all)
    block1 = [
        ("7 Gün", [None, None, "1 Aya", None, None, None, "1 Yıl ve", "Birikimli", None]),
        ("Cari Dönem", [None, "Vadesiz İhbarlı", "Kadar", "1-3 Ay", None, "3-6 Ay 6 Ay-1 Yıl", "Üstü", "Mevduat", "Toplam"]),
        ("Tasarruf Mevduatı", [100.0, "-", 10.0, 20.0, 30.0, 40.0, 50.0, 1.0, 251.0]),
        ("Döviz Tevdiat Hesabı", [200.0, "-", 10.0, 10.0, 10.0, 10.0, 10.0, "-", 250.0]),
        ("Yurtiçinde Yer. K.", [150.0, "-", 5.0, 5.0, 5.0, 5.0, 5.0, "-", 175.0]),
        ("Yurtdışında Yer. K.", [50.0, "-", 5.0, 5.0, 5.0, 5.0, 5.0, "-", 75.0]),
        ("Resmî Kur. Mevduatı", [1.0, "-", 1.0, 1.0, 1.0, 1.0, 1.0, "-", 6.0]),
        ("Tic. Kur. Mevduatı", [2.0, "-", 2.0, 2.0, 2.0, 2.0, 2.0, "-", 12.0]),
    ]
    block2 = [
        ("Bankalar Mevduatı", [3.0, "-", 3.0, 3.0, 3.0, 3.0, 3.0, "-", 18.0]),
        ("TC Merkez B.", [3.0, "-", "-", "-", "-", "-", "-", "-", 3.0]),
        ("Yurtiçi Bankalar", ["-", "-", 3.0, 3.0, 3.0, 3.0, 3.0, "-", 15.0]),
        ("Toplam", [306.0, "-", 26.0, 36.0, 46.0, 56.0, 66.0, 1.0, 537.0]),
    ]
    # BURGAN-style: an unlabelled prior-period total column on the right
    burgan = [
        ("Savings Deposits", [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 1.0, 211.0, 180.0]),
        ("Public Deposits", [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, "-", 6.0, 5.0]),
        ("Commercial Deposits", [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, "-", 12.0, 9.0]),
        ("Other Deposits", [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, "-", 18.0, 20.0]),
        ("Bank Deposits", [4.0, "-", "-", "-", "-", "-", "-", 4.0, 4.0]),
        ("Total", [20.0, 26.0, 36.0, 46.0, 56.0, 66.0, 1.0, 251.0, 218.0]),
    ]
    db = _db(tmp_path, [(139, 1, "bin", block1), (139, 2, "bin", block2), (150, 1, "bin", burgan)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=? WHERE page=150",
               (json.dumps(["Demand", "month", "months", "months", "6-12 Months", "year", "Accumulating", "Total", ""]),))
    db.commit()
    got = DM.assemble(db, KEY)
    insts = [i for i in got["instances"] if DM._identity_holds(i["rows"], got["step"])]
    assert len(insts) == 2
    z, b = insts
    first = {x["role"]: dict(x["cells"]) for x in z["rows"]}
    assert first["saving"]["demand"] == 100.0 and first["saving"]["notice_7d"] is None
    assert first["saving"]["m3_6"] == 30.0 and first["saving"]["m6_12"] == 40.0
    assert first["saving"]["y1_plus"] == 50.0 and first["saving"]["accumulating"] == 1.0
    assert first["public"]["total"] == 6.0 and first["cbrt"]["demand"] == 3.0
    assert first["total"]["total"] == 537.0                 # the row from the second block
    cols = [b_ for b_, _v in b["rows"][0]["cells"]]
    assert cols == ["demand", "m1", "m1_3", "m3_6", "m6_12", "y1_plus", "accumulating", "total", "total_prior"]
    assert dict(b["rows"][0]["cells"])["total_prior"] == 180.0


def test_section4_matrices_family_by_vocabulary_tails_and_identity(tmp_path):
    S4 = _load("build_section4_matrix_full")
    fx = [   # AKBNK-style FX position: the FVOCI head lost, its tail keeps the values
        ("Cari Dönem – 31 Aralık 2024", ["EURO", "USD", "Diğer YP", "Toplam"]),
        ("Nakit Değerler ve Merkez Bankası (*)", [10.0, 20.0, 5.0, 35.0]),
        ("Bankalar (*******)", [1.0, 2.0, 1.0, 4.0]),
        ("Gerçeğe Uygun Değer Farkı Kâr / Zarara Yansıtılan", [1.0, 1.0, "-", 2.0]),
        ("Para Piyasalarından Alacaklar", ["-", "-", "-", "-"]),
        ("Finansal Varlıklar", [3.0, 3.0, 1.0, 7.0]),
        ("Krediler (**)", [50.0, 60.0, 1.0, 111.0]),
        ("Diğer Varlıklar (***)", [1.0, 1.0, "-", 2.0]),
        ("Toplam Varlıklar", [66.0, 87.0, 8.0, 161.0]),
        ("Bankalar Mevduatı", [1.0, 1.0, "-", 2.0]),
        ("Döviz Tevdiat Hesabı", [40.0, 50.0, 5.0, 95.0]),
        ("Para Piyasalarına Borçlar", [2.0, 2.0, "-", 4.0]),
        ("Toplam Yükümlülükler", [43.0, 53.0, 5.0, 101.0]),
        ("Net Bilanço Pozisyonu", [23.0, 34.0, 3.0, 60.0]),
        ("Net Nazım Hesap Pozisyonu", [-20.0, -30.0, "-", -50.0]),
    ]
    gap = [   # liquidity gap with a page-break continuation block below
        ("Cari Dönem", ["Vadesiz", "1 Aya Kadar", "1-3 Ay", "3-12 Ay", "1-5 Yıl", "5 Yıl ve Üzeri", "Dağıtılamayan", "Toplam"]),
        ("Nakit Değerler ve Merkez Bankası", [10.0, 5.0, "-", "-", "-", "-", "-", 15.0]),
        ("Bankalar", [1.0, 1.0, 1.0, "-", "-", "-", "-", 3.0]),
        ("Para Piyasalarından Alacaklar", ["-", 2.0, "-", "-", "-", "-", "-", 2.0]),
        ("Verilen Krediler", ["-", 10.0, 20.0, 30.0, 40.0, 5.0, "-", 105.0]),
        ("Diğer Varlıklar", ["-", "-", "-", "-", "-", "-", 4.0, 4.0]),
        ("Toplam Varlıklar", [11.0, 18.0, 21.0, 30.0, 40.0, 5.0, 4.0, 129.0]),
    ]
    gap2 = [
        ("Bankalar Mevduatı", [1.0, 1.0, "-", "-", "-", "-", "-", 2.0]),
        ("Diğer Mevduat", [30.0, 40.0, 10.0, 5.0, "-", "-", "-", 85.0]),
        ("Muhtelif Borçlar", ["-", "-", "-", "-", "-", "-", 3.0, 3.0]),
        ("Toplam Yükümlülükler", [31.0, 41.0, 10.0, 5.0, "-", "-", 3.0, 90.0]),
        ("Likidite (Açığı)/Fazlası", [-20.0, -23.0, 11.0, 25.0, 40.0, 5.0, 1.0, 39.0]),
    ]
    db = _db(tmp_path, [(55, 1, "bin", fx), (60, 1, "bin", gap), (60, 2, "bin", gap2)])
    got = S4.assemble(db, KEY)
    kept = [i for i in got["instances"] if S4._identity_holds(i["rows"], got["step"])]
    fams = {i["family"] for i in kept}
    assert fams == {"fx_position", "liquidity_gap"}
    fxi = next(i for i in kept if i["family"] == "fx_position")
    roles = {x["role"]: dict(x["cells"]) for x in fxi["rows"]}
    assert roles["fvoci"]["usd"] == 3.0 and roles["fvtpl"]["eur"] == 1.0
    assert roles["gap"]["total"] == 60.0 and roles["net_off_balance"]["total"] == -50.0
    assert [b for b, _v in fxi["rows"][0]["cells"]] == ["eur", "usd", "other_fc", "total"]
    g = next(i for i in kept if i["family"] == "liquidity_gap")
    groles = {x["role"]: dict(x["cells"]) for x in g["rows"]}
    assert groles["total_liabilities"]["demand"] == 31.0         # from the continuation block
    assert groles["gap"]["unallocated"] == 1.0 and groles["loans"]["y5_plus"] == 5.0


def test_sector_families_hierarchy_gate_and_group_repairs(tmp_path):
    SE = _load("build_sector_full")
    # loans by currency, English, the industry group printed "Manufacturing"
    albrk = [
        ("Agricultural", [400.0, 2.0, 60.0, 0.4]),
        ("Farming and stockbreeding", [300.0, 1.5, 10.0, 0.1]),
        ("Forestry", [95.0, 0.4, 50.0, 0.3]),
        ("Fishery", [5.0, 0.1, "-", "-"]),
        ("Manufacturing", [5000.0, 22.0, 6000.0, 35.0]),
        ("Mining", [100.0, 0.4, 50.0, 0.3]),
        ("Production", [4500.0, 20.0, 5400.0, 31.0]),
        ("Electricity, gas and water", [400.0, 1.6, 550.0, 3.7]),
        ("Construction", [1000.0, 4.0, 2000.0, 12.0]),
        ("Services", [3000.0, 13.0, 4000.0, 23.0]),
        ("Wholesale and retail trade", [3000.0, 13.0, 4000.0, 23.0]),
        ("Other", [600.0, 3.0, 940.0, 5.0]),
        ("Total", [10000.0, 44.0, 13000.0, 75.4]),
    ]
    # stage 2 / 3 / ECL, the agriculture group row wearing a header fragment
    deniz = [
        ("Değer Kaybına Uğramış (TFRS Tam)", [50.0, 20.0, 10.0]),
        ("Çiftçilik ve Hayvancılık", [40.0, 15.0, 8.0]),
        ("Ormancılık", [10.0, 5.0, 2.0]),
        ("Sanayi", [100.0, 40.0, 30.0]),
        ("Madencilik ve Taşocakçılığı", [100.0, 40.0, 30.0]),
        ("İnşaat", [20.0, 10.0, 5.0]),
        ("Hizmetler", [30.0, 10.0, 5.0]),
        ("Ulaşım ve Haberleşme", [30.0, 10.0, 5.0]),
        ("Diğer", [5.0, 5.0, 5.0]),
        ("Toplam", [205.0, 85.0, 55.0]),
    ]
    broken = [(lab, [v * 2 if i == 9 else v for v in cells]) for i, (lab, cells) in enumerate(deniz)]
    db = _db(tmp_path, [(70, 1, "bin", albrk), (80, 1, "bin", deniz), (81, 1, "bin", broken)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=? WHERE page=70",
               (json.dumps(["TRL", "Current (%)", "Period FC", ""]),))
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=? WHERE page>=80",
               (json.dumps(["Stage 2", "Stage 3", "Provisions"]),))
    db.commit()
    got = SE.assemble(db, KEY)
    fams = [(i["family"], SE._hierarchy_holds(i["rows"], "tl" if i["family"] == "loans_currency" else "stage2", 1.0))
            for i in got["instances"]]
    assert fams == [("loans_currency", True), ("stage_ecl", True), ("stage_ecl", False)]
    a = {x["sector"]: dict(x["cells"]) for x in got["instances"][0]["rows"]}
    assert a["mfg_total"]["tl"] == 5000.0 and a["mfg_production"]["tl"] == 4500.0
    assert a["agri_fishery"]["fc"] is None and a["total"]["fc_pct"] == 75.4
    d = {x["sector"]: dict(x["cells"]) for x in got["instances"][1]["rows"]}
    assert d["agri_total"]["stage2"] == 50.0 and d["svc_transport"]["ecl"] == 5.0
    # the risk profile's numeric header row and its class-name fallback
    assert SE._class_header([{"label": "h", "cells": [float(i) for i in range(1, 18)] + ["TP", "YP", "Toplam"]}]) \
        == {**{i: f"class_{i + 1}" for i in range(17)}, 17: "tl", 18: "fc", 19: "total"}
    names = ["Merkezi Yönetimlerden", "Bölgesel", "İdari Birimler", "Çok Taraflı", "Uluslararası Teşkilatlar",
             "Bankalar ve Aracı", "Kurumsal", "Perakende", "İkamet", "Ticari Amaçlı", "Tahsili Gecikmiş",
             "Riski Yüksek", "Teminatlı Menkul", "Menkul Kıymetleştirme", "Kolektif", "Hisse Senedi", "Diğer Alacaklar",
             "TP", "YP", "Toplam"]
    assert SE._classes_from_labels(names, 20)[16] == "class_17"


def test_tl_fc_notes_families_nesting_and_gate(tmp_path):
    TF = _load("build_tl_fc_note_full")
    loans = [
        ("Kısa Vadeli Kredilerden", [100.0, 10.0, 50.0, 6.0]),
        ("Orta ve Uzun Vadeli Kredilerden", [200.0, 20.0, 60.0, 14.0]),
        ("Takipteki Alacaklardan Alınan Faizler", [5.0, "-", 1.0, "-"]),
        ("Kaynak Kul. Destekleme Fonundan Alınan Primler", ["-", "-", "-", "-"]),
        ("Toplam", [305.0, 30.0, 111.0, 20.0]),
    ]
    borrowings = [   # nested: "Bankalara" heads four sub-rows
        ("Bankalara", [24.0, 74.0, 10.0, 57.0]),
        ("T.C. Merkez Bankasına", ["-", "-", "-", "-"]),
        ("Yurtiçi Bankalara", [24.0, 2.0, 10.0, 1.0]),
        ("Yurtdışı Bankalara", ["-", 72.0, "-", 56.0]),
        ("Yurtdışı Merkez ve Şubelere", ["-", "-", "-", "-"]),
        ("Diğer Kuruluşlara", ["-", 10.0, "-", 8.0]),
        ("Toplam", [24.0, 84.0, 10.0, 65.0]),
    ]
    broken = [(lab, cells) for lab, cells in loans[:-1]] + [("Toplam", [999.0, 30.0, 111.0, 20.0])]
    banks_bs = [   # the balance-sheet banks note, same rows as interest-from-banks: not minted
        ("T.C. Merkez Bankası", [1.0, 2.0, 1.0, 2.0]),
        ("Yurtiçi Bankalar", [3.0, 4.0, 3.0, 4.0]),
        ("Yurtdışı Bankalar", ["-", 5.0, "-", 5.0]),
        ("Toplam", [4.0, 11.0, 4.0, 11.0]),
    ]
    db = _db(tmp_path, [(120, 1, "bin", loans), (121, 1, "bin", borrowings), (122, 1, "bin", broken),
                        (60, 1, "bin", banks_bs)])
    db.execute("UPDATE bank_audit_document_tables SET heading='Kredilerden alınan faiz gelirleri TP YP TP YP', "
               "item_title='Gelir tablosuna ilişkin açıklama ve dipnotlar' WHERE page>=120")
    db.execute("UPDATE bank_audit_document_tables SET heading='Bankalara ilişkin bilgiler', "
               "item_title='Bilançonun aktif hesaplarına ilişkin açıklama ve dipnotlar' WHERE page=60")
    db.commit()
    got = TF.assemble(db, KEY)
    fams = [(i["family"], TF._identity_holds(i["rows"], got["step"])) for i in got["instances"]]
    assert fams == [("interest_on_loans", True), ("interest_on_borrowings", True), ("interest_on_loans", False)]
    b = {x["role"]: x for x in got["instances"][1]["rows"]}
    assert b["foreign_banks"]["parent"] == "banks" and b["foreign_banks"]["fc_current"] == 72.0
    assert b["other_institutions"]["parent"] is None and b["total"]["fc_prior"] == 65.0


def test_npl_movement_identities_signed_tails_and_single_group(tmp_path):
    NM = _load("build_npl_movement_full")
    akbnk = [
        ("Önceki Dönem Sonu Bakiyesi: 31 Aralık 2021", [1780068.0, 1068687.0, 15379062.0]),
        ("Dönem İçinde İntikal (+)", [1268263.0, 47635.0, 277714.0]),
        ("Diğer Donuk Alacak Hesaplarından Giriş (+)", ["-", 1771442.0, 327354.0]),
        ("Diğer Donuk Alacak Hesaplarına Çıkış (-)", [1771442.0, 327354.0, "-"]),
        ("Dönem İçinde Tahsilat (-)", [171327.0, 139623.0, 484784.0]),
        ("Kayıttan düşülen (-) (**)", [1933.0, 2931.0, 59413.0]),
        ("Satılan (-)", ["-", "-", "-"]),
        ("Kurumsal ve Ticari Krediler", ["-", "-", "-"]),
        ("Dönem Sonu Bakiyesi", [1103629.0, 2417856.0, 15439933.0]),
        ("Karşılık (-)", [830444.0, 1612088.0, 9879874.0]),
        ("Bilançodaki Net Bakiyesi", [273185.0, 805768.0, 5560059.0]),
    ]
    burgan = [   # wrapped transfer rows keep only their sign; group III only
        ("Prior Period End Balance", [None, None, 100.0]),
        ("Additions (+)", [None, None, 50.0]),
        ("Loans (+)", [None, None, 20.0]),
        ("Loans (-)", [None, None, 5.0]),
        ("Collections (-)", [None, None, 15.0]),
        ("Balance at the End of the Period", [None, None, 150.0]),
        ("Specific Provision (-)", [None, None, 90.0]),
        ("Net Balance on Balance Sheet", [None, None, 60.0]),
    ]
    broken = [(lab, cells) for lab, cells in akbnk]
    broken[-1] = ("Bilançodaki Net Bakiyesi", [1.0, 805768.0, 5560059.0])
    db = _db(tmp_path, [(61, 1, "bin", akbnk), (62, 1, "bin", burgan), (63, 1, "bin", broken)])
    got = NM.assemble(db, KEY)
    assert [NM._convention(i["rows"], got["step"]) for i in got["instances"]] == ["labelled", "labelled", None]
    a = {x["role"]: x["cells"] for x in got["instances"][0]["rows"] if x["role"]}
    assert a["transfers_out"]["group_iii"] == 1771442.0 and a["net"]["group_v"] == 5560059.0
    assert a["sold_corporate"]["group_iii"] is None


def test_stage_movement_phantom_digit_column_undigited_labels_and_stacked_instances(tmp_path):
    SM = _load("build_stage_movement_full")
    # AKBNK-style: the "1." of "1. Aşamaya Transfer" split into a leading
    # column; labels "Aşama Aşama Aşama Toplam"; current and prior stacked
    grid = [
        ("Dönem Başı (31 Aralık 2023)", [None, 1000.0, 200.0, 100.0, 1300.0]),
        ("Dönem İçi İlave", [None, 500.0, 50.0, 20.0, 570.0]),
        ("Dönem İçi Kapanan", [None, -300.0, -30.0, -10.0, -340.0]),
        ("Aktiften Silinen", [None, None, None, -5.0, -5.0]),
        ("1. Aşamaya Transfer", [1.0, 10.0, -10.0, None, None]),
        ("2. Aşamaya Transfer", [2.0, -20.0, 25.0, -5.0, None]),
        ("3. Aşamaya Transfer", [3.0, -5.0, -15.0, 20.0, None]),
        ("Kur Farkı", [None, 15.0, 5.0, None, 20.0]),
        ("Dönem Sonu (31 Aralık 2024)", [None, 1200.0, 225.0, 120.0, 1545.0]),
        ("Dönem Başı (31 Aralık 2022)", [None, 900.0, 150.0, 80.0, 1130.0]),
        ("Dönem İçi İlave", [None, 100.0, 50.0, 20.0, 170.0]),
        ("Dönem Sonu (31 Aralık 2023)", [None, 1000.0, 200.0, 100.0, 1300.0]),
    ]
    db = _db(tmp_path, [(45, 1, "bin", grid)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?, heading=?",
               (json.dumps(["", "Aşama", "Aşama", "Aşama", "Toplam"]), "Beklenen zarar karşılıkları hareket tablosu"))
    db.commit()
    got = SM.assemble(db, KEY)
    assert len(got["instances"]) == 2
    cur, pri = got["instances"]
    assert cur["measure"] == "ecl"
    assert [b for b, _v in cur["rows"][0]["cells"]] == ["stage1", "stage2", "stage3", "total"]
    assert SM._convention(cur["rows"], got["step"]) == "signed" and SM._row_sums_hold(cur["rows"], got["step"])
    assert SM._convention(pri["rows"], got["step"]) == "signed"
    t1 = next(x for x in cur["rows"] if x["role"] == "transfer_to_stage1")
    assert dict(t1["cells"])["stage1"] == 10.0 and dict(t1["cells"])["stage2"] == -10.0


def test_two_period_notes_families_and_total_gate(tmp_path):
    TP = _load("build_two_period_note_full")
    log = [("Kesin teminat mektupları", [100.0, 90.0]), ("Gümrüklere verilen teminat mektupları", [5.0, 4.0]),
           ("Geçici teminat mektupları", [20.0, 15.0]), ("Avans teminat mektupları", [10.0, 8.0]),
           ("Diğer teminat mektupları", [15.0, 13.0]), ("Toplam", [150.0, 130.0])]
    ncl = [("Teminat Mektupları", [150.0, 130.0]), ("Akreditifler", [30.0, 20.0]), ("Banka Kredileri", [5.0, 5.0]),
           ("Diğer Garanti ve Kefaletler", [15.0, 10.0]), ("Toplam", [200.0, 165.0])]
    broken = ncl[:-1] + [("Toplam", [999.0, 165.0])]
    db = _db(tmp_path, [(130, 1, "bin", log), (131, 1, "bin", ncl), (132, 1, "bin", broken)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?", (json.dumps(["Cari Dönem", "Önceki Dönem"]),))
    db.commit()
    got = TP.assemble(db, KEY)
    assert [(i["family"], TP._identity_holds(i["rows"], got["step"])) for i in got["instances"]] == [
        ("letters_of_guarantee", True), ("non_cash_loans", True), ("non_cash_loans", False)]
    a = {x["role"]: x for x in got["instances"][0]["rows"]}
    assert a["customs"]["current"] == 5.0 and a["total"]["prior"] == 130.0


def test_absorb_inline_merges_a_head_only_when_it_earns_a_role():
    grid = [
        {"label": "Varlıklar", "cells": [None, None], "inline": True},        # a sub-header: dropped
        {"label": "Nakit Değerler", "cells": [1.0, 2.0]},
        {"label": "Gerçeğe Uygun Değer Farkı Diğer Kapsamlı", "cells": [None, None], "inline": True},
        {"label": "Finansal Varlıklar", "cells": [3.0, 4.0]},                 # the tail: takes its head
        {"label": "Orphan head", "cells": [None, None], "inline": True},
        {"label": "Krediler", "cells": [5.0, 6.0]},                           # already has a role: head dropped
    ]

    def role(lab):
        if lab.startswith("Nakit"):
            return "cash"
        if lab.startswith("Krediler"):
            return "loans"
        if "Diğer Kapsamlı" in lab:
            return "fvoci"
        return None

    out = NT.absorb_inline(grid, role)
    assert [r["label"] for r in out] == ["Nakit Değerler",
                                         "Gerçeğe Uygun Değer Farkı Diğer Kapsamlı Finansal Varlıklar",
                                         "Krediler"]
    assert out[1]["cells"] == [3.0, 4.0]


def test_movement_notes_subtotal_head_memo_rows_and_conventions(tmp_path):
    MV = _load("build_movement_note_full")
    halkb = [   # "Movements during the period" is a subtotal, not a movement
        ("Balance at the beginning of the period", [2833279.0, 1586859.0]),
        ("Movements during the period", [571920.0, 1246420.0]),
        ("Purchases", [None, 126285.0]),
        ("Bonus shares obtained profit from current year", [1428.0, 9697.0]),
        ("Dividends from current year income", [None, None]),
        ("Sales", [None, None]),
        ("Transfers", [None, 21242.0]),
        ("Revaluation decrease (-) / increase", [570492.0, 1089196.0]),
        ("Impairment provisions (-)/ reversals", [None, None]),
        ("Balance at the end of the period", [3405199.0, 2833279.0]),
        ("Capital commitments", [None, None]),
        ("Share percentage at the end of the period (%)", [None, None]),
    ]
    akbnk = [   # securities: deductions printed negative (signed)
        ("Dönem Başındaki Değer", [164926760.0, 98154676.0]),
        ("Parasal Varlıklarda Meydana Gelen Kur Farkları", [1473127.0, 6299057.0]),
        ("Yıl İçindeki Alımlar", [2999.0, 29740102.0]),
        ("Satış ve İtfa Yolu ile Elden Çıkarılanlar", [-12525826.0, -5337086.0]),
        ("Değer Azalışı Karşılığı", [-30493.0, -14977.0]),
        ("Değerleme Etkisi", [47692522.0, 36084988.0]),
        ("Dönem Sonu Toplamı", [201539089.0, 164926760.0]),
    ]
    labelled = [   # deductions printed positive under "(-)" labels
        ("Dönem Başı Değeri", [100.0, 80.0]),
        ("Alışlar", [30.0, 25.0]),
        ("Satışlar (-)", [10.0, 5.0]),
        ("Değer Azalma Karşılıkları (-)", [5.0, None]),
        ("Dönem Sonu Değeri", [115.0, 100.0]),
    ]
    db = _db(tmp_path, [(104, 1, "bin", halkb), (103, 1, "bin", akbnk), (105, 1, "bin", labelled)])
    got = MV.assemble(db, KEY)
    fams = [(i["family"], MV._convention(i["rows"], got["step"])) for i in got["instances"]]
    assert fams == [("securities_movement", "signed"), ("investment_movement", "signed"),
                    ("securities_movement", "deductions_labelled")]
    h = {x["role"]: x for x in got["instances"][1]["rows"]}
    assert h["movements_subtotal"]["current"] == 571920.0 and h["share_pct"]["after_closing"]


def test_eps_division_gate_share_factor_and_single_column(tmp_path):
    EP = _load("build_eps_full")
    akbnk = [("31 Mart 2026", [2026.0, 2025.0]),
             ("Grubun Net Dönem Kârı", [19151711.0, 13734126.0]),
             ("Çıkarılmış Adi Hisselerin Ağırlıklı Ortalama Adedi (Bin)", [520000000.0, 520000000.0]),
             ("Hisse Başına Kâr (Tam TL tutarı ile gösterilmiştir)", [0.03683, 0.02641])]
    units = [("Net Income/(Loss) to be appropriated to ordinary shareholders", [1000.0]),
             ("Average number of issued common shares", [2000000.0]),       # shares in units
             ("Earnings per share (full TL)", [0.5])]
    broken = [("Dönem Net Karı", [100.0, 90.0]), ("Hisse Adedi (Bin)", [1000.0, 1000.0]),
              ("Hisse Başına Kâr", [0.9, 0.09])]
    db = _db(tmp_path, [(29, 1, "bin", akbnk), (30, 1, "bin", units), (31, 1, "bin", broken)])
    got = EP.assemble(db, KEY)
    fs = [EP._division_factor(i["profit"][0], i["shares"][0], i["eps"][0]) for i in got["instances"]]
    assert fs == [1.0, 1000.0, None]
    assert got["instances"][1]["profit"] == (1000.0, None)


def test_shareholder_loans_inline_header_wrapped_labels_and_the_note_sentence(tmp_path):
    """The cash / non-cash pair that names the columns is an inline header
    row (HSBC, BURGAN) the grid loses; ZIRAATK wraps every label onto a
    "Krediler" row that carries the values; BURGAN's note sentence mentions
    employees and must not take that role from the row that has the money."""
    SH = _load("build_shareholder_loans_full")
    burgan = [
        ("1. Information on all types of loan or advance granted to shareholders and employees of the Bank", [None, None, None, None]),
        ("Direct Loans Granted To Shareholders", ["-", 89324.0, "-", 24860.0]),
        ("Cash Non-Cash Cash Non-Cash", [None, None, None, None]),
        ("Corporate Shareholders", ["-", 89324.0, "-", 24860.0]),
        ("Real Person Shareholders", ["-", "-", "-", "-"]),
        ("Indirect Loans Granted To Shareholders", ["-", "-", "-", "-"]),
        ("Loans Granted To Employees", [4180.0, "-", 4361.0, "-"]),
        ("Total", [4180.0, 89324.0, 4361.0, 24860.0]),
    ]
    ziraatk = [
        ("30 Haziran 2023 Krediler", [3330.0, "-", 2374.0, "-"]),
        ("Nakdi Gayrinakdi Nakdi Gayrinakdi", [None, None, None, None]),
        ("Banka Ortaklarına Verilen Doğrudan", [None, None, None, None]),
        ("Tüzel Kişi Ortaklara Verilen", [None, None, None, None]),
        ("Krediler", [3330.0, "-", 2374.0, "-"]),
        ("Gerçek Kişi Ortaklara Verilen", [None, None, None, None]),
        ("Krediler", ["-", "-", "-", "-"]),
        ("Banka Ortaklarına Verilen Dolaylı", [None, None, None, None]),
        ("Krediler", ["-", "-", "-", "-"]),
        ("Banka Mensuplarına Verilen Krediler", [202860.0, "-", 101173.0, "-"]),
        ("Toplam(*)", [206190.0, "-", 103547.0, "-"]),
    ]
    db = _db(tmp_path, [(60, 1, "bin", burgan), (69, 2, "bin", ziraatk)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json='[]', heading=?, grid_json="
               "replace(replace(grid_json, ?, ?), ?, ?)",
               ("A) Bilgiler",
                '"label": "Cash Non-Cash Cash Non-Cash", "cells": [null, null, null, null]}',
                '"label": "Cash Non-Cash Cash Non-Cash", "cells": [null, null, null, null], "inline": true}',
                '"label": "Nakdi Gayrinakdi Nakdi Gayrinakdi", "cells": [null, null, null, null]}',
                '"label": "Nakdi Gayrinakdi Nakdi Gayrinakdi", "cells": [null, null, null, null], "inline": true}'))
    db.commit()
    got = SH.assemble(db, KEY)
    assert [SH._identities_hold(i, got["step"]) for i in got["instances"]] == [True, True]
    b = {x["role"]: x for x in got["instances"][0] if x["role"]}
    assert b["employees"]["cash_current"] == 4180.0        # not the note's sentence
    assert b["total"]["noncash_prior"] == 24860.0
    z = {x["role"]: x for x in got["instances"][1] if x["role"]}
    assert z["direct_legal"]["cash_current"] == 3330.0     # the wrapped label took its values
    assert z["employees"]["cash_prior"] == 101173.0 and z["total"]["cash_current"] == 206190.0


def test_shareholder_loans_drop_the_capture_duplicate_only_when_it_balances(tmp_path):
    """EMLAK's capture copies the employees row's figures onto the indirect
    row above it, so the sum double-counts. A consecutive pair carrying the
    same tuple may be dropped — but only the one whose removal makes the
    template's own total come out, and only when the plain sum has already
    failed."""
    SH = _load("build_shareholder_loans_full")
    emlak = [
        ("Grup Ortaklarına Verilen Doğrudan Krediler", [110617.0, "-", 714824.0, "-"]),
        ("Tüzel Kişi Ortaklara Verilen Krediler", [110617.0, "-", 714824.0, "-"]),
        ("Gerçek Kişi Ortaklara Verilen Krediler", ["-", "-", "-", "-"]),
        ("Grup Ortaklarına Verilen Dolaylı Krediler", [997.0, "-", 973.0, "-"]),
        ("Banka Mensuplarına Verilen Krediler", [997.0, "-", 973.0, "-"]),
        ("Toplam", [111614.0, "-", 715797.0, "-"]),
    ]
    db = _db(tmp_path, [(48, 3, "bin", emlak)])
    db.execute("UPDATE bank_audit_document_tables SET heading='Cari Dönem Önceki Dönem Nakdi G.Nakdi Nakdi G.Nakdi'")
    db.commit()
    got = SH.assemble(db, KEY)
    assert SH._identities_hold(got["instances"][0], got["step"])
    # a total that no single dropped duplicate reconciles stays refused
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(grid_json, '111614', '999999')")
    db.commit()
    got = SH.assemble(db, KEY)
    assert not SH._identities_hold(got["instances"][0], got["step"])


def test_eps_four_column_blocks_and_the_lost_decimal_comma(tmp_path):
    """HALKB prints the cumulative and quarterly EPS side by side (four
    columns, the cumulative pair outside); BURGAN prints "1,640" for 1.640
    TL per 1,000 nominal and the capture reads 1640 — repaired only because
    the repair is what makes profit / shares come out."""
    EP = _load("build_eps_full")
    halkb = [
        ("Net income/(loss) to be appropriated to ordinary shareholders", [20203677.0, 20203677.0, 15056329.0, 15056329.0]),
        ("Number of issued ordinary shares (thousand)", [7184778.0, 7184778.0, 7184778.0, 7184778.0]),
        ("Earnings per share (in full TRY)", [2.81201, 2.81201, 2.09559, 2.09559]),
    ]
    burgan = [
        ("Adi hissedarlara dağıtılabilir net kar/(zarar)", [500231.0, 552874.0]),
        ("Çıkarılmış adi hisselerin ağırlıklı ortalama adedi (adet)", [305000000.0, 305000000.0]),
        ("Adi hisse başına kar/(zarar) (1.000 nominal için tam TL)", [1640.0, 1813.0]),
    ]
    db = _db(tmp_path, [(41, 1, "bin", halkb)])
    got = EP.assemble(db, KEY)
    i = got["instances"][0]
    assert i["profit"] == (20203677.0, 15056329.0) and i["shares"] == (7184778.0, 7184778.0)
    assert i["eps"] == (2.81201, 2.09559)                  # the cumulative pair, not the quarter's
    assert EP._division_factor(i["profit"][0], i["shares"][0], i["eps"][0]) == 1.0

    (tmp_path / "b").mkdir()
    db2 = _db(tmp_path / "b", [(40, 1, "bin", burgan)])
    j = EP.assemble(db2, KEY)["instances"][0]
    eps, f = EP.repair_eps(j["profit"][0], j["shares"][0], j["eps"][0])
    assert eps == 1.640 and f == 1000.0
    # a printed EPS that no repair reconciles stays refused
    assert EP.repair_eps(6438442.0, 1193585.0, 5331.0) == (5331.0, None)


def test_stage_movement_subject_and_single_band_guard(tmp_path):
    """The same three-stage roll-forward is printed for cash, securities and
    off-balance-sheet exposures. Only the loan one is comparable with the
    narrow stage lane, so the subject is recorded; and a table with figures
    in one stage only is another movement note that happens to roll."""
    SM = _load("build_stage_movement_full")
    loans = [
        ("Kredilere ilişkin beklenen zarar karşılıkları", [None, None, None, None]),
        ("Dönem Başı Bakiye", [1000.0, 200.0, 100.0, 1300.0]),
        ("Dönem İçi İlave", [500.0, 50.0, 20.0, 570.0]),
        ("Dönem Sonu Bakiye", [1500.0, 250.0, 120.0, 1870.0]),
    ]
    one_band = [
        ("Balances at Beginning of Period", [237052.0, None, None, 237052.0]),
        ("Additions during the Period (+)", [2570304.0, None, None, 2570304.0]),
        ("Balances at End of Period", [2807356.0, None, None, 2807356.0]),
    ]
    db = _db(tmp_path, [(60, 1, "bin", loans), (92, 1, "bin", one_band)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?, heading=? WHERE page=60",
               (json.dumps(["1. Aşama", "2. Aşama", "3. Aşama", "Toplam"]),
                "Kredilere ilişkin beklenen zarar karşılıkları"))
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?, heading=? WHERE page=92",
               (json.dumps(["1. Aşama", "2. Aşama", "3. Aşama", "Toplam"]),
                "(Thousands of Turkish Lira (TL))"))
    db.commit()
    got = SM.assemble(db, KEY)
    assert len(got["instances"]) == 1                       # the single-band table is not the form
    inst = got["instances"][0]
    assert inst["subject"] == "loans" and inst["measure"] == "ecl"
    assert SM._subject("Nakit ve nakit benzerleri için beklenen zarar", [], []) is None


def test_derivative_maturity_table_is_not_the_trading_note(tmp_path):
    """GARAN prints the instrument rows again split by remaining maturity;
    its columns are months, not TL / FC, and reading it as the note put
    4.9bn against the balance sheet's 16.6bn."""
    DV = _load("build_derivative_full")
    rows = [
        ("Vadeli İşlemler", [100.0, 200.0, 300.0, 600.0]),
        ("Swap İşlemleri", [400.0, 500.0, 600.0, 1500.0]),
        ("Futures İşlemleri", ["-", "-", "-", "-"]),
        ("Opsiyonlar", [10.0, 20.0, 30.0, 60.0]),
        ("Diğer", ["-", "-", "-", "-"]),
        ("Toplam", [510.0, 720.0, 930.0, 2160.0]),
    ]
    db = _db(tmp_path, [(106, 1, "bin", rows)])
    db.execute("UPDATE bank_audit_document_tables SET heading=?, item_title=?",
               ("TL FC Prior Period Medium and Long Term", "Türev finansal borçlar"))
    db.commit()
    assert DV.assemble(db, KEY) is None
    assert DV._is_maturity_table("Kalan vadeye göre türev işlemler", None, [])
    assert not DV._is_maturity_table("Alım satım amaçlı türev finansal borçlar", None, [])


def test_risk_weight_reads_the_unnumbered_cr5(tmp_path):
    """AKTIF and ATBANK print CR5's asset classes without the regulator's
    row numbers; the body rows are then the class rows themselves, the form
    is numbered by its own order, and the row sums still gate."""
    RW = _load("build_risk_weight_full")
    header = ("Risk Sınıfları / Risk Ağırlığı", [0.0, 10.0, 20.0, 50.0, 75.0, 100.0, 150.0, "Toplam"])
    body = [
        ("Merkezi yönetimlerden veya merkez bankalarından alacaklar", [8917818.0, "-", "-", "-", "-", "-", "-", 8917818.0]),
        ("Bölgesel yönetimlerden veya yerel yönetimlerden alacaklar", ["-", "-", "-", "-", "-", "-", "-", "-"]),
        ("İdari birimlerden ve ticari olmayan girişimlerden alacaklar", ["-", "-", "-", "-", "-", 1000.0, "-", 1000.0]),
        ("Çok taraflı kalkınma bankalarından alacaklar", ["-", "-", "-", "-", "-", "-", "-", "-"]),
        ("Uluslararası teşkilatlardan alacaklar", ["-", "-", "-", "-", "-", "-", "-", "-"]),
        ("Bankalardan ve aracı kurumlardan alacaklar", ["-", "-", 500000.0, 250000.0, "-", "-", "-", 750000.0]),
        ("Kurumsal alacaklar", ["-", "-", "-", "-", "-", 4000000.0, "-", 4000000.0]),
        ("Perakende alacaklar", ["-", "-", "-", "-", 2000000.0, "-", "-", 2000000.0]),
        ("Diğer alacaklar", ["-", "-", "-", "-", "-", 82182.0, "-", 82182.0]),
        ("Toplam", [8917818.0, "-", 500000.0, 250000.0, 2000000.0, 4083182.0, "-", 15751000.0]),
    ]
    db = _db(tmp_path, [(51, 2, "bin", [header] + body)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               ('["%0","%10","%20","%50","%75","%100","%150","Toplam"]',))
    db.commit()
    got = RW.assemble(db, KEY)
    cur = got["instances"]["current"]
    assert RW._identity_holds(cur, got["step"])
    weights = sorted({x["risk_weight"] for x in cur if x["col_role"] == "weight"})
    assert weights == [0.0, 10.0, 20.0, 50.0, 75.0, 100.0, 150.0]
    first = [x for x in cur if x["template_row"] == 1]
    assert first[0]["role"] == "central_governments" and first[0]["amount"] == 8917818.0
    # the form's own order numbers it: the total row is the tenth
    assert max(x["template_row"] for x in cur) == 10


def test_exposure_class_reads_the_unnumbered_cr4_by_label(tmp_path):
    """AKBNK and the participation banks print CR4's eighteen asset classes
    without the regulator's row numbers; the label chain reads them and the
    density identity on the total row still decides."""
    EC = _load("build_exposure_class_full")
    rows = [
        ("Merkezi yönetimlerden veya merkez bankalarından alacaklar", [382980743.0, 37868.0, 387042538.0, 15766.0, 429365.0, 0.11]),
        ("Bölgesel yönetimlerden veya yerel yönetimlerden alacaklar", [48174.0, "-", 48174.0, "-", 24087.0, 50.0]),
        ("İdari birimlerden ve ticari olmayan girişimlerden alacaklar", [713879.0, 407967.0, 657850.0, 210079.0, 867930.0, 100.0]),
        ("Çok taraflı kalkınma bankalarından alacaklar", ["-", "-", "-", "-", "-", 0.0]),
        ("Uluslararası teşkilatlardan alacaklar", ["-", "-", "-", "-", "-", 0.0]),
        ("Bankalardan ve aracı kurumlardan alacaklar", [63087399.0, 15101894.0, 63070189.0, 8757026.0, 22366802.0, 31.14]),
        ("Kurumsal alacaklar", [303877331.0, 158663410.0, 297122067.0, 90412597.0, 315542666.0, 81.42]),
        ("Perakende alacaklar", [216842508.0, 280878938.0, 211520162.0, 16451868.0, 185799199.0, 81.5]),
        ("İkamet amaçlı gayrimenkul ipoteği ile teminatlandırılan alacaklar", [10000.0, "-", 10000.0, "-", 3500.0, 35.0]),
        ("Tahsili gecikmiş alacaklar", [5000.0, "-", 5000.0, "-", 5000.0, 100.0]),
        ("Hisse senedi yatırımları", [1000.0, "-", 1000.0, "-", 1000.0, 100.0]),
        ("Toplam", [968565034.0, 455090077.0, 960475980.0, 115847336.0, 526038549.0, 48.87]),
    ]
    db = _db(tmp_path, [(50, 1, "bin", rows)])
    got = EC.assemble(db, KEY)
    cur = {x["template_row"]: x for x in got["instances"]["current"]}
    assert cur[7]["row_role"] == "corporates" if "row_role" in cur[7] else cur[7]["role"] == "corporates"
    assert cur[1]["rwa_density"] == 0.11 and cur[18]["rwa"] == 526038549.0
    assert cur[6]["on_bs_pre_crm"] == 63087399.0           # already canonical bin
    # a total row whose density does not follow from its own RWA is refused
    db.execute("UPDATE bank_audit_document_tables SET grid_json=replace(grid_json, '48.87', '90.0')")
    db.commit()
    assert EC.assemble(db, KEY) is None


def test_capital_mint_gate_refuses_an_equity_note():
    """The own-funds form has no single sum to check, so the gate is its
    landmarks plus one of its two identities. A shareholders'-equity note
    that reaches the roles by accident carries too few landmarks."""
    CP = _load("build_capital_full")

    def roles(**kw):
        return {k: {"cur": v} for k, v in kw.items()}

    # AKBNK's equity note: CET1 and Tier 1 only, and equal, so the first
    # identity passes trivially — the landmark count is what refuses it
    assert not CP.mint_gate(roles(cet1_total=14686252.0, tier1_total=14686252.0))
    # the form proper: four landmarks and tier 1 = CET1 + AT1
    assert CP.mint_gate(roles(cet1_total=327125355.0, at1_total=0.0, tier1_total=327125355.0,
                              total_own_funds=402382324.0, total_rwa=2035471894.0,
                              capital_adequacy_ratio=19.77))
    # landmarks but neither identity: a misread chain is refused
    assert not CP.mint_gate(roles(cet1_total=12558830.0, tier1_total=8585373.0,
                                  total_own_funds=4511856.0, total_rwa=114063225.0,
                                  capital_adequacy_ratio=22.49))
    # the CAR identity alone carries it
    assert CP.mint_gate(roles(tier1_total=100.0, tier2_total=20.0, total_own_funds=120.0,
                              total_rwa=1000.0, capital_adequacy_ratio=12.0))


def test_capital_seeds_on_the_third_and_fourth_dialect(tmp_path):
    """The own-funds template opens four ways across the fleet: the
    tasfiyesi/creditors row, the bare "Çekirdek Sermaye" header over a long
    block, QNBFB's "paid-in capital following all debts in terms of claim in
    liquidation", and FIBA's abbreviated table that opens on a bare
    "Sermaye" row followed by the share-issue premium."""
    CP = _load("build_capital_full")
    qnbfb = [("Explanations on equity", [2026.0, 2025.0]),
             ("Common Equity Tier 1 Capital", [None, None]),
             ("Paid-in capital following all debts in terms of claim in liquidation of the Bank", [5500000.0, 5500000.0]),
             ("Share issue premiums", [714.0, 714.0]),
             ("Reserves", [153216148.0, 105401365.0]),
             ("Common Equity Tier 1 Capital", [158716862.0, 110902079.0])]
    fiba = [("Sermaye", [4550000.0, 4550000.0]),
            ("Hisse senedi ihraç primleri", ["--", "--"]),
            ("Yedek akçeler", [1200000.0, 900000.0]),
            ("Türkiye Muhasebe Standartları (TMS) uyarınca özkaynaklara yansıtılan kazançlar", [50000.0, 40000.0]),
            ("Kâr", [300000.0, 250000.0]),
            ("Net dönem kârı", [300000.0, 250000.0]),
            ("Geçmiş yıllar kârı", ["--", "--"]),
            ("İndirimler öncesi çekirdek sermaye", [6100000.0, 5740000.0]),
            ("Çekirdek sermayeden yapılacak indirimler", [None, None]),
            ("Çekirdek Sermaye", [6100000.0, 5740000.0])]
    db = _db(tmp_path, [(44, 1, "bin", qnbfb)])
    assert CP.assemble(db, KEY) is not None
    (tmp_path / "b").mkdir()
    db2 = _db(tmp_path / "b", [(30, 1, "bin", fiba)])
    assert CP.assemble(db2, KEY) is not None


def test_strip_date_lines_takes_the_row_and_keeps_the_label():
    """The shared helper the note lanes run their grids through: a date row
    of its own goes, a date PREFIX goes but its row stays with the values,
    a "TP YP TP YP" header row goes, and an ordinary row is untouched."""
    grid = [
        {"label": "31 Mart 2022", "cells": [31.0, 2022.0, 31.0, 2021.0]},
        {"label": "TP YP TP YP", "cells": [None, None, None, None]},
        {"label": "30 Haziran 2023 Kasa/Efektif", "cells": [110656.0, 1933573.0, None, None]},
        {"label": "Dönem başındaki değer", "cells": [17532.0, 14374.0, None, None]},
        {"label": "1 Ocak 2024 - 30 Haziran 2024", "cells": [None, None, None, None]},
    ]
    out = NT.strip_date_lines(grid)
    assert [r["label"] for r in out] == ["Kasa/Efektif", "Dönem başındaki değer"]
    assert out[0]["cells"] == [110656.0, 1933573.0, None, None]


def test_tl_fc_note_stops_at_its_own_total(tmp_path):
    """AKTIF prints "1.4. İştirak ve bağlı ortaklıklardan alınan faizler"
    under the securities table, in the same block. Read together, the second
    note's total (7,919) was stored as the securities total against a P&L
    line of 1,031,905."""
    TF = _load("build_tl_fc_note_full")
    grid = [
        ("Gerçeğe Uygun Değer Farkı Kar veya Zarara Yansıtılan", [2154.0, 95.0, 1000.0, 50.0]),
        ("Gerçeğe Uygun Değer Farkı Diğer Kapsamlı Gelire Yansıtılan", [708632.0, 136406.0, 500000.0, 100000.0]),
        ("İtfa Edilmiş Maliyeti Üzerinden Değerlenen", [157892.0, 26726.0, 100000.0, 20000.0]),
        ("Toplam", [868678.0, 163227.0, 601000.0, 120050.0]),
        ("1.4. İştirak ve bağlı ortaklıklardan alınan faizler", [None, 7919.0, None, 5000.0]),
        ("Toplam", [None, 7919.0, None, 5000.0]),
    ]
    db = _db(tmp_path, [(82, 1, "bin", grid)])
    db.execute("UPDATE bank_audit_document_tables SET heading=?, item_title=?",
               ("Cari Dönem Önceki Dönem", "Faiz gelirlerine ilişkin bilgiler"))
    db.commit()
    got = TF.assemble(db, KEY)
    inst = [i for i in got["instances"] if i["family"] == "interest_on_securities"]
    assert len(inst) == 1
    totals = [x for x in inst[0]["rows"] if x["role"] == "total"]
    assert len(totals) == 1 and totals[0]["tl_current"] == 868678.0 and totals[0]["fc_current"] == 163227.0


def test_tl_fc_note_drops_the_date_line_above_the_first_row(tmp_path):
    """The capture prints the note's date line above the first row — as a
    row of its own ("31 Mart 2022 | 31 | 2022", HSBC) or glued onto the
    first label ("30 Haziran 2023 Kasa/Efektif", ZIRAATK, where the row is
    the Kasa row and only the prefix is noise). Either way the first role
    decides the family, so the line has to go."""
    TF = _load("build_tl_fc_note_full")
    hsbc = [
        ("31 Mart 2022", [31.0, 2022.0, 31.0, 2021.0]),
        ("TP YP TP YP", [None, None, None, None]),
        ("T.C. Merkez Bankasından", [851.0, "-", "-", "-"]),
        ("Yurtiçi bankalardan", [19296.0, "-", 25789.0, 1.0]),
        ("Yurtdışı bankalardan", [400.0, 227.0, 146.0, 78.0]),
        ("Yurtdışı merkez ve şubelerden", ["-", "-", "-", "-"]),
        ("Toplam", [20547.0, 227.0, 25935.0, 79.0]),
    ]
    ziraatk = [
        ("30 Haziran 2023 Kasa/Efektif", [110656.0, 1933573.0, 121498.0, 827299.0]),
        ("TP YP TP YP", [None, None, None, None]),
        ("T.C. Merkez Bankası(*)", [5547061.0, 31513555.0, 6189305.0, 17634063.0]),
        ("Diğer", ["-", 749964.0, "-", 202080.0]),
        ("Toplam", [5657717.0, 34197092.0, 6310803.0, 18663442.0]),
    ]
    db = _db(tmp_path, [(78, 2, "bin", hsbc), (64, 1, "bin", ziraatk)])
    db.execute("UPDATE bank_audit_document_tables SET heading='Cari Dönem Önceki Dönem', "
               "item_title='Faiz gelirlerine ilişkin bilgiler'")
    db.commit()
    got = TF.assemble(db, KEY)
    fams = [(i["family"], TF._identity_holds(i["rows"], got["step"])) for i in got["instances"]]
    assert fams == [("cash_and_cbrt", True), ("interest_from_banks", True)]
    cash = {x["role"]: x for x in got["instances"][0]["rows"] if x["role"]}
    assert cash["cash"]["label"] == "Kasa/Efektif" and cash["cash"]["tl_current"] == 110656.0
    assert cash["total"]["fc_current"] == 34197092.0
    banks = {x["role"]: x for x in got["instances"][1]["rows"] if x["role"]}
    assert banks["cbrt"]["tl_current"] == 851.0 and banks["total"]["tl_prior"] == 25935.0


def test_shareholder_loans_two_identities(tmp_path):
    SL = _load("build_shareholder_loans_full")
    ok = [("Banka Ortaklarına Verilen Doğrudan Krediler", ["-", 396.0, "-", 159.0]),
          ("Tüzel Kişi Ortaklara Verilen Krediler", ["-", 396.0, "-", 159.0]),
          ("Gerçek Kişi Ortaklara Verilen Krediler", ["-", "-", "-", "-"]),
          ("Banka Ortaklarına Verilen Dolaylı Krediler", [28896527.0, 11739676.0, 18578260.0, 7976515.0]),
          ("Banka Mensuplarına Verilen Krediler", [750313.0, "-", 606978.0, "-"]),
          ("Toplam", [29646840.0, 11740072.0, 19185238.0, 7976674.0])]
    bad = [(lab, cells) for lab, cells in ok]
    bad[1] = ("Tüzel Kişi Ortaklara Verilen Krediler", ["-", 300.0, "-", 159.0])
    db = _db(tmp_path, [(96, 1, "bin", ok), (97, 1, "bin", bad)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               (json.dumps(["Cari Nakdi", "Dönem Gayrinakdi", "Önceki Nakdi", "Dönem Gayrinakdi"]),))
    db.commit()
    got = SL.assemble(db, KEY)
    assert [SL._identities_hold(i, got["step"]) for i in got["instances"]] == [True, False]
    r = {x["role"]: x for x in got["instances"][0]}
    assert r["indirect"]["cash_current"] == 28896527.0 and r["direct_real"]["noncash_prior"] is None


def test_sector_npl_note_with_write_offs_and_the_period_from_its_own_date():
    """Two ways a sector table was filed as the stage/ECL note when it is
    not: TFKB's non-performing note prints receivables / provisions /
    write-offs — three columns, so it fell through to the stage branch — and
    ICBCT prints last year's copy first, which position alone called
    current."""
    SE = _load("build_sector_full")
    grid = [{"label": "Önceki dönem Takipteki Alacak Tutarı Özel Karşılık Aktiften Silinen Tutar",
             "cells": [None, None, None]},
            {"label": "Tarım", "cells": [1659462.0, 1353223.0, 930571.0]},
            {"label": "Çiftçilik ve Hayvancılık", "cells": [530.0, 446.0, 66961.0]},
            {"label": "Ormancılık", "cells": [5.0, 5.0, 3.0]},
            {"label": "Balıkçılık", "cells": [1.0, 1.0, 1.0]},
            {"label": "Toplam", "cells": [1717577.0, 1381251.0, 997611.0]}]
    fam, cols = SE.column_model(grid, ["Takipteki Alacak Tutarı", "Özel Karşılık", "Aktiften Silinen Tutar"], None)
    assert fam == "npl_provisions"
    assert [c for _i, c, _l in cols] == ["npl", "stage3_provision", "written_off"]

    dated = [{"label": "Krediler (1)", "cells": [None, None, None]},
             {"label": "31 Aralık 2022 Önemli sektörler / karşı taraflar", "cells": [None, None, None]},
             {"label": "Tarım", "cells": [1.0, 2.0, 3.0]}]
    assert SE._period_from_dates(dated, "2023Q4") == "prior"
    assert SE._period_from_dates(dated, "2022Q4") == "current"
    assert SE._period_from_dates([{"label": "Tarım", "cells": [1.0]}], "2023Q4") is None


def test_sector_cut_past_another_table_but_not_past_its_own_header(tmp_path):
    """ING prints the sector note in the same block as the risk-weight table
    above it, and the note's rows were being read with that table's columns
    — so the lane fell through to the next page's copy, which is the
    NON-CASH table, and disagreed with the narrow lane on every cell. The
    cut fires only where another table really sits above: fewer than three
    figure-bearing non-sector rows and the block keeps its own header, which
    the column model reads for the class labels."""
    SE = _load("build_sector_full")
    above = [("Kredi riski azaltımı öncesi tutar", [77510790.0, "-", 15437133.0]),
             ("Kredi riski azaltımı sonrası tutar", [77513183.0, "-", 14603328.0]),
             ("Önceki dönem", [42994639.0, "-", 21632773.0])]
    note = [("Tarım", ["-", 13503.0, 21032.0]), ("Çiftçilik ve hayvancılık", ["-", 11231.0, 9005.0]),
            ("Ormancılık", ["-", 114.0, 91.0]), ("Balıkçılık", ["-", 2158.0, 11936.0]),
            ("Sanayi", [4506293.0, 255023.0, 526738.0])]
    assert [r["label"] for r in SE._cut_to_sectors([{"label": lab, "cells": c} for lab, c in above + note])] \
        == [lab for lab, _c in note]
    # two header-ish rows above are the note's own: nothing is cut
    header = [("Cari Dönem", [None, None, None]), ("Değer kaybına uğramış", [None, 9.0, None])]
    kept = SE._cut_to_sectors([{"label": lab, "cells": c} for lab, c in header + note])
    assert [r["label"] for r in kept] == [lab for lab, _c in header + note]


def test_sector_block_holding_two_copies_of_the_table(tmp_path):
    """AKTIF prints the current sector table and last year's in one block.
    Stored as a single instance both copies were labelled 'current', and a
    blank current cell fell through to the prior copy's figure."""
    SE = _load("build_sector_full")
    one = [("Tarım", ["-", 100.0, 90.0]), ("Çiftçilik ve Hayvancılık", ["-", 60.0, 50.0]),
           ("Ormancılık", ["-", 20.0, 20.0]), ("Balıkçılık", ["-", 20.0, 20.0]),
           ("Sanayi", ["-", 3798.0, 3798.0]), ("Madencilik ve Taşocakçılığı", ["-", 3798.0, 3798.0]),
           ("İmalat Sanayi", ["-", "-", "-"]), ("Elektrik, Gaz, Su", ["-", "-", "-"]),
           ("İnşaat", ["-", 10.0, 10.0]), ("Hizmetler", ["-", 30.0, 30.0]),
           ("Toptan ve Perakende Ticaret", ["-", 30.0, 30.0]), ("Diğer", ["-", "-", "-"]),
           ("Toplam", ["-", 3938.0, 3928.0])]
    two = [("Tarım", [1000.0, 200.0, 180.0]), ("Çiftçilik ve Hayvancılık", [600.0, 120.0, 100.0]),
           ("Ormancılık", [200.0, 40.0, 40.0]), ("Balıkçılık", [200.0, 40.0, 40.0]),
           ("Sanayi", [35396.0, 4725.0, 4861.0]), ("Madencilik ve Taşocakçılığı", [35396.0, 4725.0, 4861.0]),
           ("İmalat Sanayi", ["-", "-", "-"]), ("Elektrik, Gaz, Su", ["-", "-", "-"]),
           ("İnşaat", [100.0, 20.0, 20.0]), ("Hizmetler", [300.0, 60.0, 60.0]),
           ("Toptan ve Perakende Ticaret", [300.0, 60.0, 60.0]), ("Diğer", ["-", "-", "-"]),
           ("Toplam", [36796.0, 5005.0, 5121.0])]
    db = _db(tmp_path, [(53, 1, "bin", one + two)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               (json.dumps(["Kredi riskinde önemli artış (ikinci aşama)", "Temerrüt (üçüncü aşama)",
                            "Beklenen kredi zarar karşılıkları"]),))
    db.commit()
    got = SE.assemble(db, KEY)
    assert [i["period_label"] for i in got["instances"]] == ["current", "prior"]
    cur = {(x["sector"], n): v for x in got["instances"][0]["rows"] for n, v in x["cells"]}
    pri = {(x["sector"], n): v for x in got["instances"][1]["rows"] for n, v in x["cells"]}
    assert cur[("mfg_mining", "stage3")] == 3798.0 and cur[("mfg_mining", "stage2")] is None
    assert pri[("mfg_mining", "stage2")] == 35396.0        # last year's, kept apart
    assert SE._split_on_restart([{"sector": "agri_total"}, {"sector": "total"},
                                 {"sector": "agri_total"}]) == [
        [{"sector": "agri_total"}, {"sector": "total"}], [{"sector": "agri_total"}]]


def test_sector_columns_ignore_the_dead_column_between_every_pair(tmp_path):
    """QNBFB and VAKBN print TL / (%) / FC / (%) twice with a dead column
    between the pairs; the capture parks stray cells there, so the column
    is live in a fifth of the rows and the eight-column shape is hidden
    until the model retries on a half-of-the-rows reading."""
    SE = _load("build_sector_full")
    rows = [
        ("Agricultural", [598735.0, 0.46, None, 75073.0, 0.06, None, 502615.0, 0.44, None, 169239.0, 0.15]),
        ("Farming and Raising Livestock", [443123.0, 0.34, None, 75073.0, 0.06, None, 356405.0, 0.31, None, 169239.0, 0.15]),
        ("Forestry", [9703.0, 0.01, None, "-", 0.0, None, 10413.0, 0.01, None, "-", "-"]),
        ("Fishing", [145909.0, 0.11, None, "-", 0.0, None, 135797.0, 0.12, None, "-", "-"]),
        ("Manufacturing", [43007140.0, 32.99, 1.0, 61017018.0, 52.72, None, 36221373.0, 31.37, None, 55487095.0, 50.36]),
        ("Mining and Quarrying", [969409.0, 0.74, None, 8007.0, 0.01, None, 849874.0, 0.74, None, 57167.0, 0.05]),
        ("Production", [37109339.0, 28.47, None, 60298291.0, 52.1, 2.0, 31624534.0, 27.39, None, 54849294.0, 49.78]),
        ("Electricity, Gas and Water", [4928392.0, 3.78, None, 710720.0, 0.61, None, 3746965.0, 3.24, None, 580634.0, 0.53]),
        ("Construction", [29418784.0, 22.57, None, 23394806.0, 20.21, None, 28215225.0, 24.43, None, 23868664.0, 21.66]),
        ("Services", [55626655.0, 42.68, None, 27344854.0, 23.63, None, 48974593.0, 42.41, None, 26974995.0, 24.48]),
        ("Wholesale and Retail Trade", [55626655.0, 42.68, None, 27344854.0, 23.63, None, 48974593.0, 42.41, None, 26974995.0, 24.48]),
        ("Other", [1300000.0, 1.0, None, 3000000.0, 2.59, None, 1200000.0, 1.04, None, 2500000.0, 2.27]),
        ("Total", [130351314.0, 100.0, None, 115731751.0, 100.0, None, 115107806.0, 100.0, None, 115000993.0, 100.0]),
    ]
    db = _db(tmp_path, [(88, 1, "bin", rows)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?, heading=?",
               ('["TL","Current (%)","Period","FC","","","TL","Prior (%)","Period","FC",""]',
                "Current Period Prior Period TL (%) FC (%) TL (%) FC (%)"))
    db.commit()
    grid = __import__("json").loads(db.execute("SELECT grid_json FROM bank_audit_document_tables").fetchone()[0])
    fam, cols = SE.column_model(grid, __import__("json").loads(
        db.execute("SELECT col_labels_json FROM bank_audit_document_tables").fetchone()[0]),
        "Current Period Prior Period TL (%) FC (%) TL (%) FC (%)")
    assert fam == "loans_currency"
    assert [c for _i, c, _l in cols] == ["tl", "tl_pct", "fc", "fc_pct",
                                         "tl_prior", "tl_pct_prior", "fc_prior", "fc_pct_prior"]
    assert [i for i, _c, _l in cols] == [0, 1, 3, 4, 6, 7, 9, 10]


def test_npl_by_borrower_periods_classes_and_net_identity(tmp_path):
    NB = _load("build_npl_by_borrower_full")
    grid = [
        ("Cari Dönem (Net): 31 Aralık", [None, None, None]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [6145603.0, 16557226.0, 15150492.0]),
        ("Karşılık Tutarı (-)", [3296993.0, 9305929.0, 9555483.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [2848610.0, 7251297.0, 5595009.0]),
        ("Bankalar (Brüt)", ["-", "-", "-"]),
        ("Karşılık Tutarı (-)", ["-", "-", "-"]),
        ("Bankalar (Net)", ["-", "-", "-"]),
        ("Önceki Dönem (Net): 31 Aralık", [None, None, None]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [100.0, 200.0, 300.0]),
        ("Karşılık Tutarı (-)", [10.0, 20.0, 30.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [90.0, 180.0, 999.0]),
    ]
    movement = [  # the NPL movement table must not be taken for this note
        ("Önceki Dönem Sonu Bakiyesi", [1.0, 2.0, 3.0]), ("Dönem İçinde İntikal (+)", [1.0, 1.0, 1.0]),
        ("Diğer Donuk Alacak Hesaplarından Giriş (+)", [None, 1.0, 1.0]), ("Dönem İçinde Tahsilat (-)", [1.0, 1.0, 1.0]),
        ("Dönem Sonu Bakiyesi", [1.0, 3.0, 4.0]), ("Karşılık (-)", [1.0, 1.0, 1.0]), ("Bilançodaki Net Bakiyesi", [0.0, 2.0, 3.0]),
    ]
    db = _db(tmp_path, [(102, 1, "bin", grid), (61, 1, "bin", movement)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?", (json.dumps(["III. Grup Krediler", "IV. Grup Krediler", "V. Grup Krediler"]),))
    db.commit()
    got = NB.assemble(db, KEY)
    assert len(got["instances"]) == 1
    cur, pri = got["instances"][0]
    assert cur["label"] == "current" and pri["label"] == "prior"
    assert NB._identity_holds(cur["rows"], got["step"]) and not NB._identity_holds(pri["rows"], got["step"])
    prov = [x for x in cur["rows"] if x["measure"] == "provision"]
    assert prov[0]["class"] == "individuals_corporates" and prov[1]["class"] == "banks"


def test_npl_by_borrower_inline_period_head_date_heads_and_lead_columns(tmp_path):
    NB = _load("build_npl_by_borrower_full")
    # TEB: no current head, the prior head an inline (valueless) row;
    # AKTIF: date heads with their digits in a lead column; YKBNK: an empty
    # lead column, "Loans granted to real persons and corporate entities"
    teb = [
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [3346.0, 5549.0, 6165.0]),
        ("Karşılık Tutarı (-)", [2520.0, 4160.0, 3928.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [826.0, 1389.0, 2237.0]),
        ("Bankalar (Brüt)", ["-", "-", "-"]),
        ("Karşılık Tutarı (-)", ["-", "-", "-"]),
        ("Bankalar (Net)", ["-", "-", "-"]),
        ("Önceki Dönem (Net)", [None, None, None]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [2441.0, 4910.0, 3549.0]),
        ("Karşılık Tutarı (-)", [2139.0, 3240.0, 2096.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [302.0, 1670.0, 1453.0]),
    ]
    aktif = [
        ("31 Mart 2026 (Net)", [31.0, None, None, None]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [None, 399155.0, 601073.0, 724960.0]),
        ("Karşılık Tutarı (-)", [None, 120358.0, 250187.0, 496790.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [None, 278797.0, 350886.0, 228170.0]),
        ("Bankalar (Brüt)", [None, "-", "-", "-"]),
        ("Karşılık Tutarı (-)", [None, "-", "-", "-"]),
        ("Bankalar (Net)", [None, "-", "-", "-"]),
        ("31 Aralık 2025 (Net)", [31.0, None, None, None]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt)", [None, 372899.0, 585288.0, 464804.0]),
        ("Karşılık Tutarı (-)", [None, 100000.0, 200000.0, 400000.0]),
        ("Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net)", [None, 272899.0, 385288.0, 64804.0]),
    ]
    ykbnk = [
        ("Current Period (Net)", [None, 7441.0, 11798.0, 14752.0]),
        ("Loans Granted to Real Persons and Corporate Entities (Gross)", [None, 16534.0, 31241.0, 40261.0]),
        ("Provision Amount (-)", [None, 9093.0, 19443.0, 25509.0]),
        ("Loans Granted to Real Persons and Corporate Entities (Net)", [None, 7441.0, 11798.0, 14752.0]),
        ("Banks (Gross)", [None, 11.0, "-", 1.0]),
        ("Provision Amount (-)", [None, 11.0, "-", 1.0]),
        ("Banks (Net)", [None, "-", "-", "-"]),
        ("", [66.0, None, None, None]),
        ("Prior Period (Net)", [None, 6362.0, 9482.0, 11187.0]),
        ("Loans Granted to Real Persons and Corporate Entities (Gross)", [None, 15261.0, 20773.0, 31911.0]),
        ("Provision Amount (-)", [None, 8899.0, 11291.0, 20724.0]),
        ("Loans Granted to Real Persons and Corporate Entities (Net)", [None, 6362.0, 9482.0, 11187.0]),
    ]
    db = _db(tmp_path, [(73, 1, "bin", teb), (60, 1, "bin", aktif), (71, 3, "bin", ykbnk)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?, grid_json=replace(grid_json, ?, ?)",
               (json.dumps(["III. Grup Krediler", "IV. Grup Krediler", "V. Grup Krediler"]),
                '"label": "Önceki Dönem (Net)", "cells": [null, null, null]}',
                '"label": "Önceki Dönem (Net)", "cells": [null, null, null], "inline": true}'))
    db.commit()
    got = NB.assemble(db, KEY)
    assert [[(p["label"], NB._identity_holds(p["rows"], got["step"])) for p in inst] for inst in got["instances"]] == [
        [("current", True), ("prior", True)], [("current", True), ("prior", True)], [("current", True), ("prior", True)]]
    firsts = {next(x for x in inst[0]["rows"] if x["class"])["cells"]["group_iii"]: inst for inst in got["instances"]}
    aktif_cur = [x for x in firsts[399155.0][0]["rows"] if x["class"]]
    assert aktif_cur[0]["class"] == "individuals_corporates" and aktif_cur[0]["cells"]["group_v"] == 724960.0
    yk_prior = [x for x in firsts[16534.0][1]["rows"] if x["class"]]
    assert yk_prior[0]["cells"]["group_iv"] == 20773.0 and yk_prior[1]["measure"] == "provision"


def test_risk_group_pairing_by_opening_closing_handoff(tmp_path):
    RG = _load("build_risk_group_full")
    cur = [("Dönem Başı Bakiyesi", ["-", "-", 18578260.0, 7976674.0, 101792.0, 4532.0]),
           ("Dönem Sonu Bakiyesi", ["-", "-", 28929188.0, 11740072.0, 90661.0, 14957.0]),
           ("Alınan Faiz ve Komisyon Gelirleri", ["-", "-", 2800443.0, 47605.0, 7218.0, 293.0])]
    pri = [("Dönem Başı Bakiyesi", ["-", "-", 11503560.0, 4863943.0, 132122.0, 140263.0]),
           ("Dönem Sonu Bakiyesi", ["-", "-", 18578260.0, 7976674.0, 101792.0, 4532.0]),
           ("Alınan Faiz ve Komisyon Gelirleri", ["-", "-", 2714832.0, 41777.0, 11594.0, 1120.0])]
    bad = [("Dönem Başı Bakiyesi", ["-", "-", 1.0, 2.0, 3.0, 4.0]),
           ("Dönem Sonu Bakiyesi", ["-", "-", 5.0, 6.0, 7.0, 8.0]),
           ("Alınan Faiz ve Komisyon Gelirleri", ["-", "-", 1.0, 1.0, 1.0, 1.0])]
    dep = [("Dönem Başı", [10.0, 20.0, 30.0]), ("Dönem Sonu", [11.0, 21.0, 31.0]), ("Mevduat Faiz Gideri", [1.0, 2.0, 3.0])]
    db = _db(tmp_path, [(127, 1, "bin", cur), (127, 2, "bin", pri), (128, 1, "bin", dep)])
    db.execute("UPDATE bank_audit_document_tables SET heading='Grubun Dahil Olduğu Risk Grubu Nakdi G.Nakdi'")
    db.commit()
    got = RG.assemble(db, KEY)
    kept, refused = RG._pair(got["instances"], got["step"])
    assert refused == 0
    assert [(i["measure"], lab, c) for i, lab, c in kept] == [
        ("loans", "current", "paired"), ("loans", "prior", "paired"), ("deposits", "current", "unpaired")]
    assert kept[0][0]["rows"][1]["cells"][2] == (("shareholders", "cash"), 28929188.0)
    db2 = _db(tmp_path / "b", [(127, 1, "bin", cur), (127, 2, "bin", bad)]) if (tmp_path / "b").mkdir() is None else None
    db2.execute("UPDATE bank_audit_document_tables SET heading='Risk Grubu Nakdi G.Nakdi'")
    db2.commit()
    got2 = RG.assemble(db2, KEY)
    assert RG._pair(got2["instances"], got2["step"])[1] == 2


def test_deposit_maturity_participation_template(tmp_path):
    DM = _load("build_deposit_maturity_full")
    grid = [
        ("Up to 1", [None, 1.0, 3.0, 6.0, 9.0, 1.0, None, "on", None]),
        ("I. Özel cari hesabı gerçek kişi ticari olmayan-TP", [100.0, "-", "-", "-", "-", "-", "-", "-", 100.0]),
        ("II. Katılma hesapları gerçek kişi ticari olmayan-TP", ["-", 10.0, 20.0, 5.0, "-", 15.0, 6.0, 1.0, 57.0]),
        ("III. Özel cari hesap diğer-TP", [40.0, "-", "-", "-", "-", "-", "-", "-", 40.0]),
        ("Resmi kuruluşlar", [2.0, "-", "-", "-", "-", "-", "-", "-", 2.0]),
        ("Ticari kuruluşlar", [38.0, "-", "-", "-", "-", "-", "-", "-", 38.0]),
        ("IV. Katılma hesapları-TP", ["-", 18.0, 15.0, 1.0, "-", 11.0, 1.0, "-", 46.0]),
        ("Toplam(**)", [140.0, 28.0, 35.0, 6.0, "-", 26.0, 7.0, 1.0, 243.0]),
    ]
    db = _db(tmp_path, [(106, 1, "bin", grid)])
    db.execute("UPDATE bank_audit_document_tables SET col_labels_json=?",
               (json.dumps(["Vadesiz", "aya kadar", "aya kadar", "aya kadar", "aya kadar", "yıla kadar", "yıl ve üstü", "katılma", "Toplam(*)"]),))
    db.commit()
    got = DM.assemble(db, KEY)
    inst = got["instances"][0]
    assert DM._identity_holds(inst["rows"], got["step"])
    bands = [b for b, _v in inst["rows"][0]["cells"]]
    assert bands == ["demand", "m1", "m3", "m6", "m9", "y1", "y1_plus", "accumulating", "total"]
    roles = {x["role"] for x in inst["rows"]}
    assert {"current_real_tl", "participation_real_tl", "current_other_tl", "participation_other_tl",
            "public_institutions", "commercial_institutions", "total"} <= roles


def test_securities_issued_refuses_a_pledged_asset_note():
    """ZIRAAT's "Teminata Verilen/Bloke İtfa Edilmiş Maliyeti Üzerinden
    Değerlenen Finansal Varlıklar" lists the issued note's rows word for
    word, and "Menkul" among those labels confirmed the family — so an asset
    note was stored as a liability, and both the consolidated and the
    unconsolidated filing carried the same 220,122,149."""
    TF = _load("build_tl_fc_note_full")
    grid = [{"label": "Bono", "cells": ["-", "-", "-", "-"]},
            {"label": "Tahvil ve Benzeri Menkul Değerler",
             "cells": [151047745.0, 69074404.0, 143859019.0, 62284619.0]},
            {"label": "Diğer", "cells": ["-", "-", "-", "-"]},
            {"label": "Toplam", "cells": [151047745.0, 69074404.0, 143859019.0, 62284619.0]}]
    pledged = "Teminata Verilen/Bloke İtfa Edilmiş Maliyeti Üzerinden Değerlenen Finansal Varlıklar"
    item = "Konsolide Bilançonun aktif hesaplarına ilişkin açıklama ve dipnotlar"
    assert TF.family_of(grid, pledged, item) is None
    # the same rows under the issued note's own title are the real thing
    assert TF.family_of(grid, "d. İhraç edilen menkul kıymetlere ait bilgiler:", item) == "securities_issued"
    # and with no heading at all the row labels still carry it -- 129
    # instances that agree with the narrow lane rest on that, so it stays
    assert TF.family_of(grid, "", item) == "securities_issued"


def test_securities_issued_titled_block_is_instance_zero():
    """BURGAN prints three tables with the issued note's rows; only one
    carries the title, and only that one totals the balance sheet's figure.
    Both readings are kept — the titled one is instance 0, which is the
    instance every consumer takes."""
    TF = _load("build_tl_fc_note_full")
    item = "Faaliyet bölümlerine ilişkin açıklamalar......................."
    assert TF.heading_confirms("securities_issued", "d. İhraç edilen menkul kıymetlere ait bilgiler:", item)
    assert not TF.heading_confirms("securities_issued", "", item)
    assert not TF.heading_confirms("securities_issued", None, item)
    # a heading that merely repeats the contents line is not a title
    assert not TF.heading_confirms("securities_issued", item, item)


def test_ov1_stops_at_row_25_when_another_table_shares_the_block(tmp_path):
    """YKBNK prints the IRB RWA movement table under OV1, in the same block,
    its rows numbered 1-9 again in columns of their own. Those columns
    entered the block's column model and the total row was read one place
    over: 2024Q3 came out as 1,115,540,871 — YKBNK's own prior figure —
    against a minimum capital of 119,803,421, which is 8% of 1,497,542,746."""
    RW = _load("build_rwa_full")
    form = [("1 Credit risk (excluding counterparty credit risk)",
             [1.0, 1276559025.0, 976167760.0, None, 102124722.0]),
            ("16 Market risk", [16.0, 19347945.0, 14512699.0, None, 1547836.0]),
            ("19 Operational risk", [19.0, 169906912.0, 99403270.0, None, 13592553.0]),
            ("23 Amounts below the thresholds for deduction",
             [23.0, 17600910.0, 11159544.0, None, 1408073.0]),
            ("24 Floor adjustment", [24.0, "-", "-", None, "-"]),
            ("25 TOTAL (1+4+7+8+9+10+11+12+16+19+23+24)",
             [25.0, 1497542746.0, 1115540871.0, None, 119803421.0])]
    movement = [("2.1.2. RWA Movement Table Under IRB Approach", [None, None, None, None, None]),
                ("1 Previous Period Closing Amount", [1.0, None, None, 849958363.0, 556692068.0]),
                ("2 Changes in Volume", [2.0, None, None, 290697671.0, 215651230.0]),
                ("9 Current Period Closing Amount", [9.0, None, None, 1060662626.0, 849958363.0])]
    grid = [{"label": lab, "cells": c} for lab, c in form + movement]
    assert [r["label"][:2] for r in RW._cut_after_the_form(grid)] == \
        ["1 ", "16", "19", "23", "24", "25"]
    # a tail that opens on the form's own row 1 is a second copy: left alone
    second = grid[:6] + [{"label": lab, "cells": c} for lab, c in form]
    assert len(RW._cut_after_the_form(second)) == len(second)

    db = _db(tmp_path, [(41, 1, "bin", form + movement)])
    got = RW.assemble(db, KEY)
    total = [r for r in got["instances"]["current"] if r["template_row"] == 25][0]
    assert total["rwa"] == 1497542746.0 and total["rwa_prior"] == 1115540871.0
    assert total["min_capital"] == 119803421.0
    assert abs(total["min_capital"] / total["rwa"] - 0.08) <= 0.002    # the form's own ratio


def test_securities_portfolio_from_the_title_line_inside_the_block():
    """ALNTF prints "e. Gerçeğe uygun değer farkı diğer kapsamlı gelire
    yansıtılan..." as a valueless row two lines above its own table, in a
    block whose heading belongs to the country table above it. The ledger
    lookback cannot see that line — it lives in the tables layer, not the
    lines layer — so it reached past it to the FVTPL note and filed
    7,919,060, the balance sheet's FVOCI line to the lira, as fvtpl."""
    SC = _load("build_securities_full")
    grid = [{"label": "AB Ülkeleri", "cells": [None, 609909.0, 304754.0]},
            {"label": "Toplam", "cells": [None, 1694092.0, 1939220.0]},
            {"label": "d. Gerçeğe uygun değer farkı diğer kapsamlı gelire yansıtılan finansal "
                      "varlıklardan teminata verilen/bloke edilenlere ilişkin bilgiler",
             "cells": [None, None, None]},
            {"label": "e. Gerçeğe uygun değer farkı diğer kapsamlı gelire yansıtılan finansal "
                      "varlıklara ilişkin bilgiler", "cells": [None, None, None]},
            {"label": "Borçlanma Senetleri", "cells": [None, 8182536.0, 7364244.0]},
            {"label": "Borsada İşlem Gören", "cells": [None, 8067345.0, 7211226.0]},
            {"label": "Hisse Senetleri", "cells": [None, 16504.0, 13782.0]},
            {"label": "Değer Azalma Karşılığı (-)", "cells": [None, 279980.0, 404032.0]},
            {"label": "Toplam", "cells": [None, 7919060.0, 6973994.0]}]
    assert SC.portfolio_from_grid(grid) == "fvoci"
    # the block heading names no portfolio at all -- that is why the grid is
    # consulted in the first place
    assert SC.portfolio_of("Serbest Tutar Serbest Olmayan Tutar",
                           "Aktif kalemlere ilişkin açıklama ve dipnotlar") == "unknown"
    # a title BELOW the table does not claim it
    below = grid[:2] + grid[4:] + [{"label": "f. İtfa edilmiş maliyeti üzerinden değerlenen finansal "
                                             "varlıklara ilişkin bilgiler", "cells": [None, None, None]}]
    assert SC.portfolio_from_grid(below) == "unknown"


def test_rowno_reads_a_number_welded_to_its_label_only_when_asked():
    """TSKB's capture prints "21TOTAL HQLA STOCK" with an empty number
    column. Opt-in, because the same shape elsewhere in the corpus is a
    maturity band, a date or a footnote."""
    def r(label):
        return {"cells": [None], "label": label}
    for label, n in (("21TOTAL HQLA STOCK", 21), ("17Secured Lending Transactions", 17),
                     ("23LIQUIDITY COVERAGE RATIO (%)", 23), ("16TOPLAM NAKİT ÇIKIŞLARI", 16),
                     ("2Gerçek kişi mevduat ve perakende mevduat", 2), ("9Teminatlı borçlar", 9)):
        assert NT.rowno(r(label), 23, glued=True) == n, label
        assert NT.rowno(r(label), 23) is None, label          # off by default
    # a maturity band, a date and an out-of-range number stay unread
    assert NT.rowno(r("1Ay"), 23, glued=True) is None
    assert NT.rowno(r("31Aralık 2024"), 40, glued=True) is None
    assert NT.rowno(r("24TOTAL"), 23, glued=True) is None     # past max_row
    # the SPACED date has always read as row 31 through the older prefix
    # rule; `glued` neither causes that nor fixes it
    assert NT.rowno(r("31 Aralık 2024"), 40) == 31
    # the number comes off the label the same way
    assert NT.strip_rowno("21TOTAL HQLA STOCK", True) == "TOTAL HQLA STOCK"
    assert NT.strip_rowno("21TOTAL HQLA STOCK") == "21TOTAL HQLA STOCK"
    assert NT.strip_rowno("21 TOTAL HQLA STOCK") == "TOTAL HQLA STOCK"
    assert NT.strip_rowno("31Aralık 2024", True) == "31Aralık 2024"


def test_lcr_keeps_the_current_table_when_its_numbers_are_welded(tmp_path):
    """TSKB 2024Q1 prints the current table on page 57 and the prior one on
    58. The current table's numbers are welded to its labels from row 15 on,
    so it stopped short of `bottom_row` and was dropped — and the prior copy
    became 'current', reporting last year's 829% for four quarters running
    against the narrow lane's 578%."""
    LC = _load("build_lcr_full")

    def table(rows, weld_from):
        out = []
        for n, label, w_total, w_fc in rows:
            if n >= weld_from:
                out.append((f"{n}{label}", [None, "-", "-", w_total, w_fc]))
            else:
                out.append((f"{n} {label}", [float(n), "-", "-", w_total, w_fc]))
        return out

    body = [(1, "High quality liquid assets", 17189886.0, 10855867.0),
            (2, "Retail and Customers Deposits", 1.0, 1.0),
            (16, "TOTAL CASH OUTFLOWS", 3000000.0, 2500000.0),
            (20, "TOTAL CASH INFLOWS", 15120609.0, 12434008.0),
            (21, "TOTAL HQLA STOCK", 17189886.0, 10855867.0),
            (22, "TOTAL NET CASH OUTFLOWS", 2974814.0, 2489915.0),
            (23, "LIQUIDITY COVERAGE RATIO (%)", 578.0, 436.0)]
    prior = [(1, "High quality liquid assets", 16966338.0, 11220341.0),
             (2, "Retail and Customers Deposits", 1.0, 1.0),
             (16, "TOTAL CASH OUTFLOWS", 3000000.0, 2500000.0),
             (20, "TOTAL CASH INFLOWS", 16832353.0, 11613207.0),
             (21, "TOTAL HQLA STOCK", 16966338.0, 11220341.0),
             (22, "TOTAL NET CASH OUTFLOWS", 2045519.0, 1612019.0),
             (23, "LIQUIDITY COVERAGE RATIO (%)", 829.0, 696.0)]
    db = _db(tmp_path, [(57, 2, "bin", table(body, 15)), (58, 1, "bin", table(prior, 99))])
    got = LC.assemble(db, KEY)
    ratio = {lab: [x for x in inst if x["template_row"] == 23][0]["w_total"]
             for lab, inst in got["instances"].items()}
    assert ratio == {"current": 578.0, "prior": 829.0}
    cur = [x for x in got["instances"]["current"] if x["template_row"] == 21][0]
    assert cur["page"] == 57 and cur["label"] == "TOTAL HQLA STOCK"


def test_npl_movement_signed_page_with_a_child_that_carries_its_own_minus(tmp_path):
    """GARAN prints "Other (***)" under the debt sale as -123,549 in a
    filing whose sale reads +3,726 and in one reading -259,367 — the same
    number, both ways round. So the residual of the children over their head
    has no fixed direction, and normalising a signed page must not assume
    one: the group still has to close, either way."""
    NM = _load("build_npl_movement_full")
    signed = [
        ("Balances at End of Prior Period", [None, None, 14626239.0]),
        ("Additions during the Period (+)", [None, None, 7772993.0]),
        ("Transfer from Other NPL Categories (+)", [None, None, 2126311.0]),
        ("Transfer to Other NPL Categories (-)", [None, None, -25178.0]),
        ("Collections during the Period (-)", [None, None, -1848826.0]),
        ("Write down /Write-offs (-)(*)", [None, None, -8146761.0]),
        ("Debt Sale (-)(**)", [None, None, -259367.0]),
        ("Corporate and Commercial Loans", [None, None, -58267.0]),
        ("Retail Loans", [None, None, -156028.0]),
        ("Credit Cards", [None, None, -45072.0]),
        ("Other (***)", [None, None, -123549.0]),
        ("Foreign Currency Differences", [None, None, 1851835.0]),
        ("Balances at End of Period", [None, None, 15973697.0]),
        ("Provisions (-)", [None, None, -11720790.0]),
        ("Net Balance on Balance Sheet", [None, None, 4252907.0]),
    ]
    db = _db(tmp_path, [(90, 1, "bin", signed)])
    got = NM.assemble(db, KEY)
    rows = got["instances"][0]["rows"]
    assert NM._convention(rows, got["step"]) == "signed"
    NM._to_labelled(rows)
    # the children follow their head: sold_retail is an outflow too
    by = {x["role"]: x["cells"]["group_v"] for x in rows if x["role"]}
    assert by["collections"] == 1848826.0 and by["sold"] == 259367.0
    assert by["sold_retail"] == 156028.0 and by["sold_other"] == 123549.0
    assert by["opening"] == 14626239.0 and by["fx_difference"] == 1851835.0
    # and it lands back on the labelled convention -- the builder refuses
    # the instance if it does not
    assert NM._convention(rows, got["step"]) == "labelled"


def test_npl_movement_outflow_children_follow_their_head():
    NM = _load("build_npl_movement_full")
    out = {"collections", "transfers_out", "write_offs", "sold", "to_performing",
           "sold_retail", "write_offs_corporate", "transfers_out_cards"}
    for role in out:
        assert NM._is_outflow({"role": role, "label": ""}), role
    for role in ("opening", "additions", "transfers_in", "closing", "provision", "net",
                 "fx_difference", "additions_retail"):
        assert not NM._is_outflow({"role": role, "label": ""}), role
    # an unregistered row follows the "(-)" its own label carries
    assert NM._is_outflow({"role": None, "label": "Diğer donuk alacak hesaplarından çıkış (-)"})
    assert not NM._is_outflow({"role": None, "label": "Diğer donuk alacak hesaplarına giriş (+)"})


def test_npl_movement_split_blocks_sub_rows_signed_and_date_labelled_variants(tmp_path):
    NM = _load("build_npl_movement_full")
    # ISCTR: every movement split by loan type, the closing in the next block
    isctr_head = [
        ("Prior Period Ending Balance", [100.0, 50.0, 200.0]),
        ("Corporate and Commercial Loans", [60.0, 30.0, 150.0]),
        ("Retail Loans", [40.0, 20.0, 50.0]),
        ("Additions (+)", [30.0, 10.0, 5.0]),
        ("Corporate and Commercial Loans", [20.0, 5.0, 5.0]),
        ("Retail Loans", [10.0, 5.0, None]),
        ("Collections (-)", [10.0, 5.0, 20.0]),
        ("Corporate and Commercial Loans", [10.0, 5.0, 20.0]),
    ]
    isctr_tail = [
        ("Current Period Ending Balance", [120.0, 55.0, 185.0]),
        ("Specific Provisions (-)", [70.0, 40.0, 170.0]),
        ("Net Balance on Balance Sheet", [50.0, 15.0, 15.0]),
    ]
    # TFKB: deductions printed negative, an unregistered accruals row
    tfkb = [
        ("Önceki Dönem Sonu Bakiyesi", [100.0, 50.0, 200.0]),
        ("Dönem İçinde İntikal (+) (*)", [30.0, 10.0, 5.0]),
        ("Dönem İçinde Tahsilat (-)", [-10.0, -5.0, -20.0]),
        ("Aktiften Silinen (-) (**)", [-2.0, "-", -3.0]),
        ("Bireysel Krediler", [-2.0, "-", -3.0]),
        ("Donuk Alacak Reeskontları", [1.0, 2.0, 3.0]),
        ("Dönem Sonu Bakiyesi", [119.0, 57.0, 185.0]),
        ("Özel Karşılık (-)", [-70.0, -40.0, -170.0]),
        ("Bilançodaki Net Bakiyesi", [49.0, 17.0, 15.0]),
    ]
    # ALNTF: date-labelled opening and closing, the digits in two lead columns
    alntf = [
        ("31 Aralık 2023", [31.0, 2023.0, 100.0, 50.0, 200.0]),
        ("Dönem İçinde İntikal (+)", [None, None, 30.0, 10.0, 5.0]),
        ("Dönem İçinde Tahsilat (-)", [None, None, 10.0, 5.0, 20.0]),
        ("Kayıttan Düşülen (-)", [None, None, "-", "-", "-"]),
        ("Satılan (-)", [None, None, "-", "-", "-"]),
        ("31 Aralık 2024 Bakiyesi", [31.0, 2024.0, 120.0, 55.0, 185.0]),
        ("Karşılık (-)", [None, None, 70.0, 40.0, 170.0]),
        ("Bilançodaki Net Bakiyesi", [None, None, 50.0, 15.0, 15.0]),
    ]
    # GARAN: "Other (****)" under the sale row is a movement of its own;
    # HALKB-style stacking under a valueless "Prior Period" header row
    garan = [
        ("Balances at End of Prior Period", [100.0, None, None]),
        ("Additions during the Period (+)", [30.0, None, None]),
        ("Collections during the Period (-)", [5.0, None, None]),
        ("Debt Sale (-) (***)", [10.0, None, None]),
        ("Corporate and Commercial Loans", [6.0, None, None]),
        ("Retail Loans", [4.0, None, None]),
        ("Other (****)", [-3.0, None, None]),
        ("Balances at End of Period", [112.0, None, None]),
        ("Provisions (-)", [50.0, None, None]),
        ("Net Balance on Balance Sheet", [62.0, None, None]),
        ("Prior Period", [None, None, None]),
        ("Balances at End of Prior Period", [80.0, None, None]),
        ("Additions during the Period (+)", [25.0, None, None]),
        ("Collections during the Period (-)", [5.0, None, None]),
        ("Balances at End of Period", [100.0, None, None]),
        ("Provisions (-)", [40.0, None, None]),
        ("Net Balance on Balance Sheet", [60.0, None, None]),
    ]
    db = _db(tmp_path, [(61, 1, "bin", isctr_head), (61, 2, "bin", isctr_tail), (70, 1, "bin", tfkb),
                        (80, 1, "bin", alntf), (90, 1, "bin", garan)])
    got = NM.assemble(db, KEY)
    inst = got["instances"]
    assert [(i["hint"], NM._convention(i["rows"], got["step"])) for i in inst] == [
        (None, "labelled"), (None, "signed"), (None, "labelled"), (None, "labelled"), ("prior", "labelled")]
    # TFKB prints the outflows already negative; normalising flips them to
    # the magnitude every other filing prints, so `collections` means one
    # thing across the lane
    tfkb_rows = inst[1]["rows"]
    before = {x["role"]: dict(x["cells"]) for x in tfkb_rows if x["role"]}
    NM._to_labelled(tfkb_rows)
    after = {x["role"]: x["cells"] for x in tfkb_rows if x["role"]}
    for role in ("collections", "transfers_out", "write_offs"):
        if role in before and before[role]["group_iii"] is not None:
            assert after[role]["group_iii"] == -before[role]["group_iii"]
    assert after["opening"] == before["opening"] and after["closing"] == before["closing"]
    assert NM._convention(tfkb_rows, got["step"]) == "labelled"   # and it still closes
    roles = [x["role"] for x in inst[0]["rows"]]
    assert roles[:6] == ["opening", "opening_corporate", "opening_retail", "additions", "additions_corporate",
                         "additions_retail"]
    assert roles[-3:] == ["closing", "provision", "net"] and inst[0]["rows"][-1]["block_id"] == 2
    tf = {x["role"]: x["cells"] for x in inst[1]["rows"] if x["role"]}
    # normalised above: TFKB's signed page now reads like every other one
    assert tf["write_offs_retail"]["group_v"] == 3.0 and tf["collections"]["group_iii"] == 10.0
    al = {x["role"]: x["cells"] for x in inst[2]["rows"] if x["role"]}
    assert al["opening"]["group_iii"] == 100.0 and al["closing"]["group_v"] == 185.0
    assert len(inst[3]["rows"]) == 10 and len(inst[4]["rows"]) == 7


def test_stage_movement_no_total_side_by_side_subtotal_head_and_year_column(tmp_path):
    SM = _load("build_stage_movement_full")
    # VAKBN: three stages, no total, the stage header in the grid, the
    # prior period stacked below; deductions labelled "(-)", the stage-3
    # "çıkanlar" printed negative (a reversal, subtracted as printed)
    vakbn = [
        ("Cari Dönem 31 Aralık 2024", [None, 1.0, "1. Aşama", 2.0, "2. Aşama", 3.0, "3. Aşama"]),
        ("Dönem Başı Karşılık Bakiyesi", [None, None, 1000.0, None, 500.0, None, 300.0]),
        ("Dönem içi ilave karşılıklar", [None, None, 200.0, None, 100.0, None, 50.0]),
        ("Dönem içi çıkanlar (-)", [None, None, 100.0, None, 50.0, None, -10.0]),
        ("1. Aşamaya transfer", [1.0, None, 20.0, None, -20.0, None, None]),
        ("Dönem Sonu Karşılık Bakiyesi", [None, None, 1120.0, None, 530.0, None, 360.0]),
        ("Önceki Dönem 31 Aralık 2023", [None, 1.0, "1. Aşama", 2.0, "2. Aşama", 3.0, "3. Aşama"]),
        ("Dönem Başı Karşılık Bakiyesi", [None, None, 800.0, None, 400.0, None, 200.0]),
        ("Dönem içi ilave karşılıklar", [None, None, 300.0, None, 150.0, None, 100.0]),
        ("Dönem içi çıkanlar (-)", [None, None, 100.0, None, 50.0, None, None]),
        ("Dönem Sonu Karşılık Bakiyesi", [None, None, 1000.0, None, 500.0, None, 300.0]),
    ]
    # ISCTR: current and prior side by side, no totals, the stage digits of
    # "Transfer to Stage N" in the first cell, the header digits in a row
    isctr = [
        ("Stage 1", [None, 1.0, 2.0, 3.0, None, None, None]),
        ("Provisions beginning of the period", [None, 100.0, 50.0, 30.0, 80.0, 40.0, 20.0]),
        ("Additional provisions within the period", [None, 40.0, 20.0, 10.0, 30.0, 15.0, 12.0]),
        ("Transfers within the period", [None, -10.0, -5.0, -2.0, -8.0, -4.0, -1.0]),
        ("Transfer to Stage", [1.0, 5.0, -5.0, None, 4.0, -4.0, None]),
        ("Transfer to Stage", [2.0, -3.0, 3.0, None, -2.0, 2.0, None]),
        ("Transfer to Stage Currency Exchange Difference", [3.0, 8.0, 5.0, 6.0, 4.0, 7.0, 9.0]),
        ("Provisions at the end of the period", [None, 140.0, 68.0, 44.0, 108.0, 56.0, 40.0]),
    ]
    # DENIZ: under a balance table in the same block, a year column, the
    # "Transferler" head over its three sub-rows, prose below the closing
    deniz = [
        ("Krediler", [None, None, 5000.0, None, 100.0, None, 4000.0, 90.0]),
        ("1. Aşama", [1.0, None, 4000.0, None, 40.0, None, 3000.0, 30.0]),
        ("j. Kredi hareketlerine ilişkin bilgiler", [None, None, None, None, None, None, None, None]),
        ("1. Aşama", [None, None, 1.0, None, 2.0, "2. Aşama", "3.Aşama", "Toplam"]),
        ("Dönem Başı (1 Ocak 2024)", [None, None, None, 3000.0, None, 700.0, 300.0, 4000.0]),
        ("Transferler", [None, None, None, -100.0, None, 60.0, 40.0, "--"]),
        ("1. Aşamaya", [None, 1.0, None, 50.0, None, -50.0, "--", "--"]),
        ("2. Aşamaya", [None, 2.0, None, -120.0, None, 130.0, -10.0, "--"]),
        ("3. Aşamaya", [None, 3.0, None, -30.0, None, -20.0, 50.0, "--"]),
        ("Dönem içinde eklenen krediler", [None, None, None, 1500.0, None, 200.0, 100.0, 1800.0]),
        ("Dönem içinde kapanan krediler", [None, None, None, -500.0, None, -100.0, -50.0, -650.0]),
        ("Kur farkı", [None, None, None, 100.0, None, 40.0, 10.0, 150.0]),
        ("Dönem Sonu (31 Aralık 2024)", [None, None, None, 4000.0, None, 900.0, 400.0, 5300.0]),
        ("Beşinci grup krediler kayıtlardan düşülmüştür", [None, None, None, None, None, None, 31.0, 2024.0]),
    ]
    db = _db(tmp_path, [(56, 1, "bin", vakbn), (113, 1, "bin", isctr), (47, 1, "bin", deniz)])
    db.execute("UPDATE bank_audit_document_tables SET heading=? WHERE page=56",
               ("Kredilere ilişkin beklenen zarar karşılıkları",))
    db.commit()
    got = SM.assemble(db, KEY)
    inst = got["instances"]
    assert [(i["measure"], len(i["rows"]), SM._convention(i["rows"], got["step"]), SM._row_sums_hold(i["rows"], got["step"]))
            for i in inst] == [
        ("gross_loans", 9, "signed", True),
        ("ecl", 5, "deductions_labelled", True), ("ecl", 4, "deductions_labelled", True),
        ("ecl", 7, "signed", True), ("ecl", 7, "signed", True)]
    d = {x["role"]: dict(x["cells"]) for x in inst[0]["rows"] if x["role"]}
    assert d["opening"] == {"stage1": 3000.0, "stage2": 700.0, "stage3": 300.0, "total": 4000.0}
    assert d["transfers_subtotal"]["stage1"] == -100.0 and d["transfer_to_stage2"]["stage3"] == -10.0
    v = {x["role"]: dict(x["cells"]) for x in inst[1]["rows"] if x["role"]}
    assert set(v["opening"]) == {"stage1", "stage2", "stage3"} and v["derecognised"]["stage3"] == -10.0
    i = {x["role"]: dict(x["cells"]) for x in inst[3]["rows"] if x["role"]}
    assert i["transfer_to_stage1"]["stage2"] == -5.0 and i["fx_difference"]["stage3"] == 6.0
    assert dict(inst[4]["rows"][0]["cells"])["stage1"] == 80.0
