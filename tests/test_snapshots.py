import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from src.pipeline import snapshots as S


@pytest.fixture
def objects(monkeypatch):
    data = {}
    monkeypatch.setattr(S.storage, "upload_file", lambda path, key, **kw: data.__setitem__(key, Path(path).read_bytes()))
    monkeypatch.setattr(S.storage, "upload_bytes", lambda body, key, **kw: data.__setitem__(key, body))
    monkeypatch.setattr(S.storage, "download_to", lambda key, path: Path(path).write_bytes(data[key]))
    monkeypatch.setattr(S.storage, "list_keys", lambda prefix: [(k, len(v)) for k, v in data.items() if k.startswith(prefix)])
    monkeypatch.setattr(S.storage, "delete", lambda key: data.pop(key, None))
    class Client:
        def copy_object(self, *, Bucket, Key, CopySource):
            data[Key] = data[CopySource["Key"]]
    monkeypatch.setattr(S.storage, "get_client", Client)
    return data


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE facts(value REAL)")
        c.executemany("INSERT INTO facts VALUES (?)", [(None,), (0,), (23,)])
    return p


def test_checkpoint_roundtrip_and_unique_same_day_keys(db, objects, tmp_path):
    a = S.prepare_candidate(db, "audit")
    assert S.CURRENT_KEYS["audit"] not in objects
    b = S.publish_snapshot(db, "audit")
    c = S.publish_snapshot(db, "audit")
    assert b != c
    assert a not in objects
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(objects[S.CURRENT_KEYS["audit"]]))
    with sqlite3.connect(restored) as con:
        assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert con.execute("SELECT value FROM facts").fetchall() == [(None,), (0.0,), (23.0,)]
    assert S.digest(restored) == json.loads(objects[c + ".json"])["sqlite_sha256"]


def test_failed_verification_preserves_current(db, objects, monkeypatch):
    objects[S.CURRENT_KEYS["audit"]] = b"previous"
    monkeypatch.setattr(S.storage, "download_to", lambda key, path: Path(path).write_bytes(b"bad"))
    with pytest.raises(ValueError, match="verification"):
        S.publish_snapshot(db, "audit")
    assert objects[S.CURRENT_KEYS["audit"]] == b"previous"


def test_failed_promotion_preserves_candidate_and_history(db, objects, monkeypatch):
    candidate = S.prepare_candidate(db, "audit")
    class Failed:
        def copy_object(self, **kwargs):
            raise OSError("copy failed")
    monkeypatch.setattr(S.storage, "get_client", Failed)
    with pytest.raises(OSError):
        S.publish_snapshot(db, "audit")
    assert candidate in objects and S.sidecar(db).exists()
    assert any(k.endswith("committed.db.gz") for k in objects)


def test_corrupt_database_is_never_uploaded(tmp_path, objects):
    db = tmp_path / "bad.db"
    db.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        S.prepare_candidate(db, "audit")
    assert not objects


def test_retention_keeps_seven_days_and_seven_runs():
    keys = [f"state/checkpoints/audit/202608{day:02}T{hour:02}-id-committed.db.gz"
            for day in range(1, 12) for hour in range(9)]
    keep = S.retained_keys(keys)
    assert set(sorted(keys)[-7:]) <= keep
    assert len({k.split('/')[-1][:8] for k in keep}) == 7
    assert all(k.startswith("state/checkpoints/audit/") for k in keep)


def test_sqlite_backup_includes_committed_wal(tmp_path, objects):
    db = tmp_path / 'wal.db'
    conn = sqlite3.connect(db)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE facts(value REAL)')
        conn.execute('INSERT INTO facts VALUES (0)')
        conn.commit()
        key = S.prepare_candidate(db, 'audit')
        restored = tmp_path / 'wal-restored.db'
        restored.write_bytes(gzip.decompress(objects[key]))
        restored_conn = sqlite3.connect(restored)
        try:
            assert restored_conn.execute('SELECT value FROM facts').fetchall() == [(0.0,)]
        finally:
            restored_conn.close()
    finally:
        conn.close()
