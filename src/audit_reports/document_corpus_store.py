"""Immutable document artifacts and revision history in a separate R2 namespace.

Only this namespace is writable here. Original acquisition objects and analytical
snapshots are never touched. Publish data before its filing index; an interrupted
run can leave an unreferenced artifact, but never an index pointing to absent data.
Indexes use conditional writes, and a failed attempt retains the last good source.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import time
from pathlib import Path

from .document_corpus import Filing, source_identity
from .document_evidence import artifact_digest, verify_evidence_records

PREFIX = "document-corpus/v1/"


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _error_code(error: Exception) -> str | None:
    """S3 error protocol, without making offline storage tests import an SDK.

    The live client is still boto3. Transport and unexpected programming errors
    have no service code and must propagate rather than becoming missing objects.
    """
    response = getattr(error, "response", None)
    return response.get("Error", {}).get("Code") if isinstance(response, dict) else None


class CorpusStore:
    def __init__(self, client, bucket: str):
        self.client, self.bucket = client, bucket

    def _read(self, key: str) -> tuple[bytes | None, str | None]:
        if not key.startswith(PREFIX):
            raise ValueError("Object is outside the document corpus namespace")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if _error_code(error) in ("404", "NoSuchKey"):
                return None, None
            raise
        return response["Body"].read(), response["ETag"]

    def _immutable(self, key: str, body: bytes, content_type: str) -> bool:
        existing, _ = self._read(key)
        if existing is not None:
            if existing != body:
                raise ValueError(f"Immutable corpus object has different content: {key}")
            return False
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                   ContentType=content_type, IfNoneMatch="*")
        except Exception as error:
            if _error_code(error) not in ("412", "PreconditionFailed"):
                raise
        stored, _ = self._read(key)
        if stored != body:
            raise ValueError(f"Corpus upload failed read-back verification: {key}")
        return True

    @staticmethod
    def index_key(filing: Filing) -> str:
        return (f"{PREFIX}filings/{filing.bank_ticker}/"
                f"{filing.period}/{filing.kind}.json")

    def _update_index(self, filing: Filing, update) -> dict:
        key = self.index_key(filing)
        for _attempt in range(3):
            previous, etag = self._read(key)
            index = json.loads(previous) if previous is not None else {
                "schema_version": "corpus-index-1", "filing": filing.as_dict(),
                "current": None, "revisions": [], "last_attempt": None}
            if index.get("filing") != filing.as_dict():
                raise ValueError("Corpus filing index identity mismatch")
            update(index)
            body = _json(index)
            if body == previous:
                return index
            condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
            try:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                       ContentType="application/json", **condition)
                return index
            except Exception as error:
                if _error_code(error) not in ("412", "PreconditionFailed"):
                    raise
        raise RuntimeError("Corpus index changed concurrently; retry the filing")

    def update_catalog(self, inventory: dict, indexes: list[dict], *,
                       evidence_engine: dict, structure_engine: dict) -> dict:
        from .document_corpus_catalog import build_catalog
        key = PREFIX + "catalog.json"
        # Four disjoint filing groups share only this compact catalog. Re-read
        # and merge after contention; never overwrite another group's progress.
        for attempt in range(8):
            previous, etag = self._read(key)
            catalog = build_catalog(inventory, json.loads(previous) if previous else None, indexes,
                                    evidence_engine=evidence_engine, structure_engine=structure_engine)
            body = _json(catalog)
            if body == previous:
                return catalog
            condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
            try:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                       ContentType="application/json", **condition)
                return catalog
            except Exception as error:
                if _error_code(error) not in ("412", "PreconditionFailed"):
                    raise
                if attempt < 7:
                    time.sleep(random.uniform(0.02, min(0.5, 0.05 * 2 ** attempt)))
        raise RuntimeError("Corpus catalog changed concurrently; retry its update")

    def read_index(self, filing: Filing) -> dict | None:
        body, _ = self._read(self.index_key(filing))
        return json.loads(body) if body is not None else None

    def publish(self, records: list[dict], original: Path, evidence: Path) -> dict:
        check = verify_evidence_records(records)
        if not check["valid"]:
            raise ValueError(f"Cannot publish invalid evidence: {check['errors']}")
        manifest = records[0]
        source = manifest["source"]
        filing = Filing(source["bank_ticker"], source["period"], source["kind"])
        observed = source_identity(original, filing)
        if (observed["pdf_sha256"], observed["byte_count"]) != (
                source["pdf_sha256"], source["byte_count"]):
            raise ValueError("Original PDF does not match evidence source")
        evidence_body = evidence.read_bytes()
        decoded = [json.loads(line) for line in gzip.decompress(evidence_body).splitlines()]
        if decoded != records:
            raise ValueError("Evidence file does not match the verified records")
        address = artifact_digest(records)
        base = f"{PREFIX}sources/{source['pdf_sha256']}/"
        original_key, evidence_key = base + "original.pdf", base + address + ".jsonl.gz"
        # Read bytes once for upload; recheck this exact payload, closing a local
        # replacement race between the source_identity check and upload.
        original_body = original.read_bytes()
        if _sha(original_body) != source["pdf_sha256"]:
            raise ValueError("Original PDF changed before upload")
        self._immutable(original_key, original_body, "application/pdf")
        self._immutable(evidence_key, evidence_body, "application/gzip")
        revision = {"source": source, "engine": manifest["engine"],
                    "artifact_sha256": address, "evidence_key": evidence_key,
                    "evidence_bytes_sha256": _sha(evidence_body),
                    "original_key": original_key,
                    "page_count": manifest["page_count"],
                    "text_characters": manifest["text_characters"],
                    "image_regions": manifest["image_regions"],
                    "status": "source_preserved", "semantic_verification": "not_performed"}

        def update(index):
            existing = next((r for r in index["revisions"] if r["artifact_sha256"] == address), None)
            if existing is None:
                existing = revision
                index["revisions"].append(existing)
            elif any(existing.get(key) != value for key, value in revision.items()):
                raise ValueError("Stored revision disagrees with its immutable artifact")
            index["current"] = existing
            structured = existing.get("structure_current")
            index["last_attempt"] = ({"status": "structured_candidates",
                                      "artifact_sha256": structured["artifact_sha256"]}
                                     if structured else
                                     {"status": "source_preserved", "artifact_sha256": address})

        return self._update_index(filing, update)

    def archive_source(self, source: dict, original: Path) -> str:
        """Preserve an original even if decoding or later structure extraction fails."""
        filing = Filing(source["bank_ticker"], source["period"], source["kind"])
        observed = source_identity(original, filing)
        if (observed["pdf_sha256"], observed["byte_count"]) != (source["pdf_sha256"], source["byte_count"]):
            raise ValueError("Original PDF does not match source identity")
        body = original.read_bytes()
        if _sha(body) != source["pdf_sha256"]:
            raise ValueError("Original PDF changed before archive")
        key = f"{PREFIX}sources/{source['pdf_sha256']}/original.pdf"
        self._immutable(key, body, "application/pdf")
        return key

    def publish_structure(self, structure: dict, evidence: list[dict]) -> dict:
        from .document_structure import structure_digest, structure_jsonl, verify_document_structure
        check = verify_document_structure(structure, evidence)
        if not check["valid"]:
            raise ValueError(f"Cannot publish invalid structure: {check['errors']}")
        source = structure["source"]
        filing = Filing(source["bank_ticker"], source["period"], source["kind"])
        digest = structure_digest(structure)
        key = f"{PREFIX}sources/{source['pdf_sha256']}/{digest}.structure.jsonl.gz"
        payload = gzip.compress(structure_jsonl(structure), compresslevel=6, mtime=0)
        self._immutable(key, payload, "application/gzip")
        from .document_quality import structure_diagnostics
        summary = {"artifact_sha256": digest, "key": key, "bytes_sha256": _sha(payload),
                   "engine": structure["engine"], "status": "structured_candidates",
                   "table_candidates": sum(len(p["tables"]) for p in structure["pages"]),
                   "text_blocks": sum(len(p["text_blocks"]) for p in structure["pages"]),
                   "pages_with_issues": sum(bool(p["issues"]) for p in structure["pages"]),
                   "diagnostics": structure_diagnostics(structure),
                   "semantic_verification": "not_performed"}

        def update(index):
            current = index["current"]
            if current is None or current["artifact_sha256"] != structure["evidence_artifact_sha256"]:
                raise ValueError("Publish the matching source before its structure")
            revision = next(r for r in index["revisions"]
                            if r["artifact_sha256"] == current["artifact_sha256"])
            history = revision.setdefault("structure_revisions", [])
            if summary not in history:
                history.append(summary)
            revision["structure_current"] = summary
            index["current"] = revision
            index["last_attempt"] = {"status": "structured_candidates", "artifact_sha256": digest}

        return self._update_index(filing, update)

    def cached_structure(self, evidence: list[dict], engine: dict) -> dict | None:
        from .document_structure import structure_digest, structure_from_jsonl, verify_document_structure
        source = evidence[0]["source"]
        filing = Filing(source["bank_ticker"], source["period"], source["kind"])
        body, _ = self._read(self.index_key(filing))
        if body is None:
            return None
        index = json.loads(body)
        for revision in reversed(index["revisions"]):
            if revision["artifact_sha256"] != artifact_digest(evidence):
                continue
            for saved in reversed(revision.get("structure_revisions", [])):
                if saved["engine"] != engine:
                    continue
                compressed, _ = self._read(saved["key"])
                if compressed is None or _sha(compressed) != saved["bytes_sha256"]:
                    raise ValueError("Cached structure is missing or corrupted")
                raw = gzip.decompress(compressed)
                structure = (structure_from_jsonl(raw) if saved["key"].endswith(".jsonl.gz")
                             else json.loads(raw))
                if (not verify_document_structure(structure, evidence)["valid"]
                        or structure["engine"] != engine
                        or structure_digest(structure) != saved["artifact_sha256"]):
                    raise ValueError("Cached structure fails its identity")
                return structure
        return None

    def record_failure(self, filing: Filing, error: str, *, source: dict | None = None,
                       original_key: str | None = None) -> dict:
        def update(index):
            failure = {"status": "failed", "error": error}
            if source is not None:
                failure["source"] = source
            if original_key is not None:
                failure["original_key"] = original_key
            index["last_attempt"] = failure
            history = index.setdefault("failed_attempts", [])
            if failure not in history:
                history.append(failure)
        return self._update_index(filing, update)

    def cached_evidence(self, source: dict, engine: dict) -> list[dict] | None:
        """Reuse only source- and engine-identical evidence whose bytes still verify.

        The caller hashes the current acquired PDF first. A filename or past
        success is never enough to skip extraction. Older revisions remain usable.
        """
        filing = Filing(source["bank_ticker"], source["period"], source["kind"])
        body, _ = self._read(self.index_key(filing))
        if body is None:
            return None
        index = json.loads(body)
        if index.get("filing") != filing.as_dict():
            raise ValueError("Corpus filing index identity mismatch")
        for revision in reversed(index["revisions"]):
            if revision["source"] != source or revision["engine"] != engine:
                continue
            compressed, _ = self._read(revision["evidence_key"])
            if compressed is None or _sha(compressed) != revision["evidence_bytes_sha256"]:
                raise ValueError("Cached corpus evidence is missing or corrupted")
            records = [json.loads(line) for line in gzip.decompress(compressed).splitlines()]
            check = verify_evidence_records(records, expected_source=source)
            if (not check["valid"] or records[0]["engine"] != engine
                    or artifact_digest(records) != revision["artifact_sha256"]):
                raise ValueError("Cached corpus evidence fails its identity")
            return records
        return None
