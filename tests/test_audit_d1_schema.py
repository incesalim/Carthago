"""Column-aware D1 schema ensure (scripts/audit_d1.py).

Regression for the 2026-07-02 incident: `rows_fx_position`/`rows_repricing`
were added to the bank_audit_extractions DDL (market-risk lane, 2026-06-27)
but CREATE ... IF NOT EXISTS can't evolve an existing table, so long-lived D1
deployments never got the columns and the override push died mid-flight AFTER
its partition clear. ensure_d1_schema now diffs remote columns against the DDL
and emits add-only ALTERs; the diff itself is pure and tested here.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.audit_d1 import _ddl_columns, missing_column_alters  # noqa: E402


def test_ddl_columns_include_market_risk_extraction_counters():
    cols = {name for name, _, _ in _ddl_columns()["bank_audit_extractions"]}
    assert {"rows_fx_position", "rows_repricing"} <= cols


def test_incident_shape_produces_exactly_the_two_alters():
    """Remote missing the two market-risk counters → two add-only ALTERs."""
    ddl = _ddl_columns()
    remote = {t: {name for name, _, _ in cols} for t, cols in ddl.items()}
    remote["bank_audit_extractions"] -= {"rows_fx_position", "rows_repricing"}
    alters = missing_column_alters(ddl, remote)
    assert alters == [
        "ALTER TABLE bank_audit_extractions ADD COLUMN rows_fx_position INTEGER;",
        "ALTER TABLE bank_audit_extractions ADD COLUMN rows_repricing INTEGER;",
    ]


def test_in_sync_schema_yields_no_alters():
    ddl = _ddl_columns()
    remote = {t: {name for name, _, _ in cols} for t, cols in ddl.items()}
    assert missing_column_alters(ddl, remote) == []


def test_remote_only_column_is_left_alone():
    """Add-only: a column D1 has but the DDL doesn't must NOT produce DDL."""
    ddl = {"t": [("a", "TEXT", None)]}
    remote = {"t": {"a", "legacy_extra"}}
    assert missing_column_alters(ddl, remote) == []


def test_absent_remote_table_is_skipped():
    """A table missing remotely was just created by the DDL pass — no ALTERs."""
    ddl = {"t": [("a", "TEXT", None)]}
    assert missing_column_alters(ddl, {}) == []


def test_non_constant_default_is_dropped_from_alter():
    """SQLite refuses ADD COLUMN with a non-constant default — emit the column
    without it (validated_at/extracted_at style CURRENT_TIMESTAMP)."""
    ddl = {"t": [("ts", "TEXT", "CURRENT_TIMESTAMP"), ("n", "INTEGER", "0"),
                 ("s", "TEXT", "'x'")]}
    remote = {"t": set()}
    assert missing_column_alters(ddl, remote) == [
        "ALTER TABLE t ADD COLUMN ts TEXT;",
        "ALTER TABLE t ADD COLUMN n INTEGER DEFAULT 0;",
        "ALTER TABLE t ADD COLUMN s TEXT DEFAULT 'x';",
    ]
