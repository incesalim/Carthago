"""Missing-row recovery must never turn a stale snapshot into an overwrite."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts import repair_missing_audit_rows as repair

TABLE = "bank_audit_capital"
OTHER = "bank_audit_credit_quality"
PART = ("AKBNK", "2026Q2", "unconsolidated")
SIBLING = ("AKBNK", "2026Q2", "consolidated")
OLDER = ("AKBNK", "2025Q4", "unconsolidated")
FIELDS = ("bank_ticker", "period", "kind", "item_order", "amount", "source_page")


def row(part=PART, item=1, amount=42, page=5, stamp="2020-01-01", identifier=1):
    return dict(zip(
        ("id", "bank_ticker", "period", "kind", "item_order", "amount", "source_page", "extracted_at"),
        (identifier, *part, item, amount, page, stamp),
    ))


def create_table(conn, table=TABLE):
    conn.execute(f"CREATE TABLE {table} (id INTEGER, bank_ticker TEXT, period TEXT, kind TEXT, "
                 "item_order INTEGER, amount REAL, source_page INTEGER, extracted_at TEXT)")
    conn.commit()


def insert(conn, rows, table=TABLE):
    for r in rows:
        conn.execute(f"INSERT INTO {table} ({','.join(r)}) VALUES ({','.join('?' for _ in r)})",
                     tuple(r.values()))
    conn.commit()


@pytest.fixture
def stores(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.db"
    source = sqlite3.connect(path)
    remote = sqlite3.connect(":memory:")
    for conn in (source, remote):
        create_table(conn)
    monkeypatch.setattr(repair, "_remote", lambda sql: repair._rows(remote, sql))
    writes, uploads = [], []

    def push(args, check):
        assert check is True
        assert "--replace-partitions" in args
        assert "--hours" not in args
        table = args[args.index("--only-tables") + 1]
        assert "," not in table
        listing = Path(args[args.index("--replace-partitions") + 1])
        parts = [tuple(line.split("|")) for line in listing.read_text().splitlines()]
        writes.append((table, parts))
        for part in parts:
            scope = repair._part_scope([part])
            remote.execute(f"DELETE FROM {table} WHERE {scope}")
            insert(remote, repair._rows(source, f"SELECT * FROM {table} WHERE {scope}"), table)

    monkeypatch.setattr(repair.subprocess, "run", push)
    monkeypatch.setattr(repair, "push_snapshot", lambda db: uploads.append(db))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    yield path, source, remote, writes, uploads
    source.close()
    remote.close()


def test_multiset_does_not_hide_extra_duplicate():
    with pytest.raises(ValueError, match="extra facts"):
        repair.missing_rows([row(), row(item=2)], [row(), row()], FIELDS)


@pytest.mark.parametrize("bad", [
    row(amount=0), row(amount=43), row(page=6), row(item=3),
])
def test_every_factual_column_and_null_are_preserved(bad):
    source = [row(amount=None), row(item=2)]
    with pytest.raises(ValueError, match="differing or extra"):
        repair.missing_rows(source, [bad], FIELDS)


def test_null_and_zero_are_two_separate_missing_facts():
    assert repair.missing_rows([row(amount=None), row(amount=0)], [row(amount=None)], FIELDS) == 1


def test_metadata_differences_do_not_prevent_safe_subset(stores):
    _, source, remote, _, _ = stores
    insert(source, [row(), row(item=2, amount=None)])
    insert(remote, [row(stamp="2026-09-01", identifier=999)])
    plan = repair.plan_repairs(source, [TABLE], "1=1")
    assert len(plan) == 1 and plan[0].missing_rows == 1
    assert "id" not in plan[0].columns and "extracted_at" not in plan[0].columns
    assert "source_page" in plan[0].columns


def test_dry_run_finds_whole_and_partial_loss_without_writes(stores):
    path, source, remote, writes, uploads = stores
    insert(source, [row(), row(item=2), row(OLDER)])
    insert(remote, [row()])
    before = path.read_bytes()
    assert repair.main(["--db", str(path), "--tables", TABLE]) == 0
    assert writes == uploads == []
    assert path.read_bytes() == before


def test_apply_restores_older_siblings_preserves_other_kind_and_is_idempotent(stores):
    path, source, remote, writes, uploads = stores
    # The missing row is older than every normal push window; the surviving row
    # and other kind must remain exactly source-faithful including stamps.
    insert(source, [row(stamp="2026-09-01"), row(item=2, amount=None), row(SIBLING, amount=84)])
    insert(remote, [row(stamp="2026-09-01"), row(SIBLING, amount=84)])
    args = ["--db", str(path), "--tables", TABLE, "--apply"]
    before = path.read_bytes()
    assert repair.main(args) == 0
    assert writes == [(TABLE, [PART])]
    assert uploads == [path]
    assert path.read_bytes() == before  # no source re-stamping
    assert repair._rows(remote, f"SELECT * FROM {TABLE} ORDER BY kind,item_order") == repair._rows(
        source, f"SELECT * FROM {TABLE} ORDER BY kind,item_order")
    assert repair.main(args) == 0
    assert writes == [(TABLE, [PART])] and uploads == [path]


def test_table_scopes_do_not_form_cartesian_union(stores):
    path, source, remote, writes, _ = stores
    for conn in (source, remote):
        create_table(conn, OTHER)
    insert(source, [row(), row(SIBLING)])
    insert(remote, [row(SIBLING)])
    insert(source, [row(), row(SIBLING)], OTHER)
    insert(remote, [row()], OTHER)
    repair.main(["--db", str(path), "--tables", f"{TABLE},{OTHER}", "--apply"])
    assert writes == [(TABLE, [PART]), (OTHER, [SIBLING])]


def test_later_conflict_aborts_before_earlier_valid_plan_writes(stores):
    path, source, remote, writes, uploads = stores
    for conn in (source, remote):
        create_table(conn, OTHER)
    insert(source, [row()])  # first table is wholly missing and safe to restore
    insert(source, [row(), row(item=2)], OTHER)
    insert(remote, [row(amount=999)], OTHER)
    with pytest.raises(ValueError, match="differing or extra"):
        repair.main(["--db", str(path), "--tables", f"{TABLE},{OTHER}", "--apply"])
    assert writes == uploads == []


def test_remote_only_partition_aborts(stores):
    path, source, remote, writes, uploads = stores
    insert(source, [row()])
    insert(remote, [row(OLDER)])
    with pytest.raises(ValueError, match="extra facts"):
        repair.main(["--db", str(path), "--tables", TABLE, "--apply"])
    assert writes == uploads == []


def test_missing_snapshot_table_is_refused_before_any_write(stores):
    path, source, remote, writes, uploads = stores
    create_table(remote, OTHER)
    insert(source, [row()])
    with pytest.raises(ValueError, match="Missing snapshot/D1 table"):
        repair.main(["--db", str(path), "--tables", f"{TABLE},{OTHER}", "--apply"])
    assert writes == uploads == []


def test_added_nullable_fact_requires_schema_migration(stores):
    _, source, remote, _, _ = stores
    remote.execute(f"ALTER TABLE {TABLE} ADD COLUMN new_fact REAL")
    with pytest.raises(ValueError, match="schema differs"):
        repair.plan_repairs(source, [TABLE], "1=1")


@pytest.mark.parametrize("attribute,value", [("type", "TEXT"), ("pk", 1), ("notnull", 1)])
def test_type_primary_key_and_nullability_drift_fail_preflight(stores, monkeypatch, attribute, value):
    path, source, remote, writes, uploads = stores
    insert(source, [row()])

    def read(sql):
        rows = repair._rows(remote, sql)
        if sql.startswith("PRAGMA"):
            for column in rows:
                if column["name"] == "amount":
                    column[attribute] = value
        return rows

    monkeypatch.setattr(repair, "_remote", read)
    with pytest.raises(ValueError, match="primary key differs|type/nullability differs"):
        repair.main(["--db", str(path), "--tables", TABLE, "--apply"])
    assert writes == uploads == []


def test_truncated_grouped_count_is_not_missing_partition(stores, monkeypatch):
    _, source, remote, _, _ = stores
    insert(source, [row(), row(OLDER)])
    insert(remote, [row(), row(OLDER)])

    def read(sql):
        rows = repair._rows(remote, sql)
        return rows[:1] if "GROUP BY" in sql else rows

    monkeypatch.setattr(repair, "_remote", read)
    with pytest.raises(ValueError, match="Incomplete or changing grouped counts"):
        repair.plan_repairs(source, [TABLE], "1=1")


def test_truncated_row_fetch_is_not_missing_fact(stores, monkeypatch):
    _, source, remote, _, _ = stores
    insert(source, [row(), row(item=2), row(item=3)])
    insert(remote, [row(), row(item=2)])

    def read(sql):
        rows = repair._rows(remote, sql)
        return rows[:1] if " IN (VALUES " in sql else rows

    monkeypatch.setattr(repair, "_remote", read)
    with pytest.raises(ValueError, match="Incomplete or changing rows"):
        repair.plan_repairs(source, [TABLE], "1=1")


def test_post_apply_conflict_prevents_snapshot_upload(stores, monkeypatch):
    path, source, remote, _, uploads = stores
    insert(source, [row()])

    def broken_push(*args, **kwargs):
        insert(remote, [row(amount=999)])

    monkeypatch.setattr(repair.subprocess, "run", broken_push)
    with pytest.raises(RuntimeError, match="Post-repair facts differ"):
        repair.main(["--db", str(path), "--tables", TABLE, "--apply"])
    assert uploads == []


def test_equal_count_rows_are_not_replaced_by_a_stale_snapshot(stores):
    path, source, remote, writes, uploads = stores
    insert(source, [row()])
    insert(remote, [row(amount=43)])
    repair.main(["--db", str(path), "--tables", TABLE, "--apply"])
    assert writes == uploads == []


def test_explicit_bank_period_kind_scope_is_preserved(stores):
    path, source, remote, writes, _ = stores
    insert(source, [row(), row(OLDER), row(SIBLING)])
    # Extra remote facts outside the requested scope are not this repair's own.
    insert(remote, [row(OLDER, amount=999)])
    repair.main(["--db", str(path), "--tables", TABLE, "--banks", "AKBNK",
                 "--periods", "2026Q2", "--kind", "unconsolidated", "--apply"])
    assert writes == [(TABLE, [PART])]


def test_apply_is_actions_only(stores, monkeypatch):
    path, _, _, writes, uploads = stores
    monkeypatch.delenv("GITHUB_ACTIONS")
    with pytest.raises(SystemExit):
        repair.main(["--db", str(path), "--tables", TABLE, "--apply"])
    assert writes == uploads == []


@pytest.mark.parametrize("table", ["ALL", "bank_audit_source_lines", "bank_audit_expected",
                                   "bank_audit_capital;DELETE FROM bank_audit_capital"])
def test_only_reviewed_partition_tables_are_allowed(stores, table):
    path, _, _, writes, uploads = stores
    with pytest.raises(SystemExit):
        repair.main(["--db", str(path), "--tables", table, "--apply"])
    assert writes == uploads == []


@pytest.mark.parametrize("response", [[], [{"success": False, "results": []}],
                                       [{"success": True}], [{"success": 1, "results": []}]])
def test_remote_transport_failure_is_never_empty_data(monkeypatch, response):
    monkeypatch.setattr(repair, "_wrangler_json", lambda *args: response)
    with pytest.raises(RuntimeError, match="successful read"):
        repair._remote("SELECT 1")
