"""reextract_statement.py's statement-key mapping must cover every statement the
/admin coverage matrix can send (web/app/lib/github.ts STATEMENT_TYPES) so a
single-cell re-extract never dispatches a key the script rejects.
"""
import pytest

pytest.importorskip("pdfplumber")  # reextract_statement imports the extractor

from reextract_statement import ALIASES, STATEMENT_TABLE, VALIDATOR_NAME  # noqa: E402

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
