import copy
import hashlib
import json

import pytest

from src.audit_reports.document_corpus_store import CorpusStore, _json
from src.audit_reports.document_editions import EditionCorpusStore, edition_source
from src.audit_reports.document_evidence import capture_source_evidence, save_evidence
from src.audit_reports.document_origin import publish_origin
from src.audit_reports.document_structure import build_document_structure
from test_document_acquisition import archive_body, pdf_body
from test_document_corpus_store import MemoryR2
from test_document_origin import FILING, PATTERNS, URL, observe


@pytest.fixture
def editions():
    client, old, new = MemoryR2(), pdf_body(), pdf_body('Another Test Bank 31 March 2026 Consolidated Financial Statements')
    store = CorpusStore(client, 'test')
    transport = archive_body([('report.pdf', new)])
    result, artifacts = observe(client, old, transport)
    different = publish_origin(store, result, artifacts, PATTERNS)
    observation = different['review_key'].rsplit('/', 1)[1][:-5]
    result, artifacts = observe(client, old, old)
    result['checked_at'] = '2026-09-07T01:00:00+00:00'
    latest = publish_origin(store, result, artifacts, PATTERNS)
    return store, client, different, observation, latest, new


def test_historical_different_pdf_remains_addressable_after_a_later_match(editions):
    store, _client, different, observation, latest, body = editions
    receipt, ref, pdf = edition_source(store, FILING, observation)
    assert pdf == body and ref['key'] == different['review_key']
    assert ref['key'] != latest['review_key'] and receipt['status'] == 'different_pdf_revision'


def capture(edition, body, folder):
    original = folder / 'edition.pdf'; original.write_bytes(body)
    records = capture_source_evidence(original, FILING, source_url=URL)
    evidence = folder / 'source.gz'; save_evidence(records, evidence)
    structure = build_document_structure(original, records)
    edition.publish(records, original, evidence)
    edition.publish_structure(structure, records)
    return records, original, evidence, structure


def test_edition_capture_preserves_every_existing_object_and_replay_writes_nothing(editions, tmp_path):
    store, client, _different, observation, _latest, body = editions
    main_key = store.index_key(FILING)
    client.objects[main_key] = b'The acquired filing index must remain unchanged'
    before = copy.deepcopy(client.objects)
    edition = EditionCorpusStore(store, FILING, observation)
    records, original, evidence, structure = capture(edition, body, tmp_path)
    assert all(client.objects[k] == v for k, v in before.items())
    index = edition.read_index(FILING)
    assert index['edition']['relationship'] == 'observed_different_official_pdf'
    assert index['origin_observations'] == [edition.reference]
    assert index['current']['source']['pdf_sha256'] == hashlib.sha256(body).hexdigest()
    writes = list(client.writes)
    edition.publish(records, original, evidence)
    edition.publish_structure(structure, records)
    assert client.writes == writes


@pytest.mark.parametrize('mutation', ['pdf', 'transport', 'receipt', 'history', 'same_pdf', 'approval', 'selection', 'foreign', 'acquisition'])
def test_false_source_bindings_cannot_publish_even_with_reminted_receipts(editions, mutation):
    store, client, different, observation, latest, _body = editions
    index = json.loads(client.objects[different['index_key']])
    receipt = json.loads(client.objects[different['review_key']])
    if mutation in ('pdf', 'transport', 'receipt'):
        key = different['origin_pdf']['key'] if mutation == 'pdf' else different['transport']['key'] if mutation == 'transport' else different['review_key']
        client.objects[key] += b'corrupt'
    elif mutation == 'history':
        index['revisions'] = [index['current']]
        client.objects[different['index_key']] = _json(index)
    elif mutation == 'same_pdf':
        observation = latest['review_key'].rsplit('/', 1)[1][:-5]
    else:
        if mutation == 'approval': receipt['semantically_verified'] = True
        if mutation == 'selection': receipt['selection']['archive_member'] = 'invented.pdf'
        if mutation == 'foreign': receipt['filing']['period'] = '2026Q2'
        if mutation == 'acquisition': receipt['acquisition']['sha256'] = receipt['origin_pdf']['sha256']
        payload = _json(receipt); observation = hashlib.sha256(payload).hexdigest()
        ref = next(r for r in index['revisions'] if r['key'] == different['review_key'])
        ref.update(key=different['review_key'].rsplit('/', 1)[0] + '/' + observation + '.json', sha256=observation, bytes=len(payload))
        if mutation == 'acquisition': ref['acquisition_sha256'] = receipt['acquisition']['sha256']
        client.objects[ref['key']] = payload
        client.objects[different['index_key']] = _json(index)
    writes = list(client.writes)
    with pytest.raises(ValueError): EditionCorpusStore(store, FILING, observation)
    assert client.writes == writes


def test_local_replacement_or_source_url_change_is_rejected_before_writing(editions, tmp_path):
    store, client, _different, observation, _latest, body = editions
    edition = EditionCorpusStore(store, FILING, observation)
    original = tmp_path / 'edition.pdf'; original.write_bytes(body)
    records = capture_source_evidence(original, FILING, source_url='https://invented.example/pdf')
    evidence = tmp_path / 'source.gz'; save_evidence(records, evidence)
    before = list(client.writes)
    with pytest.raises(ValueError, match='differs'): edition.publish(records, original, evidence)
    assert client.writes == before


def test_cli_reuses_an_edition_and_never_replaces_the_main_index(editions, tmp_path, monkeypatch):
    import capture_document_edition as command
    from src.audit_reports import r2_storage
    store, client, _different, observation, _latest, _body = editions
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setattr(r2_storage, 'get_client', lambda: client)
    primary_key = store.index_key(FILING); client.objects[primary_key] = b'primary stays'
    selection = {'method': 'source_content_detector', 'page_count': 1, 'pages': [], 'selection_completeness_verified': False}
    monkeypatch.setattr(command, 'select_pages', lambda *_args: selection)
    args = ['--filing', 'TEST|2026Q1|consolidated', '--observation', observation, '--output-dir', str(tmp_path), '--publish']
    assert command.main(args) == 0
    writes = list(client.writes)
    assert command.main(args) == 0
    assert client.writes == writes and client.objects[primary_key] == b'primary stays'
    result = json.loads((tmp_path / 'edition-results.json').read_text(encoding='utf-8'))
    assert result['native_reused'] and result['structure_reused']
    assert result['selection'] == selection and result['recovery_pages'] == []
    assert result['semantically_verified'] is False


def test_cli_cannot_claim_missing_selected_pages_succeeded(editions, tmp_path, monkeypatch):
    import capture_document_edition as command
    from src.audit_reports import r2_storage
    _store, client, _different, observation, _latest, _body = editions
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setattr(r2_storage, 'get_client', lambda: client)
    monkeypatch.setattr(command, 'select_pages', lambda *_args: {'page_count': 1, 'pages': [1]})
    monkeypatch.setattr(command, 'recover_pages', lambda *_args, **_kwargs: [])
    assert command.main(['--filing', 'TEST|2026Q1|consolidated', '--observation', observation,
                         '--output-dir', str(tmp_path)]) == 1
    result = json.loads((tmp_path / 'edition-results.json').read_text(encoding='utf-8'))
    assert 'incomplete' in result['error']


def test_edition_full_capture_cannot_run_locally(monkeypatch):
    from capture_document_edition import main
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(SystemExit): main(['--filing', 'TEST|2026Q1|consolidated', '--observation', 'a' * 64])
