"""bank_audit_coverage: from a full-rebuild rollup to a per-partition table.

It was the single largest line item in the 2026Q2 refresh — 161,272 estimated
billed rows to restate what eleven partitions' worth of change did to a ~20,000
row table. The existing content hash makes a NO-OP run free, but any change at
all paid for the whole thing.

Migration 0040 adds `derived_at`; sync_audit_expected stamps only rows whose
values moved and deletes keys the rebuild no longer produces; push_to_d1 windows
the table like every other bank_audit_* one.

The deletion half matters more than the saving, and deleting LOCALLY is not
enough: the push carries rows by `derived_at`, so a removed cell has no row and
therefore no stamp, and an upsert-only window can never express its removal.
Removals travel through the `d1_pending_deletes` outbox as full-primary-key
statements. Partition-scoped replacement is not an option here — this table
stamps CELLS, and replacing a partition while re-inserting only the stamped
cells would erase every unchanged sibling in it.

STATE: ACTIVE. Migration 0040 is applied in live D1 (deploy 31045271052,
2026-08-05) and `_COVERAGE_INCREMENTAL` was enabled 2026-08-06, after the full
rebuild breached the 250,000 run cap on the PASHA extraction — asking 161,728
rows to restate a table that had barely changed, and stranding the snapshot
upload behind the resulting failure.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

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


def test_manual_coverage_refresh_saves_snapshot_only_after_d1(tmp_path, monkeypatch):
    S = _sync()
    db = tmp_path / "snapshot-order.db"
    order = []
    monkeypatch.setattr(S, "build", lambda conn, use_r2: ([], [], []))
    monkeypatch.setattr(S, "write", lambda *args: None)
    monkeypatch.setattr(S.subprocess, "run",
                        lambda *args, **kwargs: order.append("d1"))
    from scripts import audit_d1
    monkeypatch.setattr(audit_d1, "ensure_d1_schema", lambda: order.append("schema"))
    monkeypatch.setattr(audit_d1, "push_snapshot",
                        lambda path: order.append(("snapshot", Path(path))))
    monkeypatch.setattr(sys, "argv", ["sync_audit_expected.py", "--db", str(db),
                                      "--push", "--save-snapshot", "--no-r2"])
    assert S.main() == 0
    assert order == ["schema", "d1", ("snapshot", db)]


def test_manual_mutation_workflows_persist_post_coverage_snapshot():
    for name in ("backfill-audit-source-capture.yml", "reextract-statement.yml",
                 "purge-partition.yml"):
        workflow = (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "sync_audit_expected.py --push --save-snapshot" in workflow


def test_dry_run_refuses_every_remote_write_flag(monkeypatch):
    S = _sync()
    monkeypatch.setattr(sys, "argv", ["sync_audit_expected.py", "--dry-run",
                                      "--push", "--save-snapshot"])
    with pytest.raises(SystemExit):
        S.main()


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

def test_the_incremental_push_is_ACTIVE():
    """Enabled 2026-08-06, once migration 0040 was applied in live D1 — the one
    ordering constraint. The full rebuild had by then become actively harmful:
    it asked for 161,728 rows to restate a table that had barely changed,
    breached the 250,000 run cap and stranded the snapshot upload."""
    P = _push()
    assert P._COVERAGE_INCREMENTAL is True
    assert "bank_audit_coverage" not in P._FULL_REBUILD
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


def test_the_windowed_push_carries_only_what_changed(tmp_path):
    """The point of the switch: a run that moves two cells ships two cells, not
    the whole ~20,000-row table."""
    conn = _db(tmp_path, "active.db")
    S, P = _sync(), _push()
    S.write_coverage(conn, [_row(st=f"stmt_{i}") for i in range(8)])
    # Age them all out, then move exactly one.
    conn.execute("UPDATE bank_audit_coverage SET derived_at = datetime('now','-40 days')")
    conn.commit()
    S.write_coverage(conn, [_row(st=f"stmt_{i}") for i in range(7)]
                     + [_row(st="stmt_7", status="error", failed=2)])
    lines = P.fetch_recent(conn, "bank_audit_coverage", 24)
    sql = "\n".join(lines)
    assert "stmt_7" in sql
    assert "stmt_0" not in sql, "an unchanged cell was re-shipped"
    assert not any(ln.strip().startswith("DELETE FROM bank_audit_coverage;")
                   for ln in lines), "no table-wide DELETE any more"


def test_coverage_has_a_partition_key_so_the_scoped_delete_works(tmp_path):
    """Windowed pushes replace a partition with a scoped DELETE + INSERT. Without
    the key the push would append rather than replace."""
    conn = _db(tmp_path, "key.db")
    P = _push()
    assert P.has_partition_key(conn, "bank_audit_coverage")


# --- convergence against a SIMULATED REMOTE ----------------------------------
#
# Local deletion alone does not reach D1. The push carries rows by `derived_at`,
# and a removed cell has no row and therefore no stamp — so an upsert-only
# window can never express its removal. These tests execute the SQL the push
# would actually send into a second SQLite standing in for D1, and assert the
# only thing that matters: remote == local, exactly.


def _remote(tmp_path, name="remote.db"):
    """A stand-in for D1, built from the real migrations."""
    r = sqlite3.connect(tmp_path / name)
    for f in sorted((REPO / "web" / "migrations").glob("*.sql")):
        r.executescript(f.read_text(encoding="utf-8"))
    return r


def _ship(local, remote, P):
    """Replay what push_to_d1.main() sends, in its order: outbox deletes first
    (so D1 cannot keep orphans the upsert would never touch), then the window."""
    pending = local.execute(
        "SELECT rowid, sql FROM d1_pending_deletes ORDER BY rowid").fetchall()
    for _, stmt in pending:
        # Every queued statement must survive the push's own single-row proof,
        # or main() refuses the whole push rather than replay it.
        assert P.outbox_delete_rows(local, stmt) is not None, \
            f"outbox statement not provably single-row: {stmt!r}"
        remote.executescript(stmt)
    for stmt in P.fetch_recent(local, "bank_audit_coverage", 24):
        if stmt.startswith(("INSERT", "DELETE")):
            remote.executescript(stmt)
    remote.commit()
    local.executemany("DELETE FROM d1_pending_deletes WHERE rowid = ?",
                      [(rid,) for rid, _ in pending])
    local.commit()


def _cells(conn):
    return sorted(conn.execute(
        "SELECT bank_ticker, period, kind, statement_type, status, row_count, "
        "checks_failed, is_manual, pdf_present FROM bank_audit_coverage"))


def test_removing_one_cell_removes_it_remotely(tmp_path):
    local, remote = _db(tmp_path, "l1.db"), _remote(tmp_path, "r1.db")
    S, P = _sync(), _activated(_push())
    S.write_coverage(local, [_row(st="balance_sheet_assets"), _row(st="profit_loss")])
    _ship(local, remote, P)
    assert len(_cells(remote)) == 2

    S.write_coverage(local, [_row(st="balance_sheet_assets")])
    _ship(local, remote, P)
    assert [c[3] for c in _cells(remote)] == ["balance_sheet_assets"]
    assert _cells(remote) == _cells(local)


def test_removing_a_whole_partition_removes_it_remotely(tmp_path):
    local, remote = _db(tmp_path, "l2.db"), _remote(tmp_path, "r2.db")
    S, P = _sync(), _activated(_push())
    S.write_coverage(local, [
        _row(bank="TEB", st="balance_sheet_assets"), _row(bank="TEB", st="profit_loss"),
        _row(bank="GONE", st="balance_sheet_assets"), _row(bank="GONE", st="profit_loss")])
    _ship(local, remote, P)
    assert len({c[0] for c in _cells(remote)}) == 2

    S.write_coverage(local, [_row(bank="TEB", st="balance_sheet_assets"),
                             _row(bank="TEB", st="profit_loss")])
    _ship(local, remote, P)
    assert {c[0] for c in _cells(remote)} == {"TEB"}
    assert _cells(remote) == _cells(local)


def test_changing_one_cell_does_not_erase_its_unchanged_siblings(tmp_path):
    """THE trap in doing this with partition mode: a partition-scoped DELETE
    plus a re-insert of only the stamped cells drops every sibling."""
    local, remote = _db(tmp_path, "l3.db"), _remote(tmp_path, "r3.db")
    S, P = _sync(), _activated(_push())
    siblings = [_row(st=f"stmt_{i}") for i in range(6)]
    S.write_coverage(local, siblings)
    _ship(local, remote, P)
    assert len(_cells(remote)) == 6

    moved = list(siblings)
    moved[2] = _row(st="stmt_2", status="error", failed=3)
    S.write_coverage(local, moved)
    _ship(local, remote, P)
    assert len(_cells(remote)) == 6, "unchanged siblings were erased"
    assert remote.execute(
        "SELECT status, checks_failed FROM bank_audit_coverage "
        "WHERE statement_type='stmt_2'").fetchone() == ("error", 3)
    assert _cells(remote) == _cells(local)


def test_remote_equals_local_after_a_mixed_sequence(tmp_path):
    """Adds, edits and removals interleaved — the only assertion that matters."""
    local, remote = _db(tmp_path, "l4.db"), _remote(tmp_path, "r4.db")
    S, P = _sync(), _activated(_push())
    rounds = [
        [_row(bank="TEB", st="a"), _row(bank="TEB", st="b"), _row(bank="AKBNK", st="a")],
        [_row(bank="TEB", st="a", status="error", failed=1),
         _row(bank="TEB", st="b"), _row(bank="AKBNK", st="a"), _row(bank="AKBNK", st="b")],
        [_row(bank="TEB", st="a", status="error", failed=1), _row(bank="AKBNK", st="b")],
        [_row(bank="GARAN", st="c")],
    ]
    for rows in rounds:
        S.write_coverage(local, rows)
        _ship(local, remote, P)
        assert _cells(remote) == _cells(local), (
            f"diverged after {len(rows)} rows:\n  local ={_cells(local)}\n"
            f"  remote={_cells(remote)}")
    assert [c[0] for c in _cells(remote)] == ["GARAN"]


def test_a_queued_delete_is_priced_and_provable(tmp_path):
    """An unbounded statement would blow the budget while the guard priced it as
    one row, so main() refuses to replay anything it cannot prove."""
    local = _db(tmp_path, "l5.db")
    S, P = _sync(), _push()
    S.write_coverage(local, [_row(st="a"), _row(st="b")])
    S.write_coverage(local, [_row(st="a")])
    queued = [r[0] for r in local.execute("SELECT sql FROM d1_pending_deletes")]
    assert len(queued) == 1
    assert P.outbox_delete_rows(local, queued[0]) == ("bank_audit_coverage", 1)


def test_coverage_can_never_enter_partition_mode(tmp_path):
    """Cell-level stamping and partition-level replacement are incompatible.
    Even if a caller passes --skip-unchanged-partitions, coverage must not be
    swept in — that is what would erase unchanged siblings."""
    P = _push()
    assert "bank_audit_coverage" in P._NO_PARTITION_SKIP
    from src.audit_reports.registry import AUDIT_TABLES
    assert "bank_audit_coverage" not in AUDIT_TABLES, \
        "the --table-set audit push passes --skip-unchanged-partitions"
