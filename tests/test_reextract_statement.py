"""reextract_statement.py's statement-key mapping must cover every statement the
/admin coverage matrix can send (web/app/lib/github.ts STATEMENT_TYPES) so a
single-cell re-extract never dispatches a key the script rejects.
"""
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fitz")  # reextract_statement imports the extractor (fitz-only)

from reextract_statement import (  # noqa: E402
    STATEMENT_CHOICES, STATEMENT_TABLE, _is_proven_pass,
    _partition_content, _partition_snapshot, _restore_partition,
    _satisfies_candidate_gate, _upsert, resolve_statement_route,
    should_pull_snapshot,
)
from src.audit_reports import registry  # noqa: E402
from src.audit_reports.free_provision import FreeProvision  # noqa: E402
from src.audit_reports.extractor import StatementRow  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.units import UnitContext  # noqa: E402
from src.audit_reports.validator import ValidationResult  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def test_every_registered_statement_resolves_to_a_reextract_route():
    for st in registry.REGISTRY:
        lane, token, gates = resolve_statement_route(st.key)
        assert lane == st.key
        assert token in STATEMENT_TABLE
        assert st.key in STATEMENT_CHOICES
        assert gates == registry.validation_gate(st.key)


def test_relationship_routes_are_semantically_exact():
    assert resolve_statement_route("profile") == ("profile", "bank_profile", ("profile",))
    assert resolve_statement_route("bank_profile") == (
        "profile", "bank_profile", ("profile",))
    assert resolve_statement_route("stages") == (
        "stages", "credit_quality", ("credit_quality", "stages"))
    assert resolve_statement_route("balance_sheet_assets") == (
        "balance_sheet_assets", "bs_assets", ("assets", "liabilities", "cross"))


def test_web_allowlist_matches_repairable_registry_lanes():
    source = (REPO / "web" / "app" / "lib" / "github.ts").read_text(encoding="utf-8")
    block = source.split("export const STATEMENT_TYPES", 1)[1].split("]);", 1)[0]
    actual = set(re.findall(r'"([a-z_]+)"', block))
    expected = {st.key for st in registry.REGISTRY if st.key != "prose"}
    assert actual == expected


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
    assert _satisfies_candidate_gate(skipped_only, allow_conditional_na=True)
    assert not _satisfies_candidate_gate(failed, allow_conditional_na=True)


def test_partition_snapshot_restores_timestamp_and_facts_exactly():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE rows (bank_ticker TEXT, period TEXT, kind TEXT, "
        "item_order INTEGER, amount REAL, extracted_at TEXT)")
    conn.execute(
        "INSERT INTO rows VALUES ('AKBNK', '2026Q2', 'consolidated', "
        "1, 46, '2026-08-01')")
    snapshot = _partition_snapshot(
        conn, "rows", "AKBNK", "2026Q2", "consolidated")
    conn.execute("UPDATE rows SET amount=99, extracted_at='2026-08-07'")
    _restore_partition(
        conn, "rows", "AKBNK", "2026Q2", "consolidated", snapshot)
    assert conn.execute("SELECT amount, extracted_at FROM rows").fetchone() == (
        46, "2026-08-01")


def test_targeted_upsert_does_not_commit_away_candidate_savepoint():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    report = SimpleNamespace(free_provision=FreeProvision(
        free_provision=1_500_000, disclosed=True, source_page=61))
    conn.execute("SAVEPOINT candidate")
    _upsert(conn, "free_provision", "TEB", "2026Q2", "consolidated",
            report, unit=UnitContext.canonical())
    conn.execute("ROLLBACK TO candidate")
    conn.execute("RELEASE candidate")
    assert conn.execute("SELECT COUNT(*) FROM bank_audit_free_provision").fetchone()[0] == 0


def test_targeted_pl_rebuilds_roles_inside_the_candidate_savepoint():
    """A rejected numbering change must roll back both P&L and its role map."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)

    def report(hierarchy, amount):
        return SimpleNamespace(profit_loss=[StatementRow(
            order=1, hierarchy=hierarchy, name="DÖNEM NET KARI", footnote=None,
            cur_amount=amount)])

    _upsert(conn, "profit_loss", "TEST", "2026Q2", "unconsolidated",
            report("XXV.", 42), unit=UnitContext.canonical())
    conn.execute("UPDATE bank_audit_pl_roles SET derived_at='2026-01-01 00:00:00'")
    conn.commit()
    before = _partition_snapshot(
        conn, "bank_audit_pl_roles", "TEST", "2026Q2", "unconsolidated")
    conn.execute("SAVEPOINT candidate")
    _upsert(conn, "profit_loss", "TEST", "2026Q2", "unconsolidated",
            report("XXIV.", 99), unit=UnitContext.canonical())
    assert conn.execute("SELECT hierarchy, role FROM bank_audit_pl_roles").fetchall() == [
        ("XXIV.", "period_net")]
    conn.execute("ROLLBACK TO candidate")
    conn.execute("RELEASE candidate")
    assert _partition_snapshot(
        conn, "bank_audit_pl_roles", "TEST", "2026Q2", "unconsolidated") == before
    assert conn.execute("SELECT amount FROM bank_audit_profit_loss").fetchone() == (42,)


def test_role_only_repair_leaves_the_source_facts_and_role_timestamp_unchanged():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO bank_audit_profit_loss "
        "(bank_ticker, period, kind, item_order, hierarchy, item_name, amount) "
        "VALUES ('TEST','2026Q2','unconsolidated',1,'XXV.','DÖNEM NET KARI',42)")
    report = SimpleNamespace(profit_loss=[StatementRow(
        order=1, hierarchy="XXV.", name="DÖNEM NET KARI", footnote=None,
        cur_amount=42)])
    source_before = _partition_content(
        conn, "bank_audit_profit_loss", "TEST", "2026Q2", "unconsolidated")
    _upsert(conn, "profit_loss", "TEST", "2026Q2", "unconsolidated",
            report, unit=UnitContext.canonical())
    assert _partition_content(
        conn, "bank_audit_profit_loss", "TEST", "2026Q2", "unconsolidated") == source_before
    assert conn.execute("SELECT hierarchy, role FROM bank_audit_pl_roles").fetchall() == [
        ("XXV.", "period_net")]

    conn.execute("UPDATE bank_audit_pl_roles SET derived_at='2026-01-01 00:00:00'")
    _upsert(conn, "profit_loss", "TEST", "2026Q2", "unconsolidated",
            report, unit=UnitContext.canonical())
    assert conn.execute("SELECT derived_at FROM bank_audit_pl_roles").fetchone() == (
        "2026-01-01 00:00:00",)
