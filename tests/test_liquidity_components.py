"""Original PDF word geometry and independently visually transcribed totals."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from src.audit_reports.liquidity import LiquidityReport, LiquidityRow, upsert
from src.audit_reports.liquidity_components import (
    FIELDS, _lines, amount_value, resolve_components, scan_component_page, with_component_units,
)
from src.audit_reports.schema import DDL, init_schema
from src.audit_reports.units import UNIT_SCALE, UnitContext
from src.audit_reports.validator import check_liquidity

CASES = json.loads(Path("tests/fixtures/liquidity_component_words.json").read_text(encoding="utf-8"))


def records(case):
    return [r for page, words in case["pages"].items() for r in scan_component_page(words, int(page))]


def canonical(case):
    factor = UNIT_SCALE[case["unit"]]
    rows = []
    for period, values in resolve_components(records(case)).items():
        row = dict(values, period_type=period)
        for field in FIELDS:
            row[field] = None if row[field] is None else row[field] * factor
        row["lcr_components_source_json"] = with_component_units(
            row["lcr_components_source_json"], case["unit"], factor)
        rows.append(row)
    return rows


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_six_source_tables_keep_all_48_weighted_or_capped_cells(case):
    for row in canonical(case):
        expected = case["expected"][row["period_type"]]
        assert [row[f] for f in FIELDS] == [n * UNIT_SCALE[case["unit"]] for n in expected]
        failures = check_liquidity([row]).failures
        assert [f["check"] for f in failures] == (
            ["liq_component_net_bounds"] if case["id"] == "ph-t24" and row["period_type"] == "prior" else [])


@pytest.mark.parametrize("field", FIELDS)
def test_missing_or_changed_stored_cell_fails_source_validation(field):
    row = canonical(CASES[1])[0]
    for value in (None, row[field] * 1000, row[field] + 1):
        assert check_liquidity([dict(row, **{field: value})]).failed


def test_period_weighting_currency_and_units_cannot_be_relabelled():
    row = canonical(CASES[1])[0]
    assert check_liquidity([dict(row, period_type="prior")]).failed
    for key, wrong in [("basis", "unweighted"), ("column_index", 0), ("period_heading", "Prior Period"),
                       ("source_unit", "milyon"), ("unit_scale", 1000), ("bbox", [0, 0, 0, 0]),
                       ("raw_label", "20 Total Cash Inflows")]:
        evidence = json.loads(row["lcr_components_source_json"])
        evidence[FIELDS[0]]["sources"][0][key] = wrong
        assert check_liquidity([dict(row, lcr_components_source_json=json.dumps(evidence))]).failed, key


def test_blank_currency_does_not_shift_unweighted_values_and_nil_is_not_zero():
    case = deepcopy(CASES[1])
    words = case["pages"]["85"]
    # The source row has four numeric positions. Removing only weighted total
    # must leave total NULL, never borrow either unweighted 117m/154m figure.
    target = next(w for w in words if w[4] == "80,915,658")
    words.remove(target)
    row = resolve_components(records(case))["current"]
    assert row["lcr_cash_inflows_total"] is None
    assert row["lcr_cash_inflows_fc"] == 140581651
    target[4] = "-"
    words.append(target)
    assert resolve_components(records(case))["current"]["lcr_cash_inflows_total"] is None
    target[4] = "0"
    assert resolve_components(records(case))["current"]["lcr_cash_inflows_total"] == 0


def test_recognized_table_with_missing_row_or_conflicting_repeat_fails():
    case = deepcopy(CASES[1])
    words = case["pages"]["85"]
    row_line = next(line for line in _lines(words) if any(w[4] == "80,915,658" for w in line))
    case["pages"]["85"] = [word for word in words if word not in row_line]
    assert check_liquidity(canonical(case)).failed
    repeated = records(CASES[1])
    changed = deepcopy(repeated[0]); changed["source"]["raw_value"] = "1"
    result = resolve_components(repeated + [changed])["current"]
    assert result[FIELDS[0]] is None
    assert json.loads(result["lcr_components_source_json"])[FIELDS[0]]["status"] == "conflicting_rows"


def test_no_period_heading_is_not_inferred_as_current():
    words = [word for word in CASES[1]["pages"]["85"] if word[4] not in ("Current", "Period")]
    assert scan_component_page(words, 85) == []
    assert amount_value("-") is None
    assert amount_value("0") == 0
    with pytest.raises(ValueError):
        amount_value("123.45")  # not a supported integer money literal


def test_migration_units_and_identical_upsert_are_safe():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("\n".join(line for line in DDL.splitlines()
                                if not any(f in line for f in (*FIELDS, "lcr_components_source_json"))))
    conn.execute("INSERT INTO bank_audit_liquidity(bank_ticker,period,kind,period_type,extracted_at) "
                 "VALUES('OLD','2022Q4','consolidated','current','unchanged')")
    conn.executescript(Path("web/migrations/0050_liquidity_components.sql").read_text())
    init_schema(conn)
    old = dict(conn.execute("SELECT * FROM bank_audit_liquidity").fetchone())
    assert all(old[field] is None for field in FIELDS)
    assert old["extracted_at"] == "unchanged"
    rep = LiquidityReport(rows=[LiquidityRow(period_type=period, lcr_total=127.66, **values)
        for period, values in resolve_components(records(CASES[2])).items()])
    unit = UnitContext("milyon", 1000)
    upsert(conn, "AKBNK", "2026Q2", "consolidated", rep, unit=unit)
    rows = [dict(row) for row in conn.execute("SELECT * FROM bank_audit_liquidity WHERE bank_ticker='AKBNK' ORDER BY period_type")]
    assert rows[0]["lcr_hqla_total"] == 819744000
    assert rows[0]["lcr_total"] == 127.66
    assert check_liquidity(rows).failed == 0
    changes = conn.total_changes
    upsert(conn, "AKBNK", "2026Q2", "consolidated", rep, unit=unit)
    assert conn.total_changes == changes
    conn.execute("UPDATE bank_audit_liquidity SET extracted_at='keep' WHERE bank_ticker='AKBNK'")
    rep.rows[0].lcr_total = 128
    changes = conn.total_changes
    upsert(conn, "AKBNK", "2026Q2", "consolidated", rep, unit=unit)
    assert conn.total_changes - changes == 1
    assert conn.execute("SELECT extracted_at FROM bank_audit_liquidity WHERE bank_ticker='AKBNK' AND period_type='prior'").fetchone()[0] == "keep"


def test_averages_do_not_require_a_false_ratio_identity():
    row = canonical(CASES[1])[0]
    # Source p85 reports 215.60%; ratio of its two averaged amounts is ~215.23%.
    row["lcr_total"] = 215.60
    assert abs(row["lcr_total"] - row["lcr_hqla_total"] / row["lcr_net_cash_outflows_total"] * 100) > 0.1
    assert check_liquidity([row]).failed == 0
