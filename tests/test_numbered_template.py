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
    assert [NM._identity_holds(i["rows"], got["step"]) for i in got["instances"]] == [True, True, False]
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
    assert [(i["hint"], NM._identity_holds(i["rows"], got["step"])) for i in inst] == [
        (None, True), (None, True), (None, True), (None, True), ("prior", True)]
    roles = [x["role"] for x in inst[0]["rows"]]
    assert roles[:6] == ["opening", "opening_corporate", "opening_retail", "additions", "additions_corporate",
                         "additions_retail"]
    assert roles[-3:] == ["closing", "provision", "net"] and inst[0]["rows"][-1]["block_id"] == 2
    tf = {x["role"]: x["cells"] for x in inst[1]["rows"] if x["role"]}
    assert tf["write_offs_retail"]["group_v"] == -3.0 and tf["collections"]["group_iii"] == -10.0
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
