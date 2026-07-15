"""The statement-type registry — one declarative source of truth for the audit
lane's ~10 financial-statement types.

Both the loader (the `success` gate) and the dashboard coverage matrix derive
from this, so "what statement types exist, where they live, and how we decide
present / errored" lives in exactly one place. Adding a type is a registry entry.

Pure stdlib (no extractor/D1 imports) so it's importable in CI and the
display rows can be emitted to D1 for the Worker to read.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatementType:
    key: str                      # stable id, e.g. "balance_sheet_assets"
    label: str                    # human label for the dashboard
    table: str                    # D1/SQLite table the rows live in
    statement: str | None         # value of the `statement` column (BS sub-statements); else None
    count_key: str | None         # key in loader.upsert_report's counts dict (None if not logged there)
    is_core: bool                 # gates bank_audit_extractions.success
    present_min_rows: int | None  # ">= this many rows" ⇒ present (for row-based tables)
    has_validator: bool           # structural validator writes bank_audit_validation for it
    validation_statement: str | None  # the `statement` value in bank_audit_validation (if validated)
    sort_order: int
    annual_only: bool = False     # disclosed only in the Q4 (annual) report (e.g. loans-by-sector);
    #                               interim cells with no data are N/A in the matrix, not "missing"
    conditional: bool = False     # disclosed only when the bank HOLDS one (e.g. free provision);
    #                               an empty cell means "no such reserve" = N/A, not "missing"


# Order: core financials first, then footnote/§4 tables. sort_order drives the UI.
REGISTRY: list[StatementType] = [
    StatementType("balance_sheet_assets", "Balance sheet — assets",
                  "bank_audit_balance_sheet", "assets", "bs_assets",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="assets", sort_order=10),
    StatementType("balance_sheet_liabilities", "Balance sheet — liabilities",
                  "bank_audit_balance_sheet", "liabilities", "bs_liabilities",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="liabilities", sort_order=20),
    StatementType("profit_loss", "Income statement (P&L)",
                  "bank_audit_profit_loss", None, "profit_loss",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="profit_loss", sort_order=30),
    StatementType("other_comprehensive_income", "Other comprehensive income (OCI)",
                  "bank_audit_oci", None, "oci",
                  is_core=False, present_min_rows=5, has_validator=True,
                  validation_statement="oci", sort_order=35),
    StatementType("equity_change", "Statement of changes in equity",
                  "bank_audit_equity_change", None, "equity_change",
                  is_core=False, present_min_rows=8, has_validator=True,
                  validation_statement="equity_change", sort_order=36),
    StatementType("cash_flow", "Cash flow statement",
                  "bank_audit_cash_flow", None, "cash_flow",
                  is_core=False, present_min_rows=10, has_validator=True,
                  validation_statement="cash_flow", sort_order=38),
    StatementType("off_balance", "Off-balance sheet",
                  "bank_audit_balance_sheet", "off_balance", "off_balance",
                  is_core=False, present_min_rows=10, has_validator=True,
                  validation_statement="off_balance", sort_order=40),
    StatementType("credit_quality", "Credit quality (IFRS-9 footnote)",
                  "bank_audit_credit_quality", None, "credit_quality",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="credit_quality", sort_order=50),
    StatementType("stages", "IFRS-9 stages (derived)",
                  "bank_audit_stages", None, None,
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="stages", sort_order=60),
    StatementType("loans_by_sector", "Loans by sector",
                  "bank_audit_loans_by_sector", None, "loans_by_sector",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="loans_by_sector", sort_order=70, annual_only=True),
    StatementType("npl_movement", "NPL movement",
                  "bank_audit_npl_movement", None, "npl_movement",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="npl_movement", sort_order=80),
    StatementType("capital", "Capital adequacy (§4)",
                  "bank_audit_capital", None, "capital",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="capital", sort_order=90),
    StatementType("liquidity", "Liquidity (§4)",
                  "bank_audit_liquidity", None, "liquidity",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="liquidity", sort_order=100),
    StatementType("fx_position", "FX net open position (§4)",
                  "bank_audit_fx_position", None, "fx_position",
                  is_core=False, present_min_rows=4, has_validator=True,
                  validation_statement="fx_position", sort_order=105),
    StatementType("repricing", "Interest-rate repricing gap (§4)",
                  "bank_audit_repricing", None, "repricing",
                  is_core=False, present_min_rows=7, has_validator=True,
                  validation_statement="repricing", sort_order=106),
    StatementType("profile", "Bank profile (branches/personnel)",
                  "bank_audit_profile", None, None,
                  is_core=False, present_min_rows=1, has_validator=False,
                  validation_statement=None, sort_order=110),
    StatementType("audit_opinion", "Audit opinion",
                  "bank_audit_opinion", None, None,
                  is_core=False, present_min_rows=1, has_validator=False,
                  validation_statement=None, sort_order=115),
    StatementType("free_provision", "Free provision (serbest karşılık)",
                  "bank_audit_free_provision", None, None,
                  is_core=False, present_min_rows=1, has_validator=False,
                  validation_statement=None, sort_order=116, conditional=True),
]

BY_KEY: dict[str, StatementType] = {st.key: st for st in REGISTRY}

# The two tables that carry no statement rows: the structural-validation results
# and the per-partition extraction log. Not statement types — but every audit D1
# push and every partition clear must carry them.
INFRA_TABLES: list[str] = ["bank_audit_validation", "bank_audit_extractions"]

# Every bank_audit_* table the audit lane writes: one per registered statement
# type (deduped — the balance sheet carries three sub-statements) plus the infra
# pair. THE list. Never re-enumerate it by hand.
#
# A hand-written copy is how fx_position + repricing stopped reaching D1: the
# market-risk lane shipped 2026-06-27, the extractor, the loader and
# push_to_d1.SYNC_TABLES all learned the two tables — and refresh-audit.yml's
# --only-tables didn't. The rows were extracted, stored and snapshotted every
# quarter, and silently never arrived. Registering a statement type above is now
# the only step needed to get its table pushed.
AUDIT_TABLES: list[str] = list(dict.fromkeys([st.table for st in REGISTRY] + INFRA_TABLES))


def core_types() -> list[StatementType]:
    return [st for st in REGISTRY if st.is_core]


def success_from_counts(counts: dict[str, int]) -> bool:
    """The bank_audit_extractions.success gate: every core statement has at least
    its minimum row count. Equivalent to the historical
    `all(c >= 20 for c in [bs_assets, bs_liabilities, profit_loss])`."""
    return all((counts.get(st.count_key, 0) or 0) >= (st.present_min_rows or 0)
               for st in core_types())


def web_metadata() -> list[dict]:
    """Display rows for the bank_audit_statement_types D1 table — so the Worker
    reads the registry from D1 instead of importing this module."""
    return [
        {"key": st.key, "label": st.label, "table": st.table,
         "statement": st.statement, "is_core": int(st.is_core),
         "has_validator": int(st.has_validator), "sort_order": st.sort_order}
        for st in REGISTRY
    ]
