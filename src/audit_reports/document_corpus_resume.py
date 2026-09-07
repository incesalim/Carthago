"""Cheap resume only after a byte-verified publication receipt exists.

S3 object versions (ETag, size, modification time) are change detectors, never
semantic approval. A new source, engine, annotation, failed attempt or changed
artifact invalidates the shortcut. --recheck-bytes bypasses it for full readback.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .document_corpus import Filing
from .document_corpus_store import PREFIX


def metadata(key: str, response: dict) -> dict:
    modified = response["LastModified"]
    return {"key": key, "etag": response["ETag"], "size": response["ContentLength"],
            "modified": modified.isoformat()}


def annotation_identity(directory: Path, filing: Filing | None = None, *, source_only: bool = False) -> str:
    if not directory.is_dir():
        raise ValueError("Source annotation directory is missing")
    from . import document_benchmark, document_content_review, document_table_review, document_numbered_rows, document_reviewed_grid
    paths = []
    for path in sorted(directory.glob("*.json")):
        annotation = None
        if filing is not None or source_only:
            annotation = json.loads(path.read_text(encoding="utf-8"))
            if filing is not None and Filing(**annotation["filing"]) != filing:
                continue
        if source_only:
            annotation["cases"] = [c for c in annotation["cases"]
                                   if c.get("kind") in document_benchmark.SOURCE_CASE_KINDS]
            if not annotation["cases"]:
                continue
            payload = json.dumps(annotation, ensure_ascii=False, sort_keys=True).encode("utf-8")
        else:
            payload = path.read_bytes()
        paths.append((path, payload))
    if (filing is not None or source_only) and not paths:
        return "no_registered_cases"
    digest = hashlib.sha256()
    digest.update(Path(document_benchmark.__file__).read_bytes())
    digest.update(Path(document_content_review.__file__).read_bytes())
    if not source_only:
        digest.update(Path(document_table_review.__file__).read_bytes())
        digest.update(Path(document_numbered_rows.__file__).read_bytes())
        digest.update(Path(document_reviewed_grid.__file__).read_bytes())
    for path, payload in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(payload)
    return digest.hexdigest()


def download_source(store, key: str, destination: Path) -> dict:
    """Bind the downloaded bytes to metadata from the very same GET response."""
    response = store.client.get_object(Bucket=store.bucket, Key=key)
    token = metadata(key, response)
    body = response["Body"]
    try:
        with destination.open("wb") as stream:
            while chunk := body.read(1024 * 1024):
                stream.write(chunk)
    finally:
        body.close()
    if destination.stat().st_size != token["size"]:
        raise ValueError("Acquired PDF download was truncated")
    return token


def expected_artifacts(current: dict, structure: bool) -> dict[str, str]:
    artifacts = {current["original_key"]: current["source"]["pdf_sha256"],
                 current["evidence_key"]: current["evidence_bytes_sha256"]}
    if structure:
        saved = current["structure_current"]
        artifacts[saved["key"]] = saved["bytes_sha256"]
    source_prefix = f"{PREFIX}sources/{current['source']['pdf_sha256']}/"
    if any(not key.startswith(source_prefix) for key in artifacts):
        raise ValueError("Resume receipt refers outside its source namespace")
    return artifacts


def record_receipt(store, filing: Filing, acquisition: dict, annotation_hash: str,
                   benchmark: dict | None, *, structure: bool,
                   source_annotation_hash: str | None = None, source_benchmark: dict | None = None) -> None:
    """Read back exact bytes once, then remember their storage versions.

    Receipts live in the existing conditional filing index. No timestamp is
    restamped and an identical explicit byte recheck writes nothing.
    """
    index = store.read_index(filing)
    current = index["current"]
    if current["source"]["object_key"] != acquisition["key"]:
        raise ValueError("Acquisition receipt is for a different source key")
    if metadata(acquisition["key"], store.client.head_object(Bucket=store.bucket, Key=acquisition["key"])) != acquisition:
        raise ValueError("Acquired source changed during capture; retry this filing")
    tokens = []
    for key, expected_hash in expected_artifacts(current, structure).items():
        response = store.client.get_object(Bucket=store.bucket, Key=key)
        body = response["Body"]
        digest, size = hashlib.sha256(), 0
        try:
            while chunk := body.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        finally:
            body.close()
        if digest.hexdigest() != expected_hash or size != response["ContentLength"]:
            raise ValueError("Published artifact failed receipt readback")
        tokens.append(metadata(key, response))
    receipt = {"schema_version": "corpus-receipt-1", "acquisition": acquisition,
               "artifacts": tokens, "annotation_sha256": annotation_hash, "benchmark": benchmark,
               "source_annotation_sha256": source_annotation_hash, "source_benchmark": source_benchmark,
               "evidence_artifact_sha256": current["artifact_sha256"],
               "structure_artifact_sha256": current["structure_current"]["artifact_sha256"] if structure else None}

    def update(saved):
        if saved["current"] != current or saved["last_attempt"]["status"] == "failed":
            raise ValueError("Filing changed before its resume receipt could be recorded")
        saved["resume_receipt"] = receipt
    store._update_index(filing, update)


def unchanged_index(store, filing: Filing, acquisition_key: str, source_url: str | None, *,
                    evidence_engine: dict, structure_engine: dict | None,
                    annotation_hash: str, source_annotation_hash: str | None = None) -> dict | None:
    index = store.read_index(filing)
    if not index:
        return None
    if index.get("filing") != filing.as_dict():
        raise ValueError("Resume index filing mismatch")
    current, receipt = index.get("current"), index.get("resume_receipt")
    if (not current or not receipt or receipt.get("schema_version") != "corpus-receipt-1"
            or (index.get("last_attempt") or {}).get("status") == "failed"
            or current["source"]["object_key"] != acquisition_key
            or current["source"].get("source_url") != source_url
            or current["engine"] != evidence_engine
            or (source_annotation_hash is not None
                and receipt.get("source_annotation_sha256") != source_annotation_hash)
            or receipt["evidence_artifact_sha256"] != current["artifact_sha256"]
            or structure_engine is not None and receipt["annotation_sha256"] != annotation_hash):
        return None
    structured = current.get("structure_current")
    if structure_engine is not None and (not structured or structured["engine"] != structure_engine
                                         or receipt["structure_artifact_sha256"] != structured["artifact_sha256"]):
        return None
    required = set(expected_artifacts(current, structure_engine is not None))
    tokens = {item["key"]: item for item in receipt["artifacts"]}
    if not required.issubset(tokens) or receipt["acquisition"]["key"] != acquisition_key:
        return None
    for token in [receipt["acquisition"], *(tokens[key] for key in sorted(required))]:
        try:
            response = store.client.head_object(Bucket=store.bucket, Key=token["key"])
        except Exception as error:
            from .document_corpus_store import _error_code
            if _error_code(error) in ("404", "NoSuchKey"):
                return None
            raise
        if metadata(token["key"], response) != token:
            return None
    return index
