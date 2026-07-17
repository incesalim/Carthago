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
    section: str                  # the report Bölüm the table is printed in: '1'/'2'/'4'/'5'/'7'.
    #                               PROVENANCE, and the only thing that says whether a table is a
    #                               primary statement or a note. NOT is_core — see below.
    #                               The bare number: the '§' is typography and belongs to the view
    #                               (and keeps the D1 migration ASCII, like every other one).
    is_core: bool                 # gates bank_audit_extractions.success. A SEVERITY flag: "an empty
    #                               lane here means the extraction failed, fail the whole report".
    #                               Says NOTHING about where the table sits in the filing — OCI,
    #                               changes-in-equity, cash-flow and off-balance are all §2 primary
    #                               statements that are deliberately is_core=False, because one
    #                               missing note-page shouldn't discard a good BS+P&L extraction.
    #                               The /admin matrix grouped on this flag until 2026-07-17 and so
    #                               labelled four §2 statements "Footnotes & §4". Group on `section`.
    present_min_rows: int | None  # ">= this many rows" ⇒ present (for row-based tables)
    has_validator: bool           # structural validator writes bank_audit_validation for it
    validation_statement: str | None  # the `statement` value in bank_audit_validation (if validated)
    sort_order: int
    annual_only: bool = False     # disclosed only in the Q4 (annual) report (e.g. loans-by-sector);
    #                               interim cells with no data are N/A in the matrix, not "missing"
    conditional: bool = False     # disclosed only when the bank HOLDS one (e.g. free provision);
    #                               an empty cell means "no such reserve" = N/A, not "missing"


# Order: the §2 primary statements first, then the §5 notes, the §4 risk
# disclosures, and the two single-table sections. sort_order drives the UI within
# a section; SECTION_ORDER (below) orders the sections themselves.
REGISTRY: list[StatementType] = [
    StatementType("balance_sheet_assets", "Balance sheet — assets",
                  "bank_audit_balance_sheet", "assets", "bs_assets", section="2",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="assets", sort_order=10),
    StatementType("balance_sheet_liabilities", "Balance sheet — liabilities",
                  "bank_audit_balance_sheet", "liabilities", "bs_liabilities", section="2",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="liabilities", sort_order=20),
    StatementType("profit_loss", "Income statement (P&L)",
                  "bank_audit_profit_loss", None, "profit_loss", section="2",
                  is_core=True, present_min_rows=20, has_validator=True,
                  validation_statement="profit_loss", sort_order=30),
    # OCI / changes-in-equity / cash-flow are three of the five primary statements
    # a complete set requires under TAS 1 — not notes. is_core=False is the
    # severity call (a missing one shouldn't fail the report), not a demotion.
    StatementType("other_comprehensive_income", "Other comprehensive income (OCI)",
                  "bank_audit_oci", None, "oci", section="2",
                  is_core=False, present_min_rows=5, has_validator=True,
                  validation_statement="oci", sort_order=35),
    StatementType("equity_change", "Statement of changes in equity",
                  "bank_audit_equity_change", None, "equity_change", section="2",
                  is_core=False, present_min_rows=8, has_validator=True,
                  validation_statement="equity_change", sort_order=36),
    StatementType("cash_flow", "Cash flow statement",
                  "bank_audit_cash_flow", None, "cash_flow", section="2",
                  is_core=False, present_min_rows=10, has_validator=True,
                  validation_statement="cash_flow", sort_order=38),
    # "Nazım Hesaplar Tablosu" — a BRSA addition to the IFRS set, but printed as a
    # primary statement on the balance-sheet page, hence §2 and not a note.
    StatementType("off_balance", "Off-balance sheet",
                  "bank_audit_balance_sheet", "off_balance", "off_balance", section="2",
                  is_core=False, present_min_rows=10, has_validator=True,
                  validation_statement="off_balance", sort_order=40),
    StatementType("credit_quality", "Credit quality (IFRS-9 footnote)",
                  "bank_audit_credit_quality", None, "credit_quality", section="5",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="credit_quality", sort_order=50),
    # Derived from credit_quality rather than parsed on its own, but the
    # disclosure it rests on is the §5 note — section is provenance, not pipeline.
    StatementType("stages", "IFRS-9 stages (derived)",
                  "bank_audit_stages", None, None, section="5",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="stages", sort_order=60),
    StatementType("loans_by_sector", "Loans by sector",
                  "bank_audit_loans_by_sector", None, "loans_by_sector", section="5",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="loans_by_sector", sort_order=70, annual_only=True),
    StatementType("npl_movement", "NPL movement",
                  "bank_audit_npl_movement", None, "npl_movement", section="5",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="npl_movement", sort_order=80),
    StatementType("capital", "Capital adequacy (§4)",
                  "bank_audit_capital", None, "capital", section="4",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="capital", sort_order=90),
    StatementType("liquidity", "Liquidity (§4)",
                  "bank_audit_liquidity", None, "liquidity", section="4",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="liquidity", sort_order=100),
    StatementType("fx_position", "FX net open position (§4)",
                  "bank_audit_fx_position", None, "fx_position", section="4",
                  is_core=False, present_min_rows=4, has_validator=True,
                  validation_statement="fx_position", sort_order=105),
    StatementType("repricing", "Interest-rate repricing gap (§4)",
                  "bank_audit_repricing", None, "repricing", section="4",
                  is_core=False, present_min_rows=7, has_validator=True,
                  validation_statement="repricing", sort_order=106),
    StatementType("profile", "Bank profile (branches/personnel)",
                  "bank_audit_profile", None, None, section="1",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="profile", sort_order=110),
    StatementType("audit_opinion", "Audit opinion",
                  "bank_audit_opinion", None, None, section="7",
                  is_core=False, present_min_rows=1, has_validator=True,
                  validation_statement="audit_opinion", sort_order=115),
    # free_provision stays has_validator=False DELIBERATELY, and not for want of
    # a check. conditional=True routes a 0-row partition missing → not_expected
    # in sync_audit_expected.build() BEFORE any verdict is read, so a
    # per-partition validator could never see the 469 N/A cells — the only ones
    # with a real problem (52 of them are suspect; BURGAN 2023Q2–2024Q1 read N/A
    # while the auditor qualified over exactly that reserve). Its checks are
    # corpus-wide and longitudinal by nature, so they live in
    # check_audit_quality._free_provision alongside the prior_chain check that is
    # already there.
    StatementType("free_provision", "Free provision (serbest karşılık)",
                  "bank_audit_free_provision", None, None, section="5",
                  is_core=False, present_min_rows=1, has_validator=False,
                  validation_statement=None, sort_order=116, conditional=True),
]

# The report's Bölüm, in the order the coverage matrix groups them: the primary
# statements lead (they carry the fleet), then the notes and risk disclosures we
# extract, then the two one-table sections. NOT the filing's own §1→§7 order —
# that would open the matrix on branches/personnel.
SECTION_ORDER: list[str] = ["2", "5", "4", "1", "7"]

BY_KEY: dict[str, StatementType] = {st.key: st for st in REGISTRY}

# The tables that carry no statement rows: the structural-validation results, the
# per-partition extraction log, and the derived P&L role map (which row is the
# period-net / gross / opex under THIS filer's roman numbering — see schema.py).
# Not statement types — but every audit D1 push and every partition clear must
# carry them.
INFRA_TABLES: list[str] = ["bank_audit_validation", "bank_audit_extractions",
                           "bank_audit_pl_roles"]

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
         "statement": st.statement, "section": st.section, "is_core": int(st.is_core),
         "has_validator": int(st.has_validator),
         "section_rank": SECTION_ORDER.index(st.section) if st.section in SECTION_ORDER else 99,
         "sort_order": st.sort_order}
        for st in REGISTRY
    ]
