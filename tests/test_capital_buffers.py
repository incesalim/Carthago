"""Reviewed own-funds rows must reach the existing capital lane with provenance."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

import pytest

from src.audit_reports.capital_adequacy import CapitalReport, CapitalRow, extract_from_pdf, upsert
from src.audit_reports.capital_buffers import BUFFER_FIELDS, parse_buffers
from src.audit_reports.schema import DDL, init_schema
from src.audit_reports.units import UnitContext
from src.audit_reports.validator import check_capital


def _tomk_lines():
    # Independently reviewed original PDF p29; the same five rows are already
    # in the complete-table source benchmark, not expectations from this parser.
    annotation = json.loads((Path(__file__).parent / "fixtures/document_annotations/"
                             "tomk_2023q3_solo.json").read_text(encoding="utf-8"))
    case = next(c for c in annotation["cases"] if c["id"] == "complete_capital_disclosure_page_29")
    return [(29, " ".join(row)) for row in case["rows"][:6]]


def test_all_five_reviewed_buffer_rows_preserve_both_columns_and_source_dash():
    current, prior = parse_buffers(_tomk_lines())
    assert [current[f] for f in BUFFER_FIELDS] == [4, 2.5, None, 1.5, 89.75]
    assert [prior[f] for f in BUFFER_FIELDS] == [4, 2.5, None, 1.5, 94.79]
    for values in (current, prior):
        evidence = json.loads(values["buffer_source_json"])
        assert set(evidence) == set(BUFFER_FIELDS)
        assert evidence["countercyclical_buffer_ratio"]["sources"][0]["raw_value"] == "-"
        assert {s["source_page"] for e in evidence.values() for s in e["sources"]} == {29}


def test_wrapped_english_regulation_does_not_steal_countercyclical_requirement():
    # QNBFB 2026Q1, PDF p46. The 5.97% row cites the buffer regulation but
    # is a distinct available-CET1 measure, not the 0.01% requirement.
    current, prior = parse_buffers([(46, line) for line in [
        "BUFFERS",
        "b) Bank specific counter-cyclical buffer requirement (%) 0.01 0.01",
        "The ratio of Additional Common Equity Tier 1 capital which will be",
        "calculated by the first paragraph of the Article 4 of Regulation on",
        "Capital Conservation and Countercyclical Capital buffers to Risk Weighted Assets (%) 5.97 8.13",
    ]])
    assert current["countercyclical_buffer_ratio"] == prior["countercyclical_buffer_ratio"] == 0.01
    assert (current["cet1_available_buffer_ratio"], prior["cet1_available_buffer_ratio"]) == (5.97, 8.13)


def test_missing_row_does_not_borrow_next_disclosure_or_other_section():
    current, _ = parse_buffers([(29, line) for line in [
        "BUFFERS", "a. Capital conservation buffer ratio (%)",
        "b. Countercyclical buffer ratio (%) 0 0.01",
        "Amounts below the thresholds for deduction",
        "a. Capital conservation buffer ratio (%) 99 99",
    ]])
    assert "capital_conservation_buffer_ratio" not in current
    assert current["countercyclical_buffer_ratio"] == 0
    assert parse_buffers([(29, "Capital conservation buffer ratio (%) 2.5 2.5")]) == ({}, {})


def test_single_column_does_not_invent_prior_evidence():
    current, prior = parse_buffers([(29, "BUFFERS"), (29, "Capital conservation buffer (%) 2.5")])
    assert current["capital_conservation_buffer_ratio"] == 2.5
    assert prior == {}


def test_each_buffer_is_checked_against_its_literal_cell_not_just_the_aggregate():
    current, _ = parse_buffers(_tomk_lines())
    for field in BUFFER_FIELDS:
        altered = dict(current, period_type="current", **{field: 7.5})
        result = check_capital([altered])
        assert any(f["check"] == "cap_buffer_source_value" and field in f["node"]
                   for f in result.failures)


def test_negative_available_buffer_keeps_its_printed_sign():
    current, _ = parse_buffers([(29, "BUFFERS"), (29,
        "The ratio of Additional Common Equity Tier 1 capital which will be "
        "calculated under the buffer regulation (%) (0.25) -")])
    assert current["cet1_available_buffer_ratio"] == -0.25


def test_duplicate_disagreement_abstains_and_validator_flags_it():
    current, _ = parse_buffers([(29, "BUFFERS"),
                                (29, "Capital conservation buffer (%) 2.5 2.5"),
                                (29, "Capital conservation buffer (%) 3.5 2.5")])
    assert current["capital_conservation_buffer_ratio"] is None
    result = check_capital([dict(current, period_type="current")])
    assert any(f["check"] == "cap_buffer_conflict" for f in result.failures)


def test_composition_needs_every_component_or_an_explicit_source_dash():
    current, prior = parse_buffers(_tomk_lines())
    base = dict(period_type="current", cet1_capital=100, tier1_capital=100,
                total_capital=100, total_rwa=1000, capital_adequacy_ratio=10)
    assert check_capital([dict(base, **current)]).failed == 0
    wrong = dict(current, systemic_buffer_ratio=2.5)
    assert any(f["check"] == "cap_buffer_composition"
               for f in check_capital([dict(base, **wrong)]).failures)
    # An absent component is unknown, even when the other components add up.
    missing = dict(wrong, buffer_source_json=None)
    assert not any(f["check"] == "cap_buffer_composition"
                   for f in check_capital([dict(base, **missing)]).failures)
    prior["total_buffer_requirement_ratio"] = 5
    result = check_capital([dict(base, **current), dict(base, **prior, period_type="prior")])
    assert any(f["check"] == "cap_buffer_composition" and "[prior]" in f["node"]
               for f in result.failures)


def test_migration_preserves_history_and_loader_never_scales_percentages():
    conn = sqlite3.connect(":memory:")
    new_columns = (*BUFFER_FIELDS, "buffer_source_json")
    old = "\n".join(line for line in DDL.splitlines() if not any(c in line for c in new_columns))
    conn.executescript(old)
    conn.execute("INSERT INTO bank_audit_capital(bank_ticker,period,kind,period_type,extracted_at) "
                 "VALUES('OLD','2023Q3','unconsolidated','current','unchanged')")
    migration = Path(__file__).resolve().parents[1] / "web/migrations/0048_capital_buffers.sql"
    conn.executescript(migration.read_text())
    init_schema(conn)
    assert conn.execute("SELECT total_buffer_requirement_ratio,extracted_at FROM bank_audit_capital").fetchone() == (None, "unchanged")
    current, prior = parse_buffers(_tomk_lines())
    rep = CapitalReport(source_page=26, rows=[
        CapitalRow(period_type="current", total_capital=100, **current),
        CapitalRow(period_type="prior", total_capital=90, **prior)])
    upsert(conn, "TOMK", "2023Q3", "unconsolidated", rep, unit=UnitContext("milyon", 1000))
    assert conn.execute("SELECT total_capital,capital_conservation_buffer_ratio,countercyclical_buffer_ratio "
                        "FROM bank_audit_capital WHERE bank_ticker='TOMK' AND period_type='current'").fetchone() == (100000, 2.5, None)
    stored = conn.execute("SELECT buffer_source_json FROM bank_audit_capital WHERE bank_ticker='TOMK' AND period_type='current'").fetchone()[0]
    assert json.loads(stored) == json.loads(current["buffer_source_json"])
    conn.execute("UPDATE bank_audit_capital SET extracted_at='unchanged' WHERE bank_ticker='TOMK'")
    changes = conn.total_changes
    upsert(conn, "TOMK", "2023Q3", "unconsolidated", rep, unit=UnitContext("milyon", 1000))
    assert conn.total_changes == changes
    assert conn.execute("SELECT DISTINCT extracted_at FROM bank_audit_capital WHERE bank_ticker='TOMK'").fetchall() == [("unchanged",)]


def test_existing_pdf_entrypoint_reads_buffers_after_the_old_ratio_stop(tmp_path):
    fitz = pytest.importorskip("fitz")
    with fitz.open() as doc:
        for _ in range(13):
            doc.new_page()
        doc[-1].insert_text((50, 50), "\n".join([
            "Common Equity Tier I Capital Before Deductions 100 90",
            "Total Common Equity Tier I Capital 100 90",
            "Total Tier I Capital 100 90", "Total Tier II Capital - -",
            "Total Capital 100 90", "Total Risk Weighted Assets 1000 1000",
            "Capital Adequacy Ratio (%) 10.00 9.00",
        ]))
        doc.new_page().insert_text((50, 50), "\n".join([
            "BUFFERS", "Total Additional Common Equity Tier I Capital Requirement Ratio 4.0 4.0",
            "a. Capital conservation buffer (%) 2.5 2.5",
            "b. Counter-cyclical capital buffer (%) 0 0.01",
            "c. Systemically important bank buffer (%) 1.5 1.49",
        ]), fontsize=8)
        path = tmp_path / "capital.pdf"
        doc.save(path)
    rows = [asdict(r) for r in extract_from_pdf(str(path)).rows]
    assert len(rows) == 2
    assert rows[0]["capital_adequacy_ratio"] == 10
    assert rows[0]["total_buffer_requirement_ratio"] == 4
    assert rows[0]["countercyclical_buffer_ratio"] == 0
    assert rows[1]["countercyclical_buffer_ratio"] == 0.01
    assert json.loads(rows[0]["buffer_source_json"])["systemic_buffer_ratio"]["sources"][0]["source_page"] == 14
