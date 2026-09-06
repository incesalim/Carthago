import copy
import hashlib
import json

import pytest

from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_corpus_store import CorpusStore, PREFIX
from src.audit_reports.document_evidence import capture_source_evidence, save_evidence
from src.audit_reports.document_origin import publish_origin
from src.audit_reports.document_related import RelatedCorpusStore, related_sources
from src.audit_reports.document_structure import build_document_structure
from test_document_acquisition import archive_body, pdf_body
from test_document_origin import FILING, PATTERNS, observe
from test_document_corpus_store import MemoryR2


@pytest.fixture
def archived():
    client = MemoryR2()
    primary, signed, activity = pdf_body(), pdf_body('Signed responsibility statement'), pdf_body('Activity report')
    transport = archive_body([('report.pdf', primary), ('signed.pdf', signed), ('faaliyet.pdf', activity)])
    result, artifacts = observe(client, primary, transport,
        {'member': 'report.pdf', 'sha256': hashlib.sha256(primary).hexdigest()})
    store = CorpusStore(client, 'test')
    published = publish_origin(store, result, artifacts, PATTERNS)
    return store, client, published, signed, activity


def test_related_inventory_accounts_for_signed_and_activity_pdfs_without_primary_duplication(archived):
    store, _client, published, signed, activity = archived
    receipt, sources = related_sources(store, FILING)
    assert receipt['transport'] == published['transport']
    assert [r['member']['name'] for r, _ in sources] == ['signed.pdf', 'faaliyet.pdf']
    assert [body for _, body in sources] == [signed, activity]
    assert all(r['primary_pdf_sha256'] == published['origin_pdf']['sha256'] for r, _ in sources)


def test_related_native_capture_cannot_replace_primary_filing_and_replay_writes_nothing(archived, tmp_path):
    store, client, _published, signed, _activity = archived
    primary_key = CorpusStore.index_key(FILING)
    client.objects[primary_key] = b'primary index must remain byte-identical'
    relation, raw = related_sources(store, FILING)[1][0]
    assert raw == signed
    original = tmp_path / 'signed.pdf'; original.write_bytes(raw)
    records = capture_source_evidence(original, FILING)
    evidence = tmp_path / 'signed.jsonl.gz'; save_evidence(records, evidence)
    structure = build_document_structure(original, records)
    related = RelatedCorpusStore(store, relation)
    before = dict(client.objects)
    related.publish(records, original, evidence)
    related.publish_identity_review(records, PATTERNS)
    related.publish_structure(structure, records)
    assert related.index_key(FILING).startswith(PREFIX + 'related/')
    assert client.objects[primary_key] == before[primary_key]
    for k, value in before.items(): assert client.objects[k] == value
    index = related.read_index(FILING)
    assert index['relationship'] == relation and index['current']['source']['pdf_sha256'] == hashlib.sha256(raw).hexdigest()
    writes = list(client.writes)
    related.publish(records, original, evidence)
    related.publish_identity_review(records, PATTERNS)
    related.publish_structure(structure, records)
    assert client.writes == writes
    reference = related.read_index(FILING)['current']['related_identity_review']
    packet = json.loads(client.objects[reference['key']])
    assert packet['source_filing_role'] == 'archive_container'
    assert packet['evidence_artifact_sha256'] == index['current']['artifact_sha256']
    assert hashlib.sha256(client.objects[reference['key']]).hexdigest() == reference['sha256']
    damaged = copy.deepcopy(records)
    damaged[0]['source']['pdf_sha256'] = 'a' * 64
    with pytest.raises(ValueError, match='differs from retained'):
        related.publish_identity_review(damaged, PATTERNS)
    with pytest.raises(ValueError, match='another filing'):
        related.index_key(Filing('OTHER', '2026Q1', 'consolidated'))


@pytest.mark.parametrize('mutation', ['transport', 'original', 'member', 'primary', 'approval'])
def test_changed_or_invented_related_binding_cannot_publish(archived, tmp_path, mutation):
    store, client, published, signed, _activity = archived
    relation, _ = related_sources(store, FILING)[1][0]
    original = tmp_path / 'signed.pdf'; original.write_bytes(signed)
    records = capture_source_evidence(original, FILING)
    evidence = tmp_path / 'source.gz'; save_evidence(records, evidence)
    if mutation == 'transport': client.objects[published['transport']['key']] += b'changed'
    if mutation == 'original': original.write_bytes(pdf_body('A different attachment'))
    if mutation == 'member': relation['member']['sha256'] = 'a' * 64
    if mutation == 'primary': relation['primary_pdf_sha256'] = 'b' * 64
    if mutation == 'approval': relation['semantically_verified'] = True
    writes = list(client.writes)
    with pytest.raises(ValueError):
        RelatedCorpusStore(store, relation).publish(records, original, evidence)
    assert client.writes == writes


@pytest.mark.parametrize('mutation', ['receipt_bytes', 'omitted_member', 'invented_member', 'wrong_filing', 'wrong_primary'])
def test_inventory_rechecks_transport_and_rejects_reminted_false_relationships(archived, mutation):
    store, client, published, _signed, _activity = archived
    index = json.loads(client.objects[published['index_key']])
    body = client.objects[published['review_key']]
    if mutation == 'receipt_bytes':
        client.objects[published['review_key']] = body + b'changed'
    else:
        receipt = json.loads(body)
        if mutation == 'omitted_member': receipt['selection']['unselected_pdf_members'].pop()
        if mutation == 'invented_member':
            member = copy.deepcopy(receipt['selection']['unselected_pdf_members'][0]); member['name'] = 'invented.pdf'
            receipt['selection']['unselected_pdf_members'].append(member)
        if mutation == 'wrong_filing': receipt['filing']['period'] = '2026Q2'
        if mutation == 'wrong_primary': receipt['origin_pdf']['sha256'] = 'b' * 64
        body = json.dumps(receipt).encode()
        digest = hashlib.sha256(body).hexdigest()
        key = published['review_key'].rsplit('/', 1)[0] + '/' + digest + '.json'
        index['current'] = {**index['current'], 'key': key, 'sha256': digest, 'bytes': len(body)}
        index['revisions'] = [index['current']]
        client.objects[key] = body; client.objects[published['index_key']] = json.dumps(index).encode()
    with pytest.raises(ValueError): related_sources(store, FILING)


def test_cli_keeps_each_related_document_and_failed_recovery_named(archived, tmp_path, monkeypatch):
    import capture_related_documents as command
    from src.audit_reports import r2_storage
    _store, client, _published, _signed, _activity = archived
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setattr(r2_storage, 'get_client', lambda: client)
    calls = []

    def recover(store, original, filing, count, folder, publish):
        calls.append(original)
        return [{'page': 1, 'status': 'failed' if len(calls) == 1 else 'recovery_candidates'}]

    monkeypatch.setattr(command, 'recover_pages', recover)
    primary_key = CorpusStore.index_key(FILING); client.objects[primary_key] = b'primary stays'
    assert command.main(['--filing', 'TEST|2026Q1|consolidated', '--output-dir', str(tmp_path), '--publish']) == 1
    report = json.loads((tmp_path / 'related-results.json').read_text(encoding='utf-8'))
    assert report['expected_related_documents'] == len(report['documents']) == len(calls) == 2
    assert [d['status'] for d in report['documents']] == ['failed', 'structured_and_recovery_candidates']
    assert client.objects[primary_key] == b'primary stays'
    assert report['semantically_verified'] is False


def test_related_full_capture_cannot_run_locally(monkeypatch):
    from capture_related_documents import main
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(SystemExit): main(['--filing', 'TEST|2026Q1|consolidated'])


def test_actual_takas_june_archive_contains_a_march_report():
    from pathlib import Path
    from src.audit_reports.document_quality import bank_patterns, source_identity_review
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_related_identity_takas.json').read_text(encoding='utf-8'))
    filing = Filing('TAKAS', '2022Q2', 'unconsolidated')
    result = source_identity_review(filing, [fixture['source_page']], bank_patterns(fixture['bank_config']))
    assert fixture['source_manifest']['source']['pdf_sha256'] == '08d8ab923ae97dafd64cc09d35058a771d72691b2ff4f865fb00961fb6349f31'
    assert result['status'] == 'source_text_conflict' and result['claim_page'] == 1
    assert result['issues'] == ['period_conflicts_with_source_text']
    assert result['observations'][0]['quarter_end_dates'][0]['period'] == '2022Q1'
    assert result['observations'][0]['quarter_end_dates'][0]['source_span_ids'] == [10]
