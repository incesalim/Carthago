"""The audit table list is derived, pushable, and never hand-copied.

Regression guard for the 2026-07-14 audit. refresh-audit.yml — the lane that
ingests every new quarter — hand-listed 14 of the 16 audit tables in
--only-tables. bank_audit_fx_position and bank_audit_repricing were extracted,
validated and written to the R2 snapshot on every run, and never pushed to D1:
/market-risk silently froze at the last manual backfill while every other audit
page advanced. push_to_d1 exited 0 throughout, because --only-tables was an
unvalidated filter over SYNC_TABLES — an omitted or misspelled table simply
matched nothing.

Each test below pins one link in that chain.
"""

import re
from pathlib import Path

import pytest

from push_to_d1 import SYNC_TABLES, resolve_tables
from src.audit_reports.registry import AUDIT_TABLES, INFRA_TABLES, REGISTRY

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
_ONLY_TABLES_RE = re.compile(r"--only-tables[=\s]+([A-Za-z0-9_,]+)")


def test_audit_tables_is_the_registry_plus_the_infra_pair():
    assert set(AUDIT_TABLES) == {st.table for st in REGISTRY} | set(INFRA_TABLES)
    assert len(AUDIT_TABLES) == len(set(AUDIT_TABLES)), "duplicate table in AUDIT_TABLES"


def test_every_audit_table_can_actually_be_pushed():
    """A table absent from SYNC_TABLES is extracted, stored and snapshotted — and
    never reaches D1. The failure is invisible: the push still exits 0."""
    orphans = [t for t in AUDIT_TABLES if t not in SYNC_TABLES]
    assert not orphans, (
        "in AUDIT_TABLES but not in push_to_d1.SYNC_TABLES — rows in these tables "
        f"would never reach D1: {orphans}"
    )


def test_table_set_audit_resolves_to_every_audit_table():
    resolved = resolve_tables(None, "audit")
    assert resolved == set(AUDIT_TABLES)
    # The two that went missing. Named explicitly so a future edit that drops
    # them from the registry fails here rather than in production.
    assert {"bank_audit_fx_position", "bank_audit_repricing"} <= resolved


def test_an_unknown_only_tables_name_is_a_hard_error():
    """The silent-ignore that hid the bug: a name that matches nothing used to
    push nothing and exit 0."""
    with pytest.raises(ValueError, match="cannot sync"):
        resolve_tables("bank_audit_balance_sheet,bank_audit_typo", None)


def test_table_set_and_only_tables_are_mutually_exclusive():
    with pytest.raises(ValueError, match="not both"):
        resolve_tables("bank_audit_capital", "audit")


def test_every_audit_table_is_routed_by_fetch_recent():
    """A table in SYNC_TABLES still won't push unless push_to_d1.fetch_recent knows
    which timestamp column to filter it by — else it hits the `else` branch and
    returns "no time column, skipped": 0 INSERTs, push exits 0, rows never arrive.

    This is the SECOND half of the fx_position bug (and how bank_audit_opinion
    first shipped empty): fetch_recent's per-table routing is hand-maintained and
    lived out of step with the registry. Every registered audit table must be
    routed — pin it so the next new table can't be silently dropped."""
    import sqlite3

    from push_to_d1 import fetch_recent
    from src.audit_reports.schema import init_schema

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    skipped = [
        t for t in AUDIT_TABLES
        if any("no time column, skipped" in s for s in fetch_recent(conn, t, 24))
    ]
    assert not skipped, (
        "push_to_d1.fetch_recent has no timestamp-column branch for these audit "
        f"tables — their rows would never reach D1: {skipped}"
    )


def test_no_workflow_hand_lists_the_audit_tables():
    """A workflow that pushes audit rows pushes ALL of them, via --table-set audit.
    A hand-written bank_audit_* subset in YAML is precisely the drift that caused
    this: the list cannot be kept in step with the registry by hand."""
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for match in _ONLY_TABLES_RE.finditer(wf.read_text(encoding="utf-8")):
            named = {t for t in match.group(1).split(",") if t.startswith("bank_audit_")}
            assert not named, (
                f"{wf.name} hand-lists bank_audit_* tables in --only-tables "
                f"({sorted(named)}) — use --table-set audit so the list cannot drift"
            )
