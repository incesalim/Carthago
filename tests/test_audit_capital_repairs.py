"""Source-table regressions from the 2026-08-31 capital/liquidity investigation."""
import sqlite3
from pathlib import Path

from src.audit_reports.capital_adequacy import (
    CapitalReport, CapitalRow, _parse_section, _repair_displaced_rows, upsert,
)
from src.audit_reports.liquidity import _scan
from src.audit_reports.schema import DDL, init_schema
from src.audit_reports.units import UnitContext
from src.audit_reports.validator import check_capital


def test_at1_blank_total_requires_explicit_deductions_and_independent_tier1():
    # ICBCT 2026Q2 unconsolidated pp29-30, amounts in millions.
    cur = {"cet1_capital": 5446, "tier1_capital": 10224, "additional_tier1_capital": 0}
    pri = {"cet1_capital": 3789, "tier1_capital": 8055, "additional_tier1_capital": 0}
    rows = ["Additional Tier I Capital before Deductions 4,778 4,266"]
    _repair_displaced_rows(cur, pri, rows)
    assert cur["additional_tier1_capital"] == 0
    rows.append("Total Deductions from Additional Tier I Capital - -")
    _repair_displaced_rows(cur, pri, rows)
    assert (cur["additional_tier1_capital"], pri["additional_tier1_capital"]) == (4778, 4266)
    cur.update(additional_tier1_capital=0, tier1_capital=12000)
    _repair_displaced_rows(cur, pri, rows)
    assert cur["additional_tier1_capital"] == 0


def test_emlak_displaced_own_funds_requires_all_three_ratio_identities():
    # EMLAK 2025Q1 consolidated p34: TC on heading, RWA on TC, RWA blank.
    rows = ["ÖZKAYNAK 28.781.229 22.742.022",
            "Toplam Özkaynak (Ana sermaye ve katkı sermaye toplamı) 125.508.698 97.286.237",
            "Toplam Risk Ağırlıklı Tutarlar"]
    cur = dict(cet1_capital=19850282, tier1_capital=28361476, total_capital=125508698,
               cet1_ratio=15.82, tier1_ratio=22.60, capital_adequacy_ratio=22.93)
    pri = dict(cet1_capital=14683346, tier1_capital=22335431, total_capital=97286237,
               cet1_ratio=15.09, tier1_ratio=22.96, capital_adequacy_ratio=23.38)
    bad = dict(cur, cet1_ratio=18)
    _repair_displaced_rows(bad, {}, rows)
    assert bad["total_capital"] == 125508698 and "total_rwa" not in bad
    _repair_displaced_rows(cur, pri, rows)
    assert (cur["total_capital"], cur["total_rwa"]) == (28781229, 125508698)
    assert (pri["total_capital"], pri["total_rwa"]) == (22742022, 97286237)


def test_isctr_displaced_ratio_rows_are_source_values_not_recalculated():
    # ISCTR 2025Q1 consolidated p33, all five final rows displaced.
    rows = ["Total Risk Weighted Assets 426,340,238 418,631,438",
            "CAPITAL ADEQUACY RATIOS 2,724,016,639 2,306,082,780",
            "Consolidated CET1 Capital Ratio (%)",
            "Consolidated Tier I Capital Ratio (%) 12.45 14.42",
            "Consolidated Capital Adequacy Ratio (%) 13.94 15.25",
            "BUFFERS 15.65 18.15"]
    cur = dict(cet1_capital=339170127, tier1_capital=379729028)
    pri = dict(cet1_capital=332602049, tier1_capital=351750443)
    _repair_displaced_rows(cur, pri, rows)
    assert (cur["total_capital"], cur["total_rwa"], cur["cet1_ratio"],
            cur["tier1_ratio"], cur["capital_adequacy_ratio"]) == (
                426340238, 2724016639, 12.45, 13.94, 15.65)
    assert pri["capital_adequacy_ratio"] == 18.15


def _qnb_rows():
    # QNB 2026Q2 unconsolidated pp45-46, explicit 60+240 and 67+202 deductions.
    return ["Tier II Capital Before Deductions 31,120 25,867",
            "Total Tier II Capital - -",
            "Total Capital (The sum of Tier I Capital and Tier II Capital) 31,120 25,867",
            "Deductions from Total Capital 245,709 216,724",
            "Deductions from Capital Loans granted contrary to the 50th and 51st Article of the Law",
            "Net Book Values of Movables and Immovables Exceeding the Limit Defined in Article 57,",
            "Sale but Retained more than Five Years 60 67",
            "Other items to be defined by the BRSA (-) - -",
            "In transition from Total Core Capital and Supplementary Capital (the capital) to Continue",
            "to Download Components 240 202",
            "Total Capital 245,409 216,455",
            "Total Risk Weighted Amounts 1,578,907 1,191,471"]


def test_qnb_tier2_keeps_gross_disclosure_and_deductions_separate():
    cur = dict(tier1_capital=214589, tier2_capital=0, total_capital=245409)
    pri = dict(tier1_capital=190857, tier2_capital=0, total_capital=216455)
    _repair_displaced_rows(cur, pri, _qnb_rows())
    assert (cur["tier2_capital"], cur["capital_deductions"], cur["total_capital"]) == (31120, 300, 245409)
    assert (pri["tier2_capital"], pri["capital_deductions"], pri["total_capital"]) == (25867, 269, 216455)


def test_deductions_are_never_filled_from_unexplained_residual():
    cur = dict(tier1_capital=214589, tier2_capital=0, total_capital=245309)
    rows = [row.replace("245,409", "245,309") for row in _qnb_rows()]
    _repair_displaced_rows(cur, {}, rows)
    assert "capital_deductions" not in cur
    assert cur["total_capital"] == 245309
    # Even a correct residual must not populate this field without disclosure.
    cur = dict(tier1_capital=214589, tier2_capital=31120, total_capital=245409)
    _repair_displaced_rows(cur, {}, ["Total Tier II Capital 31,120 25,867",
                                    "Total Capital 245,409 216,455"])
    assert "capital_deductions" not in cur


def test_isctr_tier2_displaced_pretotal_uses_explicit_deduction_total():
    # ISCTR 2023Q3 unconsolidated pp30-31: the Tier2 row contains Tier1+Tier2.
    rows = ["Tier II Capital Before Total Deductions 47,976,610 36,235,801",
            "Total Tier II Capital 272,020,659 229,093,344",
            "Total Equity (Total Tier I and Tier II Capital) 1,483 2,650",
            "Deductions from Total Equity (Tier I Capital and Tier II Capital) 1,483 2,650",
            "Total Capital (Total of Tier I Capital and Tier II Capital) 272,019,176 229,090,694",
            "Total Risk Weighted Assets 1,300,917,635 940,288,051"]
    cur = dict(tier1_capital=224044049, tier2_capital=272020659, total_capital=272019176)
    pri = dict(tier1_capital=192857543, tier2_capital=229093344, total_capital=229090694)
    _repair_displaced_rows(cur, pri, rows)
    assert (cur["tier2_capital"], cur["capital_deductions"]) == (47976610, 1483)
    assert (pri["tier2_capital"], pri["capital_deductions"]) == (36235801, 2650)


def test_final_own_funds_wins_over_larger_pretotal_when_deductions_are_disclosed():
    rows = ["Total Tier II Capital 31,949 26,447",
            "Total Capital 246,390 217,152",
            "Deductions from Total Capital 300 269",
            "Total Capital 246,090 216,883",
            "Total Risk Weighted Assets 1,676,462 1,260,068"]
    cur = dict(tier1_capital=214441, tier2_capital=31949, total_capital=246390)
    pri = dict(tier1_capital=190705, tier2_capital=26447, total_capital=217152)
    _repair_displaced_rows(cur, pri, rows)
    assert (cur["total_capital"], cur["capital_deductions"]) == (246090, 300)
    assert (pri["total_capital"], pri["capital_deductions"]) == (216883, 269)


def test_capital_deductions_reconcile_and_remain_strict_when_null_or_wrong():
    row = dict(period_type="current", cet1_capital=190137000, additional_tier1_capital=24452000,
               tier1_capital=214589000, tier2_capital=31120000, total_capital=245409000,
               total_rwa=1578907000, capital_adequacy_ratio=15.54, capital_deductions=300000)
    assert check_capital([row]).failed == 0
    for deduction in (None, 700000):
        result = check_capital([dict(row, capital_deductions=deduction)])
        assert any(f["check"] == "cap_composition" for f in result.failures)
    result = check_capital([dict(row, capital_deductions=-300000)])
    assert any(f["check"] == "cap_deductions_sign" for f in result.failures)
    result = check_capital([row, dict(row, period_type="prior", capital_deductions=700000)])
    assert any("[prior]" in f["node"] for f in result.failures)


def test_capital_high_ratios_need_independent_components():
    # TOMK 2023Q4's 138.08% is valid; a stray year-like token is not.
    cur = dict(total_capital=1092846, total_rwa=791472)
    _repair_displaced_rows(cur, {}, ["Sermaye Yeterliliği Oranı (%) 138.08 2021."])
    assert cur["capital_adequacy_ratio"] == 138.08
    bad = dict(total_capital=1092846, total_rwa=791472)
    _repair_displaced_rows(bad, {}, ["Sermaye Yeterliliği Oranı (%) 2021. 138.08"])
    assert "capital_adequacy_ratio" not in bad


def test_tomk_rwa_label_without_toplam():
    current, prior, _ = _parse_section(lambda _: ["Risk ağırlıklı Tutarlar 14.165 9.208"], 0, 1)
    assert (current["total_rwa"], prior["total_rwa"]) == (14165, 9208)


def test_liquidity_grouping_requires_independent_component_scale():
    rows = ["TOPLAM YKLV STOKU - - 611.732 133.175",
            "2TOPLAM NET NAKİT ÇIKIŞLARI - - 16.231 33.346",
            "3LİKİDİTE KARŞILAMA ORANI (%) - - 3,768 399,37"]
    lcr, _, _ = _scan(lambda _: rows, 0, 1)
    assert lcr == [["3768.0", "399,37"]]
    # Without component evidence, preserve the decimal reading and do not guess.
    lcr, _, _ = _scan(lambda _: rows[-1:], 0, 1)
    assert lcr == [["3,768", "399,37"]]
    # Prior rows must not borrow the current table's corroborating components.
    lcr, _, _ = _scan(lambda _: rows + rows[-1:], 0, 1)
    assert lcr[1] == ["3,768", "399,37"]


def test_capital_deductions_migration_keeps_history_null_and_scales_new_amounts():
    conn = sqlite3.connect(":memory:")
    old_ddl = "\n".join(line for line in DDL.splitlines() if "capital_deductions" not in line)
    conn.executescript(old_ddl)
    conn.execute("INSERT INTO bank_audit_capital(bank_ticker,period,kind,period_type,extracted_at) "
                 "VALUES('OLD','2025Q1','unconsolidated','current','unchanged')")
    migration = Path(__file__).resolve().parents[1] / "web/migrations/0045_capital_deductions.sql"
    conn.executescript(migration.read_text())
    init_schema(conn)
    assert conn.execute("SELECT capital_deductions,extracted_at FROM bank_audit_capital").fetchone() == (None, "unchanged")
    rep = CapitalReport(rows=[CapitalRow(period_type="current", tier2_capital=31120,
                                        capital_deductions=300, capital_adequacy_ratio=15.54)])
    upsert(conn, "QNBFB", "2026Q2", "unconsolidated", rep, unit=UnitContext("milyon", 1000))
    assert conn.execute("SELECT tier2_capital,capital_deductions,capital_adequacy_ratio "
                        "FROM bank_audit_capital WHERE bank_ticker='QNBFB'").fetchone() == (31120000, 300000, 15.54)
