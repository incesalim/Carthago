"""Serving-schema authority is the migration chain, never staging initialization."""
import pytest

from scripts import audit_d1
from src.pipeline import schema


def test_versioned_counters_are_present():
    conn = schema.migrated_schema()
    try:
        assert {"rows_fx_position", "rows_repricing"} <= schema.columns(conn, "bank_audit_extractions").keys()
    finally:
        conn.close()


def test_drift_in_repair_is_a_read_only_refusal(monkeypatch):
    def drift(tables):
        raise schema.SchemaMismatch("missing rows_fx_position")
    monkeypatch.setattr(schema, "assert_remote_schema", drift)
    monkeypatch.setattr(audit_d1, "retry_wrangler", lambda *a: pytest.fail("DDL is forbidden"))
    with pytest.raises(schema.SchemaMismatch, match="rows_fx_position"):
        audit_d1.ensure_d1_schema()


@pytest.mark.parametrize("definition", ["TEXT", "INTEGER DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"])
def test_adoption_checks_type_default_and_nullability(definition):
    from scripts.reconcile_schema import adoption_plan
    conn = schema.migrated_schema()
    applied = {p.name for p in schema.MIGRATIONS.glob("*.sql")} - {"0047_audit_extraction_counters.sql"}
    conn.execute("ALTER TABLE bank_audit_extractions DROP COLUMN rows_fx_position")
    try:
        conn.execute(f"ALTER TABLE bank_audit_extractions ADD COLUMN rows_fx_position {definition}")
        with pytest.raises(schema.SchemaMismatch, match="definition differs"):
            adoption_plan(conn, applied)
    finally:
        conn.close()
