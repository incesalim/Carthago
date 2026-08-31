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
    conn.execute(f"CREATE TABLE {table} (id INTEGER, bank_ticker TEXT NOT NULL, "
                 "period TEXT NOT NULL, kind TEXT NOT NULL, item_order INTEGER NOT NULL, "
                 "amount REAL, source_page INTEGER, extracted_at TEXT, "
                 "PRIMARY KEY (bank_ticker,period,kind,item_order))")
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


def _install_extra_writer(remote, monkeypatch, calls):
    def write(sql_path, what):
        sql = Path(sql_path).read_text(encoding="utf-8")
        calls.append((what, sql))
        remote.executescript(sql)
        remote.commit()

    monkeypatch.setattr(repair, "retry_wrangler", write)


def test_remote_extra_mode_deletes_only_extra_primary_key(stores, monkeypatch):
    path, source, remote, writes, uploads = stores
    insert(source, [row(stamp="source-old"), row(item=2, amount=None)])
    insert(remote, [row(stamp="remote-preserve", identifier=999),
                    row(item=2, amount=None), row(item=3, amount=777)])
    calls = []
    _install_extra_writer(remote, monkeypatch, calls)
    before = path.read_bytes()
    args = ["--db", str(path), "--tables", TABLE, "--partitions",
            "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras", "--apply"]
    assert repair.main(args) == 0
    assert writes == uploads == []
    assert path.read_bytes() == before
    assert len(calls) == 1
    assert "DELETE FROM bank_audit_capital" in calls[0][1]
    assert "item_order IS 3" in calls[0][1]
    assert "amount IS 777" in calls[0][1]
    assert "INSERT" not in calls[0][1]
    # Ignored bookkeeping values on canonical facts are not rewritten.
    assert remote.execute(
        f"SELECT extracted_at,id FROM {TABLE} WHERE item_order=1"
    ).fetchone() == ("remote-preserve", 999)
    assert [r[0] for r in remote.execute(
        f"SELECT item_order FROM {TABLE} ORDER BY item_order"
    )] == [1, 2]
    assert repair.main(args) == 0
    assert len(calls) == 1


def test_remote_extra_dry_run_is_read_only(stores, monkeypatch):
    path, source, remote, writes, uploads = stores
    insert(source, [row()])
    insert(remote, [row(), row(item=2)])
    calls = []
    _install_extra_writer(remote, monkeypatch, calls)
    assert repair.main(["--db", str(path), "--tables", TABLE, "--partitions",
                        "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras"]) == 0
    assert calls == writes == uploads == []
    assert remote.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] == 2


def test_remote_extra_mode_aborts_on_changed_or_missing_canonical_fact(stores, monkeypatch):
    path, source, remote, writes, uploads = stores
    insert(source, [row(), row(item=2)])
    insert(remote, [row(amount=999), row(item=3)])
    calls = []
    _install_extra_writer(remote, monkeypatch, calls)
    with pytest.raises(ValueError, match="missing or differs"):
        repair.main(["--db", str(path), "--tables", TABLE, "--partitions",
                     "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras", "--apply"])
    assert calls == writes == uploads == []


def test_remote_extra_mode_preflights_all_tables_before_delete(stores, monkeypatch):
    path, source, remote, writes, uploads = stores
    for conn in (source, remote):
        create_table(conn, OTHER)
    insert(source, [row()])
    insert(remote, [row(), row(item=2)])
    insert(source, [row()], OTHER)
    insert(remote, [row(amount=999)], OTHER)
    calls = []
    _install_extra_writer(remote, monkeypatch, calls)
    with pytest.raises(ValueError, match="missing or differs"):
        repair.main(["--db", str(path), "--tables", f"{TABLE},{OTHER}", "--partitions",
                     "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras", "--apply"])
    assert calls == writes == uploads == []


def test_remote_extra_mode_postverify_catches_delete_failure(stores, monkeypatch):
    path, source, remote, _, uploads = stores
    insert(source, [row()])
    insert(remote, [row(), row(item=2)])
    monkeypatch.setattr(repair, "retry_wrangler", lambda *args: None)
    with pytest.raises(ValueError, match="Incomplete or changing rows"):
        repair.main(["--db", str(path), "--tables", TABLE, "--partitions",
                     "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras", "--apply"])
    assert uploads == []


def test_remote_extra_compare_and_delete_refuses_row_changed_after_preflight(stores, monkeypatch):
    path, source, remote, _, uploads = stores
    insert(source, [row()])
    insert(remote, [row(), row(item=2, amount=777)])

    def race(sql_path, what):
        remote.execute(f"UPDATE {TABLE} SET amount=778 WHERE item_order=2")
        remote.executescript(Path(sql_path).read_text(encoding="utf-8"))
        remote.commit()

    monkeypatch.setattr(repair, "retry_wrangler", race)
    with pytest.raises(ValueError, match="Incomplete or changing rows"):
        repair.main(["--db", str(path), "--tables", TABLE, "--partitions",
                     "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras", "--apply"])
    assert remote.execute(f"SELECT amount FROM {TABLE} WHERE item_order=2").fetchone() == (778.0,)
    assert uploads == []


@pytest.mark.parametrize("args", [
    ["--remove-remote-extras"],
    ["--remove-remote-extras", "--partitions", "ALL"],
    ["--remove-remote-extras", "--partitions", "AKBNK:2026Q2:unconsolidated",
     "--banks", "AKBNK"],
])
def test_remote_extra_mode_requires_only_exact_partition_scope(stores, args):
    path, _, _, writes, uploads = stores
    with pytest.raises(SystemExit):
        repair.main(["--db", str(path), "--tables", TABLE, *args])
    assert writes == uploads == []


def test_remote_extra_mode_refuses_primary_key_on_ignored_metadata(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.db"
    source = sqlite3.connect(path)
    remote = sqlite3.connect(":memory:")
    ddl = (f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY NOT NULL, bank_ticker TEXT NOT NULL, "
           "period TEXT NOT NULL, kind TEXT NOT NULL, item_order INTEGER, amount REAL)")
    source.execute(ddl)
    remote.execute(ddl)
    source.execute(f"INSERT INTO {TABLE} VALUES (1,'AKBNK','2026Q2','unconsolidated',1,42)")
    remote.execute(f"INSERT INTO {TABLE} VALUES (1,'AKBNK','2026Q2','unconsolidated',1,42)")
    remote.execute(f"INSERT INTO {TABLE} VALUES (2,'AKBNK','2026Q2','unconsolidated',2,43)")
    source.commit()
    remote.commit()
    monkeypatch.setattr(repair, "_remote", lambda sql: repair._rows(remote, sql))
    with pytest.raises(ValueError, match="Primary key does not contain the audit partition"):
        repair.main(["--db", str(path), "--tables", TABLE, "--partitions",
                     "AKBNK:2026Q2:unconsolidated", "--remove-remote-extras"])
    source.close()
    remote.close()
