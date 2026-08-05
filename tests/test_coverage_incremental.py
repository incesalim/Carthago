"""bank_audit_coverage: from a full-rebuild rollup to a per-partition table.

It was the single largest line item in the 2026Q2 refresh — 161,272 estimated
billed rows to restate what eleven partitions' worth of change did to a ~20,000
row table. The existing content hash makes a NO-OP run free, but any change at
all paid for the whole thing.

Migration 0040 adds `derived_at`; sync_audit_expected stamps only rows whose
values moved and deletes keys the rebuild no longer produces; push_to_d1 windows
the table like every other bank_audit_* one.

The deletion half matters more than the saving. The delete-all this replaces is
what stopped D1 keeping a cell for a partition that has left the expected
universe, and losing that quietly would leave the coverage matrix showing rows
that no longer exist.

NOT YET ACTIVATED LIVE: migration 0040 is unapplied and no push has run with it.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.audit_reports.schema import init_schema  # noqa: E402


def _sync():
    spec = importlib.util.spec_from_file_location(
        "sae", REPO / "scripts" / "sync_audit_expected.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _push():
    spec = importlib.util.spec_from_file_location(
        "p2d_cov", REPO / "scripts" / "push_to_d1.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _db(tmp_path, name="cov.db"):
    conn = sqlite3.connect(tmp_path / name)
    init_schema(conn)
    return conn


def _row(bank="TEB", period="2026Q2", kind="consolidated",
         st="balance_sheet_assets", status="ok", rows=47, failed=0,
         manual=0, pdf=1):
    return (bank, period, kind, st, status, rows, failed, manual, pdf)


def test_the_schema_carries_the_stamp(tmp_path):
    conn = _db(tmp_path, "schema.db")
    cols = {c[1] for c in conn.execute("PRAGMA table_info(bank_audit_coverage)")}
    assert "derived_at" in cols


def test_migrations_replay_and_provide_derived_at():
    """Without 0040 the first windowed push fails on an unknown column."""
    conn = sqlite3.connect(":memory:")
    for f in sorted((REPO / "web" / "migrations").glob("*.sql")):
        conn.executescript(f.read_text(encoding="utf-8"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bank_audit_coverage)")}
    assert "derived_at" in cols, "migration 0040 missing — the push would fail"


def test_only_changed_rows_are_stamped(tmp_path):
    conn = _db(tmp_path, "inc.db")
    S = _sync()
    rows = [_row(st="balance_sheet_assets"), _row(st="profit_loss"),
            _row(st="cash_flow")]
    changed, gone = S.write_coverage(conn, rows)
    assert (changed, gone) == (3, 0)
    before = dict(conn.execute(
        "SELECT statement_type, derived_at FROM bank_audit_coverage"))

    # One cell moves; the other two are byte-identical.
    rows[1] = _row(st="profit_loss", status="error", failed=2)
    changed, gone = S.write_coverage(conn, rows)
    assert (changed, gone) == (1, 0), "only the moved cell may be written"
    after = dict(conn.execute(
        "SELECT statement_type, derived_at FROM bank_audit_coverage"))
    assert after["balance_sheet_assets"] == before["balance_sheet_assets"]
    assert after["cash_flow"] == before["cash_flow"]
    assert conn.execute(
        "SELECT status, checks_failed FROM bank_audit_coverage "
        "WHERE statement_type='profit_loss'").fetchone() == ("error", 2)


def test_a_no_op_rebuild_writes_nothing(tmp_path):
    conn = _db(tmp_path, "noop.db")
    S = _sync()
    rows = [_row(st=f"t{i}") for i in range(25)]
    S.write_coverage(conn, rows)
    assert S.write_coverage(conn, rows) == (0, 0)


def test_a_vanished_cell_is_deleted(tmp_path):
    """What the delete-all used to do. A partition that leaves the expected
    universe must not keep a coverage cell."""
    conn = _db(tmp_path, "del.db")
    S = _sync()
    S.write_coverage(conn, [_row(st="balance_sheet_assets"), _row(st="profit_loss")])
    changed, gone = S.write_coverage(conn, [_row(st="balance_sheet_assets")])
    assert (changed, gone) == (0, 1)
    assert [r[0] for r in conn.execute(
        "SELECT statement_type FROM bank_audit_coverage")] == ["balance_sheet_assets"]


def test_a_whole_partition_can_disappear(tmp_path):
    conn = _db(tmp_path, "delpart.db")
    S = _sync()
    S.write_coverage(conn, [_row(bank="TEB"), _row(bank="GONE")])
    changed, gone = S.write_coverage(conn, [_row(bank="TEB")])
    assert gone == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM bank_audit_coverage WHERE bank_ticker='GONE'"
    ).fetchone()[0] == 0


# --- the push side -----------------------------------------------------------

def test_the_incremental_push_is_prepared_but_NOT_active():
    """The switch is deliberately off. The windowed push reads `derived_at`, so
    D1 must have the column before the first incremental push, and migration
    0040 lands on the deploy that follows this commit. Flipping
    `_COVERAGE_INCREMENTAL` is the supervised activation."""
    P = _push()
    assert P._COVERAGE_INCREMENTAL is False
    assert "bank_audit_coverage" in P._FULL_REBUILD, (
        "activating before 0040 is applied would window on a column D1 lacks")
    assert "bank_audit_expected" in P._FULL_REBUILD, "the others are unchanged"
    assert "api_series" in P._FULL_REBUILD


def _activated(P):
    """The push module as it behaves once the switch is flipped."""
    P._FULL_REBUILD.discard("bank_audit_coverage")
    return P


def test_the_push_windows_coverage_on_its_stamp_once_activated(tmp_path):
    conn = _db(tmp_path, "win.db")
    S, P = _sync(), _activated(_push())
    S.write_coverage(conn, [_row(st="balance_sheet_assets"), _row(st="profit_loss")])
    # Age one row out of the window; the other stays fresh.
    conn.execute("UPDATE bank_audit_coverage SET derived_at = "
                 "datetime('now','-40 days') WHERE statement_type='profit_loss'")
    conn.commit()
    sql = "\n".join(P.fetch_recent(conn, "bank_audit_coverage", 24))
    assert "balance_sheet_assets" in sql
    assert "profit_loss" not in sql, "an unchanged, old row must not be re-shipped"


def test_a_null_stamp_is_out_of_window(tmp_path):
    """Rows written before 0040 carry NULL and are already in D1; re-shipping
    all of them on the first run after the migration would cost exactly what
    this change is removing."""
    conn = _db(tmp_path, "null.db")
    P = _activated(_push())
    conn.execute(
        "INSERT INTO bank_audit_coverage (bank_ticker, period, kind, "
        "statement_type, status, row_count, checks_failed, is_manual, pdf_present) "
        "VALUES ('TEB','2026Q1','consolidated','profit_loss','ok',60,0,0,1)")
    conn.commit()
    sql = "\n".join(P.fetch_recent(conn, "bank_audit_coverage", 24))
    assert "INSERT" not in sql


def test_while_inactive_the_full_rebuild_still_works(tmp_path):
    """Until the switch flips, behaviour must be exactly what shipped before —
    the incremental writer changes the staging table, not the push."""
    conn = _db(tmp_path, "inactive.db")
    S, P = _sync(), _push()
    S.write_coverage(conn, [_row(st="balance_sheet_assets"), _row(st="profit_loss")])
    sql = "\n".join(P.fetch_recent(conn, "bank_audit_coverage", 24,
                                   skip_unchanged=False))
    assert any(ln.startswith("DELETE FROM bank_audit_coverage") for ln in sql.split("\n")), \
        "a full rebuild must still clear the table first"
    assert "balance_sheet_assets" in sql and "profit_loss" in sql


def test_coverage_has_a_partition_key_so_the_scoped_delete_works(tmp_path):
    """Windowed pushes replace a partition with a scoped DELETE + INSERT. Without
    the key the push would append rather than replace."""
    conn = _db(tmp_path, "key.db")
    P = _push()
    assert P.has_partition_key(conn, "bank_audit_coverage")
