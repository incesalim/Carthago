from pathlib import Path
import json

import pytest

from test_document_corpus_store import corpus as corpus
from src.audit_reports.document_corpus_resume import (
    annotation_identity, download_source, metadata, record_receipt, unchanged_index,
)
from src.audit_reports.document_structure import build_document_structure
from src.audit_reports.document_corpus import Filing


@pytest.fixture
def published(corpus):
    store, client, filing, pdf, evidence, artifact = corpus
    key = evidence[0]["source"]["object_key"]
    client.objects[key] = pdf.read_bytes()
    store.publish(evidence, pdf, artifact)
    structure = build_document_structure(pdf, evidence)
    store.publish_structure(structure, evidence)
    token = metadata(key, client.head_object(Bucket=store.bucket, Key=key))
    return store, client, filing, token, dict(evidence[0]["engine"]), dict(structure["engine"])


def resume(published, annotation_hash="annotations-one"):
    store, _client, filing, token, engine, structure_engine = published
    return unchanged_index(store, filing, token["key"], None, evidence_engine=engine,
                           structure_engine=structure_engine, annotation_hash=annotation_hash)


def receipt(published):
    store, _client, filing, token, _engine, _structure_engine = published
    record_receipt(store, filing, token, "annotations-one", {"status": "not_annotated"}, structure=True)


def test_resume_requires_prior_byte_verification_and_replays_without_writes(published):
    store, client, filing, *_ = published
    assert resume(published) is None
    receipt(published)
    writes = list(client.writes)
    client.reads.clear()
    assert resume(published)["current"]["semantic_verification"] == "not_performed"
    assert client.reads == [store.index_key(filing)]  # metadata HEADs, no PDF/artifact downloads
    receipt(published)  # explicit full byte readback is also content-idempotent
    assert client.writes == writes


@pytest.mark.parametrize("change", ["source", "source_timestamp", "evidence", "structure", "missing_original", "failed", "annotation", "engine"])
def test_changed_inputs_and_failed_attempts_cannot_use_the_shortcut(published, change):
    store, client, filing, token, engine, _structure_engine = published
    receipt(published)
    current = store.read_index(filing)["current"]
    if change == "source":
        client.objects[token["key"]] += b" changed"
    elif change == "source_timestamp":
        client.versions[token["key"]] = 100
    elif change == "evidence":
        client.objects[current["evidence_key"]] += b" corrupted"
    elif change == "structure":
        client.objects[current["structure_current"]["key"]] += b" corrupted"
    elif change == "missing_original":
        del client.objects[current["original_key"]]
    elif change == "failed":
        store.record_failure(filing, "new attempt failed")
    elif change == "annotation":
        assert resume(published, "new-annotations") is None
        return
    elif change == "engine":
        engine["new_version"] = "changed"
    assert resume(published) is None


def test_receipt_refuses_corrupted_artifacts_or_a_source_changed_during_capture(published):
    store, client, filing, token, *_ = published
    current = store.read_index(filing)["current"]
    client.objects[current["evidence_key"]] += b" changed"
    with pytest.raises(ValueError, match="receipt readback"):
        receipt(published)
    assert "resume_receipt" not in store.read_index(filing)
    client.objects[token["key"]] += b" new source"
    with pytest.raises(ValueError, match="changed during capture"):
        receipt(published)


def test_download_receipt_describes_the_exact_response(published, tmp_path):
    store, client, _filing, token, *_ = published
    target = tmp_path / "source.pdf"
    assert download_source(store, token["key"], target) == token
    assert target.read_bytes() == client.objects[token["key"]]


def test_changed_annotations_invalidate_resume_and_missing_directory_is_an_error(tmp_path):
    (tmp_path / "case.json").write_text('{"value": 1}')
    first = annotation_identity(tmp_path)
    (tmp_path / "case.json").write_text('{"value": 2}')
    assert annotation_identity(tmp_path) != first
    with pytest.raises(ValueError, match="missing"):
        annotation_identity(Path(tmp_path / "absent"))


def test_unrelated_bank_annotations_do_not_force_a_corpus_redownload(tmp_path):
    one = Filing("ONE", "2026Q1", "consolidated")
    two = Filing("TWO", "2026Q1", "consolidated")
    (tmp_path / "one.json").write_text(json.dumps({"filing": one.as_dict(), "cases": [1]}))
    before = annotation_identity(tmp_path, one)
    (tmp_path / "two.json").write_text(json.dumps({"filing": two.as_dict(), "cases": [2]}))
    assert annotation_identity(tmp_path, one) == before
    assert annotation_identity(tmp_path, two) != before


def test_source_only_resume_does_not_depend_on_table_annotations(published):
    store, _client, filing, token, engine, _structure_engine = published
    receipt(published)
    assert unchanged_index(store, filing, token["key"], None, evidence_engine=engine,
                            structure_engine=None, annotation_hash="changed-but-not-requested") is not None


def test_source_annotation_changes_invalidate_source_only_resume(published):
    store, _client, filing, token, engine, _structure_engine = published
    record_receipt(store, filing, token, "tables", None, structure=False, source_annotation_hash="source-v1")
    args = dict(evidence_engine=engine, structure_engine=None, annotation_hash="different-table-case")
    assert unchanged_index(store, filing, token["key"], None, **args, source_annotation_hash="source-v1")
    assert unchanged_index(store, filing, token["key"], None, **args, source_annotation_hash="source-v2") is None


def test_source_annotation_identity_excludes_table_case_changes(tmp_path):
    filing = Filing("ONE", "2026Q1", "consolidated")
    annotation = {"filing": filing.as_dict(), "cases": [
        {"kind": "source_span", "text_sha256": "a" * 64}, {"kind": "table", "cells": [1]}]}
    path = tmp_path / "one.json"
    path.write_text(json.dumps(annotation))
    before = annotation_identity(tmp_path, filing, source_only=True)
    annotation["cases"][1]["cells"] = [2]
    path.write_text(json.dumps(annotation))
    assert annotation_identity(tmp_path, filing, source_only=True) == before
    annotation["cases"][0]["text_sha256"] = "b" * 64
    path.write_text(json.dumps(annotation))
    assert annotation_identity(tmp_path, filing, source_only=True) != before


def test_logical_review_code_invalidates_table_receipts_only(tmp_path, monkeypatch):
    from src.audit_reports import document_table_review
    folder = tmp_path / 'annotations'
    folder.mkdir()
    (folder / 'source.json').write_text(json.dumps({
        'filing': {'bank_ticker': 'TOMK', 'period': '2023Q3', 'kind': 'unconsolidated'},
        'cases': [{'kind': 'source_word', 'text': 'original'}],
    }))
    before = annotation_identity(folder)
    source_before = annotation_identity(folder, source_only=True)
    changed = tmp_path / 'review.py'
    changed.write_text('changed review implementation')
    monkeypatch.setattr(document_table_review, '__file__', str(changed))
    assert annotation_identity(folder) != before
    assert annotation_identity(folder, source_only=True) == source_before
