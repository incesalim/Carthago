"""reextract_statement.py's statement-key mapping must cover every statement the
/admin coverage matrix can send (web/app/lib/github.ts STATEMENT_TYPES) so a
single-cell re-extract never dispatches a key the script rejects.
"""
import sqlite3

import pytest

pytest.importorskip("fitz")  # reextract_statement imports the extractor (fitz-only)

from reextract_statement import (  # noqa: E402
    ALIASES, STATEMENT_TABLE, VALIDATOR_NAME, _is_proven_pass,
    _partition_content, should_pull_snapshot,
)
from src.audit_reports.validator import ValidationResult  # noqa: E402

# Mirror of web/app/lib/github.ts STATEMENT_TYPES — the registry keys the matrix
# cells use. Keep in sync if a statement type is added.
MATRIX_STATEMENT_TYPES = {
    "balance_sheet_assets", "balance_sheet_liabilities", "profit_loss",
    "other_comprehensive_income", "equity_change", "cash_flow", "off_balance",
    "credit_quality", "stages", "loans_by_sector", "npl_movement",
    "capital", "liquidity", "profile",
}


def test_every_matrix_statement_resolves_to_a_table():
    for key in MATRIX_STATEMENT_TYPES:
        token = ALIASES.get(key, key)
        assert token in STATEMENT_TABLE, f"{key} -> {token!r} not handled by reextract_statement"


def test_aliases_point_at_real_tokens():
    for token in ALIASES.values():
        assert token in STATEMENT_TABLE


def test_validator_name_keys_are_known_tokens():
    for token in VALIDATOR_NAME:
        assert token in STATEMENT_TABLE


@pytest.mark.parametrize("dry_run,requested,expected", [
    (False, False, True),
    (False, True, True),
    (True, False, False),
    (True, True, True),
])
def test_snapshot_pull_policy(dry_run, requested, expected):
    assert should_pull_snapshot(
        dry_run=dry_run, pull_snapshot_requested=requested) is expected


def test_partition_content_ignores_write_timestamp_but_not_facts():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE statement_rows (bank_ticker TEXT, period TEXT, kind TEXT, "
        "item_order INTEGER, amount REAL, extracted_at TEXT)")
    conn.execute(
        "INSERT INTO statement_rows VALUES ('AKBNK', '2026Q2', 'consolidated', "
        "1, 46, '2026-08-01')")
    before = _partition_content(
        conn, "statement_rows", "AKBNK", "2026Q2", "consolidated")

    conn.execute("UPDATE statement_rows SET extracted_at='2026-08-06'")
    assert _partition_content(
        conn, "statement_rows", "AKBNK", "2026Q2", "consolidated") == before

    conn.execute("UPDATE statement_rows SET amount=-46")
    assert _partition_content(
        conn, "statement_rows", "AKBNK", "2026Q2", "consolidated") != before


def test_candidate_requires_positive_validation_evidence():
    passed = ValidationResult(passed=1)
    failed = ValidationResult(passed=12, failed=1)
    skipped_only = ValidationResult(skipped=3)

    assert _is_proven_pass(passed)
    assert not _is_proven_pass(failed)
    assert not _is_proven_pass(skipped_only)
