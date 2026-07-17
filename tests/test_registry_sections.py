"""`section` is provenance; `is_core` is severity. Keep them apart.

Regression guard for the 2026-07-17 fix. The /admin coverage matrix grouped its
lanes on `is_core` and headed the false group "Footnotes & §4" — so OCI, changes
in equity, cash flow and off-balance, four §2 PRIMARY statements, were presented
to the operator as footnotes. Nothing was wrong with the data; the taxonomy was
borrowed from a flag that never meant what the view read into it.

`is_core` gates `bank_audit_extractions.success` and nothing else: "an empty lane
here means the extraction failed". It is False for those four because one
unreadable note-page shouldn't discard a good BS+P&L — not because they're notes.

Each test pins one link so the conflation can't come back.
"""

import sqlite3
from pathlib import Path

from src.audit_reports import schema
from src.audit_reports.registry import (
    BY_KEY,
    REGISTRY,
    SECTION_ORDER,
    core_types,
    web_metadata,
)

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO / "web" / "migrations"

# The five statements TAS 1 requires in a complete set (as BRSA prints them),
# plus off-balance ("Nazım Hesaplar Tablosu"), which is a BRSA addition but is
# printed as a primary statement on the balance-sheet page — not in the notes.
PRIMARY_STATEMENTS = {
    "balance_sheet_assets",
    "balance_sheet_liabilities",
    "profit_loss",
    "other_comprehensive_income",
    "equity_change",
    "cash_flow",
    "off_balance",
}


def test_every_type_has_a_known_section():
    """A lane registered without a section renders under a blank heading."""
    orphans = [st.key for st in REGISTRY if st.section not in SECTION_ORDER]
    assert not orphans, (
        f"section missing or not in SECTION_ORDER {SECTION_ORDER}: {orphans}"
    )


def test_the_primary_statements_are_section_2():
    """The bug, stated directly: these are §2 statements, whatever is_core says."""
    misfiled = {k: BY_KEY[k].section for k in PRIMARY_STATEMENTS if BY_KEY[k].section != "2"}
    assert not misfiled, f"primary statements filed outside §2: {misfiled}"


def test_is_core_is_severity_not_provenance():
    """is_core marks the lanes whose absence fails the whole extraction — exactly
    BS assets / BS liabilities / P&L. If this list ever grows to match §2, someone
    has read it as "primary statement" again."""
    assert {st.key for st in core_types()} == {
        "balance_sheet_assets",
        "balance_sheet_liabilities",
        "profit_loss",
    }
    # The four that started this: §2 primary statements, deliberately not gates.
    for key in ("other_comprehensive_income", "equity_change", "cash_flow", "off_balance"):
        assert BY_KEY[key].section == "2" and not BY_KEY[key].is_core, (
            f"{key} is a §2 primary statement that must NOT gate success"
        )


def test_section_is_ascii_bare_number():
    """The '§' is typography and lives in the view — storing it would put
    non-ASCII into a D1 migration, which every other migration avoids."""
    for st in REGISTRY:
        assert st.section.isascii() and st.section.isdigit(), (
            f"{st.key}: section must be a bare Bölüm number, got {st.section!r}"
        )


def test_web_metadata_carries_section_and_rank():
    for m in web_metadata():
        assert m["section"] in SECTION_ORDER
        assert m["section_rank"] == SECTION_ORDER.index(m["section"])


def test_migration_0030_backfill_matches_the_registry():
    """The backfill hand-lists each key in SQL, so it can drift from the registry.
    sync_audit_expected.py would eventually heal it, but it runs in the audit
    workflows — not on deploy — so a drifted backfill is what /admin shows in the
    meantime. Replay the real migration and diff it against the registry."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        (MIGRATIONS / "0008_audit_registry_expected.sql").read_text(encoding="utf-8"))
    # Seed the table as the live D1 holds it today: pre-section columns only.
    conn.executemany(
        "INSERT INTO bank_audit_statement_types (key, label, source_table, statement, "
        "is_core, has_validator, sort_order) VALUES (?,?,?,?,?,?,?)",
        [(m["key"], m["label"], m["table"], m["statement"], m["is_core"],
          m["has_validator"], m["sort_order"]) for m in web_metadata()])
    conn.executescript(
        (MIGRATIONS / "0030_audit_statement_type_section.sql").read_text(encoding="utf-8"))

    got = {k: (s, r) for k, s, r in conn.execute(
        "SELECT key, section, section_rank FROM bank_audit_statement_types")}
    want = {m["key"]: (m["section"], m["section_rank"]) for m in web_metadata()}
    assert got == want, "migration 0030's backfill has drifted from the registry"


def test_fresh_schema_and_the_sync_insert_agree():
    """schema.py's DDL and sync_audit_expected.write()'s column list are edited in
    different files; a mismatch silently lands values in the wrong column."""
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO bank_audit_statement_types (key, label, source_table, statement, "
        "section, is_core, has_validator, section_rank, sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
        [(m["key"], m["label"], m["table"], m["statement"], m["section"],
          m["is_core"], m["has_validator"], m["section_rank"], m["sort_order"])
         for m in web_metadata()])
    rows = conn.execute(
        "SELECT key, section, is_core, section_rank FROM bank_audit_statement_types "
        "ORDER BY section_rank, sort_order").fetchall()
    assert len(rows) == len(REGISTRY)
    assert [r[1] for r in rows] == sorted(
        (r[1] for r in rows), key=SECTION_ORDER.index), "not grouped by SECTION_ORDER"
    for key, section, is_core, rank in rows:
        assert (section, rank) == (BY_KEY[key].section, SECTION_ORDER.index(section))
        assert bool(is_core) == BY_KEY[key].is_core
