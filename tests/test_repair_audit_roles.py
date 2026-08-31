"""Role repair must not rewrite financial facts or use an out-of-date snapshot."""
import sqlite3
import sys

import pytest

from scripts import repair_audit_roles as repair
from scripts.repair_audit_roles import plan_repairs, verify_sources
from src.audit_reports.schema import init_schema
from src.audit_reports.validator import pl_roles


def source(bank="AKBNK", profit=34_378_000):
    return [dict(bank_ticker=bank, period="2026Q2", kind="unconsolidated",
                 item_order=i, hierarchy=h, item_name=label, amount=amount)
            for i, (h, label, amount) in enumerate([
                ("VIII.", "BRÜT FAALİYET KARI", 50_000_000),
                ("XIII.", "NET FAALİYET KARI", 40_000_000),
                ("XIX.", "SÜRDÜRÜLEN FAALİYETLER DÖNEM NET KARI", profit),
                ("XXIV.", "DURDURULAN FAALİYETLER DÖNEM NET KARI", 0),
                ("XXV.", "DÖNEM NET KARI/ZARARI", profit),
            ], 1)]


def role_rows(rows):
    return [dict(bank_ticker=rows[0]["bank_ticker"], period="2026Q2", kind="unconsolidated",
                 hierarchy=h, role=role, derived_at="old timestamp")
            for h, role in pl_roles(rows).items()]


def test_missing_roles_are_repaired_but_matching_partitions_are_not():
    akbank, hsbc = source(), source("HSBC")
    repairs = plan_repairs(akbank + hsbc, role_rows(hsbc))
    assert list(repairs) == [("AKBNK", "2026Q2", "unconsolidated")]
    verify_sources(repairs, akbank + hsbc)
    assert not plan_repairs(akbank + hsbc, role_rows(akbank) + role_rows(hsbc))


def test_wrong_role_at_existing_hierarchy_is_repaired():
    rows = source()
    actual = role_rows(rows)
    next(r for r in actual if r["hierarchy"] == "XXV.")["role"] = "disc_net"
    assert plan_repairs(rows, actual)


@pytest.mark.parametrize("remote", [[], source(profit=1), source(profit=None)])
def test_different_or_absent_remote_source_stops_repair(remote):
    with pytest.raises(ValueError, match="Snapshot/D1 P&L mismatch"):
        verify_sources(plan_repairs(source(), []), remote)


def test_missing_statement_does_not_delete_remote_roles():
    assert not plan_repairs([], role_rows(source()))


def test_zero_and_negative_profit_are_real_sources():
    for profit in (0, -243_000):
        rows = source(profit=profit)
        repairs = plan_repairs(rows, [])
        assert repairs
        verify_sources(repairs, rows)


def test_retry_repairs_stale_snapshot_without_rewriting_correct_d1(tmp_path, monkeypatch):
    db = tmp_path / "audit.db"
    rows = source()
    with sqlite3.connect(db) as conn:
        init_schema(conn)
        for row in rows:
            conn.execute(
                "INSERT INTO bank_audit_profit_loss "
                "(bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
                "VALUES (:bank_ticker,:period,:kind,:item_order,:hierarchy,:item_name,:amount)", row)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", ["repair", "--db", str(db), "--banks", "AKBNK", "--apply"])
    monkeypatch.setattr(repair, "_remote", lambda sql: role_rows(rows)
                        if "FROM bank_audit_pl_roles" in sql else rows)
    snapshots = []
    monkeypatch.setattr(repair, "push_snapshot", snapshots.append)

    def no_d1_write(*args, **kwargs):
        pytest.fail("Correct remote role maps must not be rewritten")

    monkeypatch.setattr(repair.subprocess, "run", no_d1_write)
    assert repair.main() == 0
    assert snapshots == [db]
    with sqlite3.connect(db) as conn:
        assert dict(conn.execute("SELECT hierarchy,role FROM bank_audit_pl_roles")) == pl_roles(rows)
    assert repair.main() == 0
    assert snapshots == [db]  # even snapshot upload is skipped on the next run
