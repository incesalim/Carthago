"""Verified immutable checkpoints and promotion of authoritative R2 snapshots.

Only changed publications call this module. Candidates precede D1 writes;
committed snapshots include confirmed push digests and follow successful D1.
Unresolved candidates survive failures and are never pruned automatically.
"""
from __future__ import annotations

from contextlib import closing
import gzip
import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.audit_reports import r2_storage as storage

CURRENT_KEYS = {
    "bulletin": "state/bddk_data.db.gz",
    "audit": "state/bank_audit.db.gz",
    "analyst": "state/analyst.db.gz",
    "capture": "state/bank_audit_capture.db.gz",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package(db: Path, gz: Path) -> str:
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed; snapshot not published")
        # SQLite backup includes any committed WAL pages without changing source.
        copy = gz.with_suffix(".db")
        with closing(sqlite3.connect(copy)) as target:
            conn.backup(target)
    source_hash = digest(copy)
    with copy.open("rb") as src, gz.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=6, mtime=0, filename="") as dst:
            shutil.copyfileobj(src, dst)
    return source_hash


def checkpoint(db: Path, lane: str, phase: str) -> str:
    if lane not in CURRENT_KEYS or phase not in {"candidate", "committed"}:
        raise ValueError("unknown snapshot lane/phase")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    key = f"state/checkpoints/{lane}/{stamp}-{uuid.uuid4().hex}-{phase}.db.gz"
    with tempfile.TemporaryDirectory(prefix="carthago-snapshot-") as directory:
        gz = Path(directory) / "snapshot.gz"
        source_hash = package(Path(db), gz)
        compressed_hash = digest(gz)
        storage.upload_file(gz, key, content_type="application/gzip")
        downloaded = Path(directory) / "verified.gz"
        storage.download_to(key, downloaded)
        if digest(downloaded) != compressed_hash:
            raise ValueError("R2 checkpoint verification failed; current snapshot preserved")
        storage.upload_bytes(json.dumps({"sha256": compressed_hash, "sqlite_sha256": source_hash,
                                         "phase": phase, "lane": lane}).encode(),
                             key + ".json", content_type="application/json")
        if phase == "committed":
            # The verified object is promoted server-side; partial local uploads
            # never become the current key. Failure leaves the checkpoint intact.
            storage.get_client().copy_object(
                Bucket=storage._bucket(), Key=CURRENT_KEYS[lane],
                CopySource={"Bucket": storage._bucket(), "Key": key})
    return key


def sidecar(db: Path) -> Path:
    return Path(db).with_name(Path(db).name + ".candidates.json")


def prepare_candidate(db: Path, lane: str) -> str:
    key = checkpoint(Path(db), lane, "candidate")
    path = sidecar(db)
    keys = json.loads(path.read_text()) if path.exists() else []
    keys.append(key)
    path.write_text(json.dumps(keys), encoding="utf-8")
    print(f"Recovery candidate verified: {key}")
    return key


def retained_keys(keys: list[str]) -> set[str]:
    ordered = sorted(keys, reverse=True)
    keep = set(ordered[:7])
    days = set()
    for key in ordered:
        day = key.rsplit("/", 1)[-1][:8]
        if day not in days and len(days) < 7:
            days.add(day)
            keep.add(key)
    return keep


def publish_snapshot(db: Path, lane: str) -> str:
    key = checkpoint(Path(db), lane, "committed")
    prefix = f"state/checkpoints/{lane}/"
    committed = [k for k, _ in storage.list_keys(prefix) if k.endswith("-committed.db.gz")]
    for obsolete in sorted(set(committed) - retained_keys(committed) - {key}):
        storage.delete(obsolete)
        storage.delete(obsolete + ".json")
    # Only resolve candidates recorded by this runner for this exact DB. Failed
    # previous runners' candidates remain for deliberate recovery/comparison.
    path = sidecar(db)
    if path.exists():
        for candidate in json.loads(path.read_text()):
            if candidate.startswith(prefix) and candidate.endswith("-candidate.db.gz"):
                storage.delete(candidate)
                storage.delete(candidate + ".json")
        path.unlink()
    print(f"Snapshot verified and promoted: {key} -> {CURRENT_KEYS[lane]}")
    return key
