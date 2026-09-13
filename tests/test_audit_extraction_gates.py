"""Fault injection must measure real gates without altering the source data."""
import json
import sqlite3

import pytest

pytest.importorskip("fitz")

from scripts.diagnostics.audit_extraction_gates import (  # noqa: E402
    Fault, apply_fault, audit_lane, digest, disposable_database,
    lane_rows, select_faults, summarize, verdict,
    pull_pinned_snapshot,
)
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.validator import ValidationResult  # noqa: E402

PART = ("AKBNK", "2026Q2", "consolidated")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.db"
    conn = sqlite3.connect(path)
    init_schema(conn)
    conn.executemany(
        "INSERT INTO bank_audit_liquidity(bank_ticker,period,kind,period_type,lcr_total,lcr_fc) "
        "VALUES (?,?,?,?,?,?)", [(*PART, "current", 200, 150), (*PART, "prior", 170, 120)])
    conn.commit()
    conn.close()
    return path


def test_faults_measure_accepted_corruption_and_rollback_source_exactly(source):
    before = digest(source)
    with disposable_database(source) as (conn, schema):
        baseline = revalidate_partition(conn, *PART)
        original = lane_rows(conn, PART, "liquidity")[0]
        result = audit_lane(conn, PART, "liquidity", baseline, schema, 0)
        assert result["state"] == "eligible"
        assert {c["outcome"] for c in result["cases"]} == {"escaped", "rejected"}
        # Merely swapping two plausible period ratios cannot be seen without
        # their source evidence. This measures a real gap, not a fake validator.
        swap = next(c for c in result["cases"] if c["operator"] == "swap_periods")
        assert swap["outcome"] == "escaped"
        assert next(c for c in result["cases"] if c["operator"] == "delete_table")["outcome"] == "rejected"
        assert {c["column"]: c["outcome"] for c in result["cases"]
                if c["operator"] == "null_column"} == {"lcr_total": "rejected", "lcr_fc": "escaped"}
        assert lane_rows(conn, PART, "liquidity")[0] == original
    assert digest(source) == before


def test_failed_and_unchecked_baselines_never_enter_escape_denominator(source):
    with disposable_database(source) as (conn, schema):
        for value, state in [(ValidationResult(failed=1), "baseline_failed"),
                             (ValidationResult(skipped=1), "unproven")]:
            result = audit_lane(conn, PART, "liquidity", {"liquidity": value}, schema, 0)
            assert result["state"] == state
            assert result["cases"] == []
            assert summarize([result])["liquidity"]["tested_faults"] == 0
        result = audit_lane(conn, PART, "equity_change", {}, schema, 0)
        assert result["state"] == "empty"


def test_all_relationship_gates_and_conditional_skip_policy_are_measured():
    good = ValidationResult(passed=1)
    skip = ValidationResult(skipped=1)
    assert not verdict({"assets": good}, "balance_sheet_assets")["accepted"]
    assert verdict({"assets": good, "liabilities": good, "cross": good},
                   "balance_sheet_assets")["accepted"]
    assert not verdict({"credit_quality": good, "stages": skip}, "credit_quality")["accepted"]
    assert not verdict({"capital": skip}, "capital")["accepted"]
    assert verdict({"free_provision": skip}, "free_provision")["accepted"]


def test_sampling_is_explicit_deterministic_and_balanced_by_operator(source):
    with disposable_database(source) as (conn, schema):
        rows, _, _ = lane_rows(conn, PART, "liquidity")
        first, candidates = select_faults(rows, schema["bank_audit_liquidity"], 1)
        second, _ = select_faults(list(reversed(rows)), schema["bank_audit_liquidity"], 1)
        assert first == second
        assert len(first) == len(candidates)
        assert sum(candidates.values()) > len(first)
        assert "source_page" not in {f.column for f in first}


def test_mutation_exception_is_reported_and_still_rolled_back(source, monkeypatch):
    import scripts.diagnostics.audit_extraction_gates as audit
    with disposable_database(source) as (conn, schema):
        baseline = revalidate_partition(conn, *PART)
        original = lane_rows(conn, PART, "liquidity")[0]

        def fail(*args):
            raise ValueError("validator failure")

        monkeypatch.setattr(audit, "revalidate_partition", fail)
        result = audit_lane(conn, PART, "liquidity", baseline, schema, 1)
        assert all(c["outcome"] == "execution_error" for c in result["cases"])
        assert lane_rows(conn, PART, "liquidity")[0] == original


def test_duplicate_labels_mutate_only_exact_row_identity(source):
    with disposable_database(source) as (conn, _):
        conn.executemany(
            "INSERT INTO bank_audit_profit_loss(bank_ticker,period,kind,item_order,item_name,amount) "
            "VALUES (?,?,?,?,?,?)", [(*PART, 1, "Non-cash loans", 175010),
                                    (*PART, 2, "Non-cash loans", 449)])
        rows, where, params = lane_rows(conn, PART, "profit_loss")
        apply_fault(conn, "bank_audit_profit_loss", where, params,
                    Fault("cell_value", rows[1]["_rowid_"], "amount", 175010))
        assert [r["amount"] for r in lane_rows(conn, PART, "profit_loss")[0]] == [175010, 175010]
        assert rows[0]["amount"] == 175010 and rows[1]["amount"] == 449


def test_snapshot_upgrade_does_not_hide_missing_source_columns(tmp_path):
    source = tmp_path / "old.db"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE placeholder (value INTEGER)")
    conn.commit()
    conn.close()
    before = digest(source)
    with disposable_database(source) as (conn, schema):
        result = audit_lane(conn, PART, "liquidity", {}, schema, 1)
        assert "lcr_components_source_json" in result["source_missing_columns"]
        json.dumps(result)  # report is portable, no connection or sqlite.Row objects
    assert digest(source) == before


def test_filing_scale_changes_money_but_keeps_ratios_and_other_filings(source):
    with disposable_database(source) as (conn, _):
        conn.executemany(
            "INSERT INTO bank_audit_profit_loss(bank_ticker,period,kind,item_order,item_name,amount) "
            "VALUES (?,?,?,?,?,?)", [(*PART, 1, "profit", 10),
                                    (PART[0], "2026Q1", PART[2], 1, "profit", 20)])
        before_ratios = lane_rows(conn, PART, "liquidity")[0]
        apply_fault(conn, "bank_audit_profit_loss", "", list(PART), Fault("scale_filing"))
        assert lane_rows(conn, PART, "profit_loss")[0][0]["amount"] == 10000
        assert lane_rows(conn, (PART[0], "2026Q1", PART[2]), "profit_loss")[0][0]["amount"] == 20
        assert lane_rows(conn, PART, "liquidity")[0] == before_ratios


def test_snapshot_pull_requires_actions_and_pinned_new_destination(source, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="GitHub Actions"):
        pull_pinned_snapshot(source, "etag")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(ValueError, match="new destination"):
        pull_pinned_snapshot(source, "etag")
