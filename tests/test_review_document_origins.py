import json

import pytest

import review_document_origins as command
from src.audit_reports import r2_storage
from test_document_acquisition import pdf_body
from test_document_corpus_store import MemoryR2
from test_document_origin import FILING, KEY, URL, observe


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    client = MemoryR2()
    config = {'banks': {'TEST': {'name': 'Test Bank', 'urls': {'consolidated': {
        '2026Q1': URL, '2026Q2': 'https://bank.example/q2.pdf'}},
        'archive_selection': {'consolidated': {'2026Q2': {'member': 'q2.pdf', 'sha256': 'a' * 64}}}},
        'OTHER': {'name': 'Other Bank', 'urls': {'consolidated': {'2026Q1': 'https://other.example/report.pdf'}}}}}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(r2_storage, 'get_client', lambda: client)
    monkeypatch.setattr(r2_storage, 'list_audit_pdfs', lambda: [('TEST', '2026Q1', 'consolidated', KEY)])
    return client, ['--config', str(path), '--output-dir', str(tmp_path)], tmp_path


@pytest.mark.parametrize('args', [[], ['--limit', '5'], ['--limit', '1', '--publish'],
                                 ['--limit', '-1'], ['--limit', '1', '--shard-index', '1']])
def test_heavy_or_publishing_reviews_and_invalid_scopes_cannot_run_locally(monkeypatch, args):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(SystemExit):
        command.main(args)


def test_every_scoped_outcome_is_named_and_archive_selection_stays_period_bound(setup, monkeypatch):
    client, args, folder = setup
    calls = []

    def review(store, filing, key, url, patterns, *, reviewed_member):
        calls.append((filing, key, url, reviewed_member))
        if filing.period == '2026Q1':
            raise RuntimeError('Acquisition read interrupted')
        return {'filing': filing.as_dict(), 'status': 'origin_unavailable', 'error': 'HTTP 404'}, {}

    monkeypatch.setattr(command, 'observe_origin', review)
    assert command.main(args + ['--bank', 'TEST']) == 1
    report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
    assert report['selected_filings'] == report['assigned_filings'] == len(report['filings']) == 2
    assert report['summary'] == {'failed': 1, 'origin_unavailable': 1}
    assert calls[0] == (FILING, KEY, URL, None)
    assert calls[1][1] == 'test/TEST_2026Q2_consolidated.pdf'
    assert calls[1][3] == {'member': 'q2.pdf', 'sha256': 'a' * 64}
    assert not client.writes


def test_four_groups_partition_scope_without_omissions_or_duplicate_downloads(setup, monkeypatch):
    _client, args, folder = setup
    calls = []

    def review(store, filing, *unused, **kwargs):
        calls.append(filing)
        return {'filing': filing.as_dict(), 'status': 'matches_acquired_bytes'}, {}

    monkeypatch.setattr(command, 'observe_origin', review)
    for group in range(4):
        assert command.main(args + ['--shard-count', '4', '--shard-index', str(group)]) == 0
        report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
        assert report['selected_filings'] == 3
        assert report['assigned_filings'] == len(report['filings'])
    assert len(calls) == len(set(calls)) == 3


@pytest.mark.parametrize('publish', [False, True])
def test_byte_match_with_conflicting_identity_still_fails_and_preserves_evidence(setup, monkeypatch, publish):
    client, args, folder = setup
    body = pdf_body('Test Bank 31 March 2025 Consolidated Financial Statements')
    result, artifacts = observe(client, body, body)
    monkeypatch.setattr(command, 'observe_origin', lambda *a, **kw: (result, artifacts))
    assert command.main(args + ['--bank', 'TEST', '--period', '2026Q1'] + (['--publish'] if publish else [])) == 1
    report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
    assert report['summary'] == {'matches_acquired_bytes': 1}
    assert report['identity_summary'] == {'source_text_conflict': 1}
    if publish:
        record = report['filings'][0]
        assert client.objects[record['transport']['key']] == body
        assert client.objects[record['origin_pdf']['key']] == body
    else:
        assert (folder / 'sources/TEST_2026Q1_consolidated/origin_pdf.pdf').read_bytes() == body
        assert not client.writes
    assert client.objects[KEY] == body


def test_duplicate_acquisition_keys_fail_before_downloading(setup, monkeypatch):
    client, args, folder = setup
    monkeypatch.setattr(r2_storage, 'list_audit_pdfs', lambda: [
        ('TEST', '2026Q1', 'consolidated', KEY), ('TEST', '2026Q1', 'consolidated', 'another.pdf')])
    monkeypatch.setattr(command, 'observe_origin', lambda *a, **kw: pytest.fail('Ambiguous acquisition was downloaded'))
    assert command.main(args + ['--bank', 'TEST', '--period', '2026Q1']) == 1
    report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
    assert report['summary'] == {'failed': 1} and not client.writes


def test_publication_failure_retains_observed_comparison_in_run_report(setup, monkeypatch):
    client, args, folder = setup
    result, artifacts = observe(client, pdf_body(), pdf_body())
    monkeypatch.setattr(command, 'observe_origin', lambda *a, **kw: (result, artifacts))

    def fail(*args):
        raise RuntimeError('R2 publication interrupted')

    monkeypatch.setattr(command, 'publish_origin', fail)
    assert command.main(args + ['--bank', 'TEST', '--period', '2026Q1', '--publish']) == 1
    report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
    failed = report['filings'][0]
    assert failed['status'] == 'failed' and failed['observation_status'] == result['status']
    assert failed['acquisition'] == result['acquisition']
    assert failed['transport'] == result['transport'] and failed['origin_leading_pages']


def test_failed_regulator_listing_keeps_every_named_filing_outcome(setup, monkeypatch):
    from src.audit_reports import document_origin_listing
    client, args, folder = setup
    def unavailable():
        raise RuntimeError('Listing unavailable')
    monkeypatch.setattr(document_origin_listing, 'fetch_listing', unavailable)
    monkeypatch.setattr(command, 'observe_origin', lambda *a, **kw: pytest.fail('No listing was available'))
    assert command.main(args + ['--bank', 'TEST', '--source', 'bddk']) == 1
    report = json.loads((folder / 'origin-results.json').read_text(encoding='utf-8'))
    assert report['origin_source'] == 'bddk' and report['summary'] == {'failed': 2}
    assert all('Listing unavailable' in r['error'] for r in report['filings'])
    assert not client.writes


def test_regulator_alternative_does_not_reuse_another_urls_archive_override(setup, monkeypatch):
    from src.audit_reports import document_origin_listing
    from test_document_origin_listing import BODY, RESPONSE
    client, args, folder = setup
    path = folder / 'config.json'
    config = {'banks': {'ATBANK': {'name': 'Arap Türk Bankası', 'urls': {'unconsolidated': {'2026Q2': URL}},
                                'archive_selection': {'unconsolidated': {'2026Q2': {'member': 'old.pdf', 'sha256': 'a' * 64}}}}}}
    path.write_text(json.dumps(config), encoding='utf-8')
    before = path.read_bytes(); calls = []
    monkeypatch.setattr(document_origin_listing, 'fetch_listing', lambda: (BODY, RESPONSE))
    def review(store, filing, key, url, patterns, *, reviewed_member, listing):
        calls.append((filing, url, reviewed_member, listing))
        return {'filing': filing.as_dict(), 'status': 'matches_acquired_bytes'}, {}
    monkeypatch.setattr(command, 'observe_origin', review)
    assert command.main(args + ['--bank', 'ATBANK', '--source', 'bddk']) == 0
    assert len(calls) == 1 and calls[0][2] is None and calls[0][3] == (BODY, RESPONSE)
    assert 'BDREki-091-SOLO-2026-06' in calls[0][1]
    assert path.read_bytes() == before and not client.writes
