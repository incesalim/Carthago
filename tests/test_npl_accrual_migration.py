"""The optional NPL accrual survives old snapshots and the D1 schema boundary."""
import sqlite3
from pathlib import Path

from scripts.revalidate_audit_db import _npl_movement_rows
from src.audit_reports.schema import DDL, init_schema


def _legacy_database():
    conn = sqlite3.connect(":memory:")
    legacy_ddl = DDL.replace("    accrual_movement   REAL,\n", "")
    assert legacy_ddl != DDL
    conn.executescript(legacy_ddl)
    conn.execute(
        "INSERT INTO bank_audit_npl_movement "
        "(bank_ticker,period,kind,group_code,period_type,closing_balance) "
        "VALUES ('TFKB','2026Q2','consolidated','III','current',530000)"
    )
    return conn


def test_old_snapshot_reader_and_idempotent_staging_migration_preserve_null():
    with _legacy_database() as conn:
        row = _npl_movement_rows(conn, "TFKB", "2026Q2", "consolidated")[0]
        assert row["closing_balance"] == 530000 and row["accrual_movement"] is None
        init_schema(conn)
        init_schema(conn)
        assert conn.execute(
            "SELECT closing_balance,accrual_movement FROM bank_audit_npl_movement"
        ).fetchone() == (530000, None)
        conn.execute("UPDATE bank_audit_npl_movement SET accrual_movement=-4000")
        assert _npl_movement_rows(conn, "TFKB", "2026Q2", "consolidated")[0]["accrual_movement"] == -4000


def test_d1_additive_migration_matches_staging_and_does_not_invent_zero():
    path = Path(__file__).resolve().parents[1] / "web/migrations/0046_npl_accrual_movement.sql"
    with _legacy_database() as conn, sqlite3.connect(":memory:") as staging:
        conn.executescript(path.read_text(encoding="utf-8"))
        init_schema(staging)
        shape = lambda db: {(r[1], r[2], r[3], r[4]) for r in db.execute(
            "PRAGMA table_info(bank_audit_npl_movement)")}
        assert shape(conn) == shape(staging)
        assert conn.execute("SELECT accrual_movement FROM bank_audit_npl_movement").fetchone() == (None,)
