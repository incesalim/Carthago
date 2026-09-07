"""Existing liquidity lane against retained original TR/EN report pages."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

import pytest

from src.audit_reports import liquidity
from src.audit_reports.liquidity_coverage import ratio_value, resolve_lcr, scan_lcr
from src.audit_reports.schema import DDL, init_schema
from src.audit_reports.units import UnitContext
from src.audit_reports.validator import check_liquidity

FIXTURE = json.loads((Path(__file__).parent / "fixtures/liquidity_source_periods.json").read_text(encoding="utf-8"))


def source_report(monkeypatch, case):
    pages = {int(k) - 1: v for k, v in case["pages"].items()}
    monkeypatch.setattr(liquidity, "_HAS_FITZ", True)
    monkeypatch.setattr(liquidity, "_fitz_page_count", lambda _: case["page_count"])
    monkeypatch.setattr(liquidity, "_fitz_page_text", lambda _, i: "\n".join(pages.get(i, [])))
    monkeypatch.setattr(liquidity, "_fitz_lines", lambda _, i: pages.get(i, []))
    return liquidity.extract_from_pdf("source.pdf")


@pytest.mark.parametrize("case,expected", [
    # Values transcribed from the original source pages, independently of this
    # reader. TOMK23's current huge ratio conflicts with its high/low disclosure:
    # retaining its literal is NOT a financial certification or publish approval.
    (FIXTURE[0], [(809080325, 1047115, 33), (142085400, None, 34)]),
    (FIXTURE[1], [(266.99, 767.43, 35), (3768, 399.37, 36)]),
    (FIXTURE[2], [(215.60, 522.77, 85), (197.05, 406.54, 86)]),
])
def test_original_pages_reach_both_periods_and_keep_literal_evidence(monkeypatch, case, expected):
    rep = source_report(monkeypatch, case)
    assert [r.period_type for r in rep.rows] == ["current", "prior"]
    for row, (total, fc, page) in zip(rep.rows, expected):
        assert (row.lcr_total, row.lcr_fc) == (total, fc)
        evidence = json.loads(row.lcr_source_json)
        for field in ("lcr_total", "lcr_fc"):
            source = evidence[field]["sources"][0]
            assert source["source_page"] == page
            assert source["period_type"] == row.period_type
            assert source["period_assignment"] == "heading"
        failures = check_liquidity([asdict(row)]).failures
        if case is FIXTURE[0] and row.period_type == "current":
            assert [f["check"] for f in failures] == ["liq_source_range"]
        else:
            assert failures == []
    if case is FIXTURE[0]:
        evidence = json.loads(rep.rows[1].lcr_source_json)
        assert evidence["lcr_fc"]["sources"][0]["raw_value"] == "-"


def test_prior_only_is_never_promoted_to_current():
    result = resolve_lcr(scan_lcr([(34, ["Önceki Dönem TP+YP YP", "23 LİKİDİTE KARŞILAMA ORANI (%) 142.085.400 -"])]))
    assert set(result) == {"prior"}
    assert result["prior"]["lcr_total"] == 142085400


def test_unheaded_duplicate_does_not_invent_a_comparative_period():
    result = resolve_lcr(scan_lcr([(1, ["Liquidity Coverage Ratio (%) 150 200", "Liquidity Coverage Ratio (%) 160 210"])]))
    assert set(result) == {"current"}
    assert result["current"]["lcr_total"] == 150


def test_scan_continues_after_all_current_metrics_until_comparative_table():
    pages = {0: ["Current Period", "High-Quality Liquid Assets",
                 "Liquidity Coverage Ratio (%) 150 200", "Net Stable Funding Ratio 125",
                 "Leverage ratio 8 7"],
             1: ["Prior Period", "Liquidity Coverage Ratio (%) 140 190"]}
    observations = []
    liquidity._scan(lambda i: pages[i], 0, 2, lcr_records=observations)
    assert resolve_lcr(observations)["prior"]["lcr_total"] == 140


def test_nil_and_zero_are_distinct_and_displaced_values_cannot_cross_pages():
    result = resolve_lcr(scan_lcr([(1, ["Current Period", "Liquidity Coverage Ratio (%)", "- - 150 0"]),
                                   (2, ["Prior Period", "Liquidity Coverage Ratio (%) - -"])]))
    assert result["current"]["lcr_fc"] == 0
    assert result["prior"]["lcr_fc"] is None
    assert scan_lcr([(1, ["Liquidity Coverage Ratio (%)"]), (2, ["150 200"])]) == []
    assert scan_lcr([(1, ["Liquidity Coverage Ratio (%) 1 2 3 4"])]) == []


def test_disagreement_and_cell_or_period_mutations_fail_validation():
    result = resolve_lcr(scan_lcr([(1, ["Current Period", "Liquidity Coverage Ratio (%) 150 200"])]))["current"]
    row = dict(result, period_type="current")
    for field in ("lcr_total", "lcr_fc"):
        assert check_liquidity([dict(row, **{field: 170})]).failed
        assert check_liquidity([dict(row, **{field: None})]).failed
    assert check_liquidity([dict(row, period_type="prior")]).failed
    corrupted = json.loads(row["lcr_source_json"])
    corrupted["lcr_total"]["sources"][0]["period_heading"] = "Prior Period"
    assert check_liquidity([dict(row, lcr_source_json=json.dumps(corrupted))]).failed
    duplicate = resolve_lcr(scan_lcr([(1, ["Prior Period", "Liquidity Coverage Ratio (%) 150 200", "Liquidity Coverage Ratio (%) 160 200"])]))["prior"]
    assert duplicate["lcr_total"] is None
    assert check_liquidity([dict(duplicate, period_type="prior")]).failed


def test_ratio_grouping_sign_and_no_component_borrowing():
    assert ratio_value("142.085.400") == 142085400
    assert ratio_value("142,085,400") == 142085400
    assert ratio_value("(3.25)") == -3.25
    assert ratio_value("3,768") == 3.768
    assert ratio_value("3,768", "611.732", "16.231") == 3768
    records = scan_lcr([(1, ["Current Period", "TOPLAM YKLV STOKU 611.732 133.175",
        "TOPLAM NET NAKİT ÇIKIŞLARI 16.231 33.346", "Prior Period",
        "Liquidity Coverage Ratio (%) 3,768 399,37"])])
    assert records[0]["values"][0] == 3.768


def test_printed_range_is_period_scoped_and_accepts_reversed_high_low_columns():
    observations = scan_lcr([(33, ["Cari Dönem En Düşük Tarih En Yüksek Tarih",
        "TP+YP 100,25 01.07.2024 300,75 30.09.2024",
        "YP 120,25 01.07.2024 320,75 30.09.2024",
        "Cari Dönem TP+YP YP", "Liquidity Coverage Ratio (%) 150 200",
        "Önceki Dönem TP+YP YP", "Liquidity Coverage Ratio (%) 500 600"])])
    resolved = resolve_lcr(observations)
    for period, values in resolved.items():
        assert check_liquidity([dict(values, period_type=period)]).failed == 0
    assert json.loads(resolved["prior"]["lcr_source_json"])["lcr_total"]["sources"][0]["reported_range"] is None


def test_migration_preserves_history_and_repeat_upsert_writes_nothing(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.executescript("\n".join(line for line in DDL.splitlines() if "lcr_source_json" not in line))
    conn.execute("INSERT INTO bank_audit_liquidity(bank_ticker,period,kind,period_type,extracted_at) "
                 "VALUES('OLD','2022Q4','consolidated','current','unchanged')")
    conn.executescript(Path("web/migrations/0049_liquidity_source.sql").read_text())
    init_schema(conn)
    assert conn.execute("SELECT lcr_source_json,extracted_at FROM bank_audit_liquidity").fetchone() == (None, "unchanged")
    rep = source_report(monkeypatch, FIXTURE[1])
    liquidity.upsert(conn, "TOMK", "2024Q1", "unconsolidated", rep, unit=UnitContext("milyon", 1000))
    assert conn.execute("SELECT lcr_total,lcr_fc FROM bank_audit_liquidity WHERE bank_ticker='TOMK' ORDER BY period_type").fetchall() == [(266.99, 767.43), (3768, 399.37)]
    conn.execute("UPDATE bank_audit_liquidity SET extracted_at='unchanged'")
    changes = conn.total_changes
    liquidity.upsert(conn, "TOMK", "2024Q1", "unconsolidated", rep, unit=UnitContext("milyon", 1000))
    assert conn.total_changes == changes
    assert conn.execute("SELECT DISTINCT extracted_at FROM bank_audit_liquidity").fetchall() == [("unchanged",)]
