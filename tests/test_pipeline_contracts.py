import sqlite3

import pytest

from scripts.check_schema_contract import check
from scripts.reconcile_schema import ADOPTIONS, adoption_plan
from src.pipeline.registry import TABLE_SETS, owner
from src.pipeline.schema import MIGRATIONS, SchemaMismatch, migrated_schema


def legacy(*, counters=0):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY, name TEXT UNIQUE, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    names = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in ADOPTIONS:
            break
        c.executescript(path.read_text(encoding="utf-8"))
        c.execute("INSERT INTO d1_migrations(name) VALUES (?)", (path.name,))
        names.add(path.name)
    for col in ["rows_fx_position", "rows_repricing"][:counters]:
        c.execute(f"ALTER TABLE bank_audit_extractions ADD COLUMN {col} INTEGER")
    return c, names


def test_migration_only_db_accepts_publisher():
    assert check() == []


@pytest.mark.parametrize("counters", [0, 1, 2])
def test_legacy_adoption_preserves_values_and_is_repeatable(counters):
    c, applied = legacy(counters=counters)
    c.execute("INSERT INTO bank_audit_extractions(bank_ticker,period,kind,pdf_path) VALUES ('TEST','2026Q2','unconsolidated','test.pdf')")
    if counters:
        c.execute("UPDATE bank_audit_extractions SET rows_fx_position=23")
    plan = adoption_plan(c, applied)
    c.executescript("\n".join(plan))
    all_applied = {r[0] for r in c.execute("SELECT name FROM d1_migrations")}
    assert adoption_plan(c, all_applied) == []
    assert c.execute("SELECT rows_fx_position FROM bank_audit_extractions").fetchone()[0] == (23 if counters else None)
    assert all_applied >= ADOPTIONS.keys()


def test_conflicting_existing_column_is_not_adopted():
    c, names = legacy()
    c.execute("ALTER TABLE bank_audit_extractions ADD COLUMN rows_fx_position TEXT")
    with pytest.raises(SchemaMismatch, match="definition differs"):
        adoption_plan(c, names)
    assert c.execute("SELECT count(*) FROM d1_migrations").fetchone()[0] == len(names)


def test_fresh_install_uses_normal_migrations():
    assert adoption_plan(sqlite3.connect(":memory:"), set()) == []


def test_repair_schema_preflight_never_mutates(monkeypatch):
    import scripts.audit_d1 as audit
    calls = []
    monkeypatch.setattr("src.pipeline.schema.assert_remote_schema", lambda tables: calls.append(tables))
    monkeypatch.setattr(audit, "retry_wrangler", lambda *a: pytest.fail("DDL write"))
    audit.ensure_d1_schema()
    assert calls == [set(audit.AUDIT_TABLES)]


def test_lane_ownership_cannot_be_inferred_from_db_contents():
    assert owner(set(TABLE_SETS["evds"])) == "bulletin"
    with pytest.raises(ValueError):
        owner({"evds_series", "bank_audit_statement_types"})
    with pytest.raises(ValueError):
        owner({"bank_audit_statement_types"}, "bulletin")


def test_missing_serving_column_refuses_preflight(monkeypatch):
    from src.pipeline import schema
    remote = migrated_schema()
    remote.execute("ALTER TABLE bank_audit_extractions DROP COLUMN rows_fx_position")
    monkeypatch.setattr(schema, "remote_schema", lambda tables: remote)
    with pytest.raises(SchemaMismatch, match="rows_fx_position"):
        schema.assert_remote_schema({"bank_audit_extractions"})

@pytest.mark.parametrize('fault', ['schema', 'snapshot'])
def test_publication_preflight_stops_before_wrangler(tmp_path, monkeypatch, fault):
    import scripts.push_to_d1 as push
    from src.pipeline import snapshots
    import sys
    db = tmp_path / 'bddk_data.db'
    c = migrated_schema()
    with sqlite3.connect(db) as target:
        c.backup(target)
    c.close()
    with sqlite3.connect(db) as conn:
        required = [r for r in conn.execute("PRAGMA table_info(api_series)") if r[3] and r[4] is None]
        names = [r[1] for r in required]
        values = [1 if r[2].upper() == "INTEGER" else "TEST" for r in required]
        conn.execute(f"INSERT INTO api_series({','.join(names)}) VALUES ({','.join('?' for _ in names)})", values)
    events = []
    def probe(tables):
        events.append('schema')
        if fault == 'schema': raise SchemaMismatch('drift')
    def candidate(db, lane):
        events.append('candidate')
        raise OSError('R2 unavailable')
    monkeypatch.setattr(push, 'assert_remote_schema', probe)
    monkeypatch.setattr(snapshots, 'prepare_candidate', candidate)
    monkeypatch.setattr(push, 'run_wrangler', lambda *a: pytest.fail('must not write'))
    monkeypatch.setattr(sys, 'argv', ['push_to_d1.py','--db',str(db),'--only-tables','api_series'])
    assert push.main() == push.EXIT_VALIDATION
    assert events == (['schema'] if fault == 'schema' else ['schema', 'candidate'])
    with sqlite3.connect(db) as conn:
        assert not push.stored_hash(conn, 'api_series')


def test_real_publication_requires_scope_before_initialization(tmp_path, monkeypatch):
    import scripts.push_to_d1 as push
    import sys
    db = tmp_path / 'bddk_data.db'
    sqlite3.connect(db).close()
    before = db.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['push_to_d1.py','--db',str(db)])
    assert push.main() == push.EXIT_VALIDATION
    assert db.read_bytes() == before


def test_shared_queue_and_caller_gate_detects_regressions():
    from scripts.check_publication_contract import check, workflow_errors
    assert check() == []
    assert workflow_errors('concurrency:\n  group: bddk-pipeline\n  cancel-in-progress: false\n')
    assert workflow_errors('      - name: Push\n        run: python scripts/push_to_d1.py\n')
    assert not workflow_errors('concurrency:\n  group: bddk-pipeline\n  queue: max\n  cancel-in-progress: false\n')


def test_direct_current_snapshot_upload_is_refused_outside_workflows():
    from scripts.check_publication_contract import boundary_errors
    assert boundary_errors('r2_storage.upload_file(gz, "state/bddk_data.db.gz")')
    assert not boundary_errors('snapshots.publish_snapshot(db, "bulletin")')


def test_canonical_snapshot_cannot_publish_another_lane(tmp_path, monkeypatch):
    import scripts.push_to_d1 as push
    import sys
    db = tmp_path / 'bddk_data.db'
    sqlite3.connect(db).close()
    monkeypatch.setattr(sys, 'argv', ['push_to_d1.py', '--db', str(db), '--table-set', 'audit'])
    assert push.main() == push.EXIT_VALIDATION
    assert db.read_bytes() == b''


def test_outbox_replays_only_the_declared_scope(tmp_path, monkeypatch):
    import scripts.push_to_d1 as push
    from src.pipeline import snapshots
    import sys
    db = tmp_path / 'bddk_data.db'
    schema = migrated_schema()
    with sqlite3.connect(db) as conn:
        schema.backup(conn)
        conn.execute('CREATE TABLE d1_pending_deletes(sql TEXT NOT NULL)')
        conn.executemany('INSERT INTO d1_pending_deletes VALUES (?)', [
            ("DELETE FROM api_series WHERE series_code='TEST';",),
            ("DELETE FROM bank_audit_extractions WHERE bank_ticker='TEST' AND period='2026Q2' AND kind='unconsolidated';",),
        ])
    schema.close()
    events = []
    monkeypatch.setattr(push, 'assert_remote_schema', lambda tables: events.append(('schema', tables)))
    monkeypatch.setattr(snapshots, 'prepare_candidate', lambda db, lane: events.append(('candidate', lane)))
    def execute(path):
        sql = path.read_text(encoding='utf-8')
        assert "DELETE FROM api_series WHERE series_code='TEST'" in sql
        assert 'bank_audit_extractions' not in sql
        events.append(('write', None))
        return 0
    monkeypatch.setattr(push, 'run_wrangler', execute)
    monkeypatch.setattr(sys, 'argv', ['push_to_d1.py','--db',str(db),'--only-tables','api_series'])
    assert push.main() == 0
    assert [name for name, _ in events] == ['schema', 'candidate', 'write']
    with sqlite3.connect(db) as conn:
        pending = conn.execute('SELECT sql FROM d1_pending_deletes').fetchall()
        assert len(pending) == 1 and 'bank_audit_extractions' in pending[0][0]
