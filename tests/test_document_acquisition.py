import io
import json
import zipfile

import fitz
import pytest

from src.audit_reports.document_acquisition import acquire_filing, unwrap_pdf
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_corpus_store import CorpusStore, PREFIX
from src.audit_reports.document_quality import bank_patterns
from test_document_corpus_store import MemoryR2, ClientError


def pdf_body(text='Test Bank 31 March 2026 Consolidated Financial Statements'):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 80), text)
        return pdf.tobytes()


def archive_body(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, body in files:
            archive.writestr(name, body)
    return stream.getvalue()


def run_acquire(client, body, text=None):
    return acquire_filing(CorpusStore(client, 'test'), Filing('TEST', '2026Q1', 'consolidated'),
                          'https://bank.example/source.zip', bank_patterns({'TEST': {'name': 'Test Bank'}}),
                          fetch=lambda url: (body, {'source_url': url, 'resolved_url': url}))


def test_activity_pdf_first_in_archive_cannot_replace_financial_report():
    wanted = pdf_body()
    archive = archive_body([('interim faaliyet.pdf', pdf_body('Activity')), ('financial report.pdf', wanted)])
    body, selection = unwrap_pdf(archive)
    assert body == wanted
    assert selection['archive_member'] == 'financial report.pdf'
    assert [r['name'] for r in selection['archive_members']] == ['interim faaliyet.pdf', 'financial report.pdf']


@pytest.mark.parametrize('names', [('English.pdf', 'Turkish.pdf'), ('faaliyet.pdf',), ('notes.xlsx',), ('same.pdf', 'same.pdf')])
def test_ambiguous_or_activity_only_archive_needs_explicit_review(names):
    with pytest.raises(ValueError, match='needs source selection'):
        unwrap_pdf(archive_body([(name, pdf_body()) for name in names]))


def test_java_wrapper_is_recorded_and_never_changes_pdf_bytes():
    body = pdf_body()
    selected, receipt = unwrap_pdf(b'\xac\xed\x00\x05' + b'x' * 23 + body)
    assert selected == body
    assert receipt['prefix_bytes'] == 27


def test_serialized_pdf_inside_a_zip_is_unwrapped_with_both_source_steps_retained():
    import hashlib
    wanted = pdf_body()
    wrapped = b'\xac\xed\x00\x05' + b'x' * 23 + wanted
    transport = archive_body([('bank report.pdf', wrapped)])
    selected, receipt = unwrap_pdf(transport)
    assert selected == wanted
    assert receipt['archive_member'] == 'bank report.pdf'
    assert receipt['prefix_bytes'] == 27
    assert receipt['wrapped_pdf_sha256'] == hashlib.sha256(wrapped).hexdigest()
    client = MemoryR2()
    result = run_acquire(client, transport)
    assert result['status'] == 'acquired'
    assert client.objects[result['transport_key']] == transport
    assert client.objects[result['original_key']] == wanted


def test_reviewed_archive_selection_is_bound_to_member_bytes_and_keeps_other_pdfs_named():
    import hashlib
    report, declaration = pdf_body(), pdf_body('Signed responsibility declaration')
    archive = archive_body([('declaration.pdf', declaration), ('report.pdf', report)])
    reviewed = {'member': 'report.pdf', 'sha256': hashlib.sha256(report).hexdigest()}
    body, selection = unwrap_pdf(archive, reviewed)
    assert body == report and selection['method'] == 'source_reviewed_archive_member'
    assert selection['unselected_pdf_members'] == [{'name': 'declaration.pdf', 'bytes': len(declaration),
                                                  'sha256': hashlib.sha256(declaration).hexdigest()}]
    with pytest.raises(ValueError, match='bytes changed'):
        unwrap_pdf(archive_body([('report.pdf', declaration)]), reviewed)
    with pytest.raises(ValueError, match='needs source selection'):
        unwrap_pdf(archive_body([('renamed.pdf', report)]), reviewed)
    with pytest.raises(ValueError, match='requires the source archive'):
        unwrap_pdf(report, reviewed)


def test_source_bytes_are_preserved_before_acquisition_and_replay_writes_nothing():
    client = MemoryR2()
    body = pdf_body()
    result = run_acquire(client, body)
    assert result['status'] == 'acquired' and result['byte_readback_verified']
    assert result['identity']['status'] == 'supported_by_source_text'
    assert result['semantic_verification'] == 'not_performed'
    assert client.writes[-1] == result['acquisition_key']
    assert client.objects[result['original_key']] == body
    assert client.objects[result['transport_key']] == body
    assert json.loads(client.objects[result['manifest_key']])['status'] == 'source_candidate'
    count = len(client.writes)
    second = acquire_filing(CorpusStore(client, 'test'), Filing('TEST', '2026Q1', 'consolidated'),
                            'https://bank.example/new.pdf', {}, fetch=lambda _: pytest.fail('existing source downloaded'))
    assert second['status'] == 'already_acquired'
    assert len(client.writes) == count


@pytest.mark.parametrize('text', ['Test Bank 30 June 2026 Consolidated Financial Statements',
                                  'Test Bank 31 March 2026 Unconsolidated Financial Statements'])
def test_wrong_cover_is_preserved_for_review_without_creating_acquisition(text):
    client = MemoryR2()
    result = run_acquire(client, pdf_body(text))
    assert result['status'] == 'needs_review'
    assert result['identity']['status'] == 'source_text_conflict'
    assert result['original_key'] in client.objects
    assert result['manifest_key'] in client.objects
    assert result['acquisition_key'] not in client.objects


def test_unreadable_cover_stays_unresolved_not_excluded_from_preservation():
    client = MemoryR2()
    result = run_acquire(client, pdf_body('Damaged text layer'))
    assert result['status'] == 'acquired'
    assert result['identity']['status'] == 'unresolved'
    assert result['semantic_verification'] == 'not_performed'


@pytest.mark.parametrize('body', [b'<html>Unavailable</html>', b'%PDF-1.7 broken PDF',
                                 archive_body([('one.pdf', b'%PDF-1.7 a'), ('two.pdf', b'%PDF-1.7 b')])])
def test_bad_response_or_ambiguous_archive_retains_transport_and_named_failure(body):
    client = MemoryR2()
    result = run_acquire(client, body)
    assert result['status'] == 'needs_review'
    assert client.objects[result['transport_key']] == body
    assert result['acquisition_key'] not in client.objects
    assert result['manifest_key'] in client.objects


@pytest.mark.parametrize('same_source', [False, True])
def test_concurrent_acquisition_never_overwrites_another_source(same_source):
    source = pdf_body()
    other = source if same_source else pdf_body('Different report')

    class RacingR2(MemoryR2):
        def put_object(self, **kwargs):
            if not kwargs['Key'].startswith(PREFIX):
                self.objects[kwargs['Key']] = other
                raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
            return super().put_object(**kwargs)

    client = RacingR2()
    if same_source:
        assert run_acquire(client, source)['status'] == 'acquired_by_concurrent_writer'
    else:
        with pytest.raises(ValueError, match='different bytes'):
            run_acquire(client, source)
    assert client.objects['test/TEST_2026Q1_consolidated.pdf'] == other


def test_corrupt_byte_readback_cannot_claim_acquisition_success():
    class CorruptR2(MemoryR2):
        def put_object(self, **kwargs):
            result = super().put_object(**kwargs)
            if not kwargs['Key'].startswith(PREFIX):
                self.objects[kwargs['Key']] = b'corrupted'
            return result
    with pytest.raises(ValueError, match='different bytes'):
        run_acquire(CorruptR2(), pdf_body())


def test_source_acquisition_cli_cannot_run_locally(monkeypatch):
    import acquire_document_corpus
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(SystemExit):
        acquire_document_corpus.main([])


def test_scoped_cli_records_each_success_and_failure_without_touching_other_filings(tmp_path, monkeypatch):
    import acquire_document_corpus as command
    from src.audit_reports import r2_storage
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    config = {'banks': {'TEST': {'name': 'Test Bank', 'urls': {'consolidated': {
        '2026Q1': 'https://example/one.pdf', '2026Q2': 'https://example/two.pdf'}}},
        'OTHER': {'name': 'Other Bank', 'urls': {'consolidated': {'2026Q1': 'https://example/other.pdf'}}}}}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    monkeypatch.setattr(r2_storage, 'get_client', MemoryR2)
    calls = []

    def acquire(store, filing, url, patterns):
        calls.append(filing)
        if filing.period == '2026Q1':
            raise ValueError('Source not available')
        return {'filing': filing.as_dict(), 'status': 'acquired'}

    monkeypatch.setattr(command, 'acquire_filing', acquire)
    assert command.main(['--config', str(path), '--output-dir', str(tmp_path), '--bank', 'TEST']) == 1
    report = json.loads((tmp_path / 'acquisition-results.json').read_text())
    assert report['summary'] == {'failed': 1, 'acquired': 1}
    assert len(calls) == 2 and all(f.bank_ticker == 'TEST' for f in calls)


def test_cli_archive_selection_cannot_leak_to_another_period(tmp_path, monkeypatch):
    import acquire_document_corpus as command
    from src.audit_reports import r2_storage
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    chosen = {'member': 'reviewed.pdf', 'sha256': 'a' * 64}
    config = {'banks': {'TEST': {'name': 'Test Bank', 'urls': {'consolidated': {
        '2026Q1': 'https://example/one.zip', '2026Q2': 'https://example/two.zip'}},
        'archive_selection': {'consolidated': {'2026Q2': chosen}}}}}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    monkeypatch.setattr(r2_storage, 'get_client', MemoryR2)
    calls = []

    def acquire(store, filing, url, patterns, **kwargs):
        calls.append((filing.period, kwargs))
        return {'filing': filing.as_dict(), 'status': 'acquired'}

    monkeypatch.setattr(command, 'acquire_filing', acquire)
    assert command.main(['--config', str(path), '--output-dir', str(tmp_path)]) == 0
    assert calls == [('2026Q1', {}), ('2026Q2', {'reviewed_member': chosen})]


@pytest.mark.parametrize('marker', [b'', b'PK\x07\x08'])
def test_single_nested_zip_keeps_both_archive_inventories_and_exact_pdf(marker):
    import hashlib
    pdf = pdf_body()
    inner = archive_body([('report.pdf', pdf)])
    outer = marker + archive_body([('original.zip', inner)])
    actual, selection = unwrap_pdf(outer)
    assert actual == pdf and selection['method'] == 'single_nested_zip'
    assert selection['archive_members'] == [{'name': 'original.zip', 'bytes': len(inner), 'sha256': hashlib.sha256(inner).hexdigest()}]
    assert selection['nested_selection']['archive_members'] == [{'name': 'report.pdf', 'bytes': len(pdf), 'sha256': hashlib.sha256(pdf).hexdigest()}]
    assert selection['nested_selection']['archive_member'] == 'report.pdf'
    assert selection.get('archive_prefix_bytes') == (4 if marker else None)
    assert selection['unselected_pdf_members'] == []


@pytest.mark.parametrize('case', ['extra_pdf', 'activity', 'extra_text', 'deep', 'override', 'fake_zip', 'fake_prefix', 'truncated'])
def test_nested_archive_does_not_hide_extra_members_or_invent_wrapper_rules(case):
    pdf = pdf_body()
    members = [('report.pdf', pdf)]
    if case == 'extra_pdf': members.append(('another.pdf', pdf))
    if case == 'activity': members.append(('faaliyet.pdf', pdf))
    if case == 'extra_text': members.append(('readme.txt', b'Other evidence'))
    inner = archive_body(members)
    if case == 'deep': inner = archive_body([('deeper.zip', inner)])
    if case == 'fake_zip': inner = pdf
    outer = b'PK\x07\x08' + archive_body([('nested.zip', inner)])
    if case == 'fake_prefix': outer = b'unknown' + outer
    if case == 'truncated': outer = outer[:-30]
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        unwrap_pdf(outer, {'member': 'report.pdf', 'sha256': 'a' * 64} if case == 'override' else None)
