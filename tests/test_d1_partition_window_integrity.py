"""Windowed partition replacement must converge without deleting older facts.

Regression for the 2026-08-31 whole-filing refresh: a recent extraction log is
not proof an independently stamped table is empty, and one changed current row
must not discard its unchanged prior-period sibling.
"""
import sqlite3

import pytest

from scripts import push_to_d1 as push


TABLE_STAMPS = [
    ("bank_audit_capital", "extracted_at"),
    ("bank_audit_credit_quality", "extracted_at"),
    ("bank_audit_stages", "extracted_at"),
    ("bank_audit_profile", "extracted_at"),
    ("bank_audit_npl_movement", "extracted_at"),
    ("bank_audit_opinion", "extracted_at"),
    ("bank_audit_free_provision", "extracted_at"),
    ("bank_audit_liquidity", "extracted_at"),
    ("bank_audit_fx_position", "extracted_at"),
    ("bank_audit_repricing", "extracted_at"),
    ("bank_audit_pl_roles", "derived_at"),
    ("bank_audit_validation", "validated_at"),
    ("bank_audit_document_manifest", "captured_at"),
]


def copies(table, stamp):
    local = sqlite3.connect(":memory:")
    local.execute(f"CREATE TABLE {table} (bank_ticker TEXT,period TEXT,kind TEXT,"
                  f"item TEXT,amount REAL,{stamp} TEXT,"
                  "PRIMARY KEY(bank_ticker,period,kind,item))")
    local.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT,period TEXT,"
                  "kind TEXT,extracted_at TEXT)")
    # The primary source was repaired now; these independent lanes still hold
    # their already published facts from weeks ago.
    for bank in ("ZIRAAT", "ICBCT"):
        local.execute("INSERT INTO bank_audit_extractions VALUES (?,?,?,datetime('now'))",
                      (bank, "2026Q2", "unconsolidated"))
        local.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?)", [
            (bank, "2026Q2", "unconsolidated", "current", 15.17, "2000-01-01 00:00:00"),
            (bank, "2026Q2", "unconsolidated", "prior", 18.62, "2000-01-01 00:00:00"),
        ])
    remote = sqlite3.connect(":memory:")
    remote.executescript("\n".join(local.iterdump()))
    initial = push.partition_digests(local, table, "")
    push.record_partition_digests(local, table, initial,
                                  rows={key: 2 for key in initial})
    return local, remote


def rows(conn, table):
    return conn.execute(f"SELECT * FROM {table} ORDER BY bank_ticker,period,kind,item").fetchall()


def prepare(local, table):
    digests, rowcounts, dropped = {}, {}, {}
    statements = push.fetch_recent(local, table, 168, skip_partitions=True,
                                   digests=digests, rowcounts=rowcounts, dropped=dropped)
    return statements, digests, rowcounts, dropped


@pytest.mark.parametrize("table,stamp", TABLE_STAMPS)
def test_recent_filing_log_cannot_delete_an_intact_older_lane(table, stamp):
    local, remote = copies(table, stamp)
    before = rows(remote, table)
    statements, _, _, dropped = prepare(local, table)
    assert not any(s.startswith(("INSERT", "DELETE")) for s in statements)
    assert not dropped.get(table)
    remote.executescript("\n".join(statements))
    assert rows(remote, table) == before == rows(local, table)


@pytest.mark.parametrize("table,stamp", TABLE_STAMPS)
def test_one_current_row_change_preserves_old_prior_and_unrelated_bank(table, stamp):
    local, remote = copies(table, stamp)
    local.execute(f"UPDATE {table} SET amount=21.3,{stamp}=datetime('now') "
                  "WHERE bank_ticker='ICBCT' AND item='current'")
    local_before = rows(local, table)
    statements, digests, rowcounts, dropped = prepare(local, table)
    remote.executescript("\n".join(statements))
    assert rows(remote, table) == local_before
    assert rows(local, table) == local_before, "generating a push must not restamp source rows"
    assert set(digests[table]) == {"ICBCT|2026Q2|unconsolidated"}
    assert rowcounts[table] == {"ICBCT|2026Q2|unconsolidated": 2}
    assert not dropped.get(table)
    assert digests[table]["ICBCT|2026Q2|unconsolidated"] == push.partition_digests(
        local, table, "WHERE bank_ticker='ICBCT'")["ICBCT|2026Q2|unconsolidated"]


@pytest.mark.parametrize("table,stamp", TABLE_STAMPS[:-1])
def test_current_timestamp_only_change_does_not_resend_partial_partition(table, stamp):
    local, _ = copies(table, stamp)
    local.execute(f"UPDATE {table} SET {stamp}=datetime('now') "
                  "WHERE bank_ticker='ICBCT' AND item='current'")
    statements, _, _, dropped = prepare(local, table)
    assert not any(s.startswith(("INSERT", "DELETE")) for s in statements)
    assert not dropped.get(table)


@pytest.mark.parametrize("table,stamp", TABLE_STAMPS)
def test_actually_empty_touched_partition_still_deletes_only_that_partition(table, stamp):
    local, remote = copies(table, stamp)
    local.execute(f"DELETE FROM {table} WHERE bank_ticker='ICBCT'")
    statements, _, _, dropped = prepare(local, table)
    remote.executescript("\n".join(statements))
    assert rows(remote, table) == rows(local, table)
    assert dropped[table] == ["ICBCT|2026Q2|unconsolidated"]
    assert len(rows(remote, table)) == 2


def test_explicit_recovery_restores_old_facts_without_restamping_or_touching_other_bank():
    table = "bank_audit_capital"
    local, remote = copies(table, "extracted_at")
    remote.execute(f"DELETE FROM {table} WHERE bank_ticker='ICBCT'")
    before = rows(local, table)
    statements = push.fetch_recent(local, table, 1, digests={}, rowcounts={},
                                   replace={"ICBCT|2026Q2|unconsolidated"})
    remote.executescript("\n".join(statements))
    assert rows(remote, table) == before == rows(local, table)
    assert "ZIRAAT" not in "\n".join(statements)
