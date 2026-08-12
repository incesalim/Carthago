"""Never re-stamp a row whose values did not change (AGENTS.md).

The 2026Q2 audit refresh wrote 306,647 rows to D1. Only ~13.7k of that was the
new quarter. The rest was three derived tables rewritten wholesale on every run:
`upsert_validation` and `upsert_pl_roles` did an unconditional DELETE+INSERT,
and `build_stages` wiped its table and re-inserted it. All three carry a stamp
column (`validated_at` / `derived_at` / `extracted_at`) that defaults to
CURRENT_TIMESTAMP, and `push_to_d1` windows on exactly those columns — so
rewriting an identical row is not free, it is a full re-ship to D1.

Measured on the real snapshot before the fix: a second, NOTHING-CHANGED pass
re-stamped 19,950 validation rows and 9,439 pl_roles rows. After: zero.

These tests pin both halves — the skip, and that a genuinely changed verdict is
still written. A skip that also swallowed real changes would be far worse than
the cost it saves.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.audit_reports import validator as V  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402


def _db(tmp_path, name="amp.db"):
    conn = sqlite3.connect(tmp_path / name)
    init_schema(conn)
    return conn


def _result(passed=3, failed=0, skipped=1):
    r = V.ValidationResult()
    for _ in range(passed):
        r.add_pass()
    for _ in range(skipped):
        r.add_skip()
    for i in range(failed):
        r.add_fail("chk", f"node {i}", expected=1, actual=2)
    return r


def _stamps(conn, table, col):
    return [r[0] for r in conn.execute(f"SELECT {col} FROM {table} ORDER BY rowid")]


# --- validation --------------------------------------------------------------

def test_an_unchanged_verdict_is_not_rewritten(tmp_path):
    conn = _db(tmp_path)
    res = {"assets": _result(), "profit_loss": _result(failed=2)}
    assert V.upsert_validation(conn, "TEB", "2026Q2", "consolidated", res) is True
    before = _stamps(conn, "bank_audit_validation", "validated_at")
    time.sleep(1.1)                       # sqlite CURRENT_TIMESTAMP is 1s-grained
    assert V.upsert_validation(conn, "TEB", "2026Q2", "consolidated", res) is False
    assert _stamps(conn, "bank_audit_validation", "validated_at") == before, \
        "validated_at moved, so push_to_d1's --hours window would re-ship the row"


@pytest.mark.parametrize("changed", [
    {"assets": _result(passed=4)},                    # a check started passing
    {"assets": _result(failed=1)},                    # a check started failing
    {"assets": _result(), "oci": _result()},          # a statement appeared
])
def test_a_changed_verdict_is_always_written(tmp_path, changed):
    conn = _db(tmp_path, "chg.db")
    V.upsert_validation(conn, "TEB", "2026Q2", "consolidated", {"assets": _result()})
    assert V.upsert_validation(conn, "TEB", "2026Q2", "consolidated", changed) is True
    stored = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
        "SELECT statement, checks_passed, checks_failed, checks_skipped "
        "FROM bank_audit_validation")}
    assert set(stored) == set(changed)
    for stmt, r in changed.items():
        assert stored[stmt] == (r.passed, r.failed, r.skipped)


def test_a_changed_failure_detail_alone_still_writes(tmp_path):
    """The counts can match while the failing NODE differs — a different check
    failing the same number of times is a different verdict."""
    conn = _db(tmp_path, "det.db")
    a = V.ValidationResult(); a.add_fail("chk", "assets row 1", expected=1, actual=2)
    b = V.ValidationResult(); b.add_fail("chk", "assets row 9", expected=1, actual=2)
    assert a.passed == b.passed and a.failed == b.failed
    V.upsert_validation(conn, "T", "2026Q2", "c", {"assets": a})
    assert V.upsert_validation(conn, "T", "2026Q2", "c", {"assets": b}) is True
    detail = conn.execute(
        "SELECT failed_detail FROM bank_audit_validation").fetchone()[0]
    assert "assets row 9" in json.loads(detail)[0]["node"]


def test_the_first_write_of_a_partition_always_happens(tmp_path):
    conn = _db(tmp_path, "first.db")
    assert V.upsert_validation(conn, "NEW", "2026Q2", "c", {"assets": _result()}) is True
    assert conn.execute("SELECT COUNT(*) FROM bank_audit_validation").fetchone()[0] == 1


# --- pl_roles ----------------------------------------------------------------

_PL = [{"hierarchy": "I.", "item_name": "FAİZ GELİRLERİ", "amount": 10.0},
       {"hierarchy": "XVII.", "item_name": "DÖNEM NET KÂRI", "amount": 5.0}]


def test_an_unchanged_role_map_is_not_rewritten(tmp_path):
    conn = _db(tmp_path, "roles.db")
    V.upsert_pl_roles(conn, "TEB", "2026Q2", "c", _PL)
    before = _stamps(conn, "bank_audit_pl_roles", "derived_at")
    assert before, "fixture produced no roles — the test would prove nothing"
    time.sleep(1.1)
    V.upsert_pl_roles(conn, "TEB", "2026Q2", "c", _PL)
    assert _stamps(conn, "bank_audit_pl_roles", "derived_at") == before


def test_a_changed_role_map_is_written(tmp_path):
    conn = _db(tmp_path, "roles2.db")
    V.upsert_pl_roles(conn, "TEB", "2026Q2", "c", _PL)
    before = {tuple(r) for r in conn.execute(
        "SELECT hierarchy, role FROM bank_audit_pl_roles")}
    moved = [dict(_PL[0]), {"hierarchy": "XVI.", "item_name": "DÖNEM NET KÂRI",
                            "amount": 5.0}]
    V.upsert_pl_roles(conn, "TEB", "2026Q2", "c", moved)
    after = {tuple(r) for r in conn.execute(
        "SELECT hierarchy, role FROM bank_audit_pl_roles")}
    assert after != before, "the compressed-template roman shift must be stored"


# --- stages ------------------------------------------------------------------

def _stages_mod():
    spec = importlib.util.spec_from_file_location(
        "stg", REPO / "scripts" / "build_bank_audit_stages.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _seed_cq(conn, total=100.0):
    conn.execute("DELETE FROM bank_audit_credit_quality")
    conn.executemany(
        "INSERT INTO bank_audit_credit_quality (bank_ticker, period, kind, section,"
        " period_type, stage1_amount, stage2_amount, stage3_amount, total_amount,"
        " source_page) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [("TEB", "2026Q2", "consolidated", "loans_amounts", "current",
          total, 20.0, 30.0, total + 50.0, 5)])
    conn.commit()


def test_stages_rebuild_is_incremental(tmp_path):
    conn = _db(tmp_path, "stg.db")
    _seed_cq(conn)
    ST = _stages_mod()
    ST.build_stages(conn)
    before = _stamps(conn, "bank_audit_stages", "extracted_at")
    assert before, "no stage rows built — the test would prove nothing"
    time.sleep(1.1)
    ST.build_stages(conn)
    assert _stamps(conn, "bank_audit_stages", "extracted_at") == before, \
        "an unchanged derived row was re-stamped and would re-ship"


def test_stages_still_reflects_a_real_change(tmp_path):
    conn = _db(tmp_path, "stg2.db")
    _seed_cq(conn, total=100.0)
    ST = _stages_mod()
    ST.build_stages(conn)
    _seed_cq(conn, total=999.0)
    ST.build_stages(conn)
    assert conn.execute(
        "SELECT stage1_amount FROM bank_audit_stages").fetchone()[0] == 999.0


def test_stages_removes_a_row_whose_source_disappeared(tmp_path):
    """The delete-all this replaced was what removed vanished rows. Losing that
    silently would leave a stale derived row behind for ever."""
    conn = _db(tmp_path, "stg3.db")
    _seed_cq(conn)
    ST = _stages_mod()
    ST.build_stages(conn)
    assert conn.execute("SELECT COUNT(*) FROM bank_audit_stages").fetchone()[0] == 1
    conn.execute("DELETE FROM bank_audit_credit_quality")
    conn.commit()
    ST.build_stages(conn)
    assert conn.execute("SELECT COUNT(*) FROM bank_audit_stages").fetchone()[0] == 0


def test_partition_stage_rebuild_obeys_candidate_savepoint(tmp_path):
    """Targeted repair must judge derived stages before acceptance and be able
    to roll both source and derived rows back together."""
    conn = _db(tmp_path, "stg_savepoint.db")
    _seed_cq(conn, total=100.0)
    ST = _stages_mod()
    ST.build_stages(conn)
    conn.execute("SAVEPOINT candidate")
    conn.execute(
        "UPDATE bank_audit_credit_quality SET stage1_amount=999 "
        "WHERE bank_ticker='TEB' AND period='2026Q2' AND kind='consolidated'")
    assert ST.rebuild_stages_partition(
        conn, "TEB", "2026Q2", "consolidated") == 1
    assert conn.execute(
        "SELECT stage1_amount FROM bank_audit_stages").fetchone()[0] == 999.0
    conn.execute("ROLLBACK TO candidate")
    conn.execute("RELEASE candidate")
    assert conn.execute(
        "SELECT stage1_amount FROM bank_audit_stages").fetchone()[0] == 100.0


# --- the run ledger is gone (2026-08-12) -------------------------------------
#
# Four tests lived here pinning that a cap bounded the RUN and not each
# invocation — the 203,799-then-226,069 case where two pushes each passed a
# 250,000 ceiling and the run spent 429,868. There is no cap to bound anything
# now, so they were removed with the guard rather than left asserting on
# symbols that no longer exist.
#
# The rest of this file matters MORE for that, not less: every test above and
# below is about not GENERATING a write that changed nothing, which is the only
# mechanism still holding the bill down.

def _push_mod():
    spec = importlib.util.spec_from_file_location(
        "p2d_amp", REPO / "scripts" / "push_to_d1.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_nothing_in_the_push_path_reads_a_run_ledger():
    """A leftover D1_RUN_LEDGER in an environment must be inert, not
    half-honoured. Reading it without a cap to apply it to would be worse than
    ignoring it: the file would grow and mean nothing."""
    P = _push_mod()
    for gone in ("RUN_LEDGER_ENV", "run_ledger_spent", "run_ledger_add",
                 "effective_cap", "D1_MONTHLY_ALLOWANCE"):
        assert not hasattr(P, gone), f"{gone} is back without its tests"
    assert "D1_RUN_LEDGER" not in (
        REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
