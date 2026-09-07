"""Official alternatives require exact listing identity, not a guessed URL."""
import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_corpus_store import CorpusStore
from src.audit_reports.document_origin import observe_origin, publish_origin
from src.audit_reports.document_origin_listing import FORM, LISTING_URL, NAMES_PATH, RESULT_URL, listing_rows, listing_witness
from src.audit_reports.document_quality import bank_patterns
from test_document_acquisition import pdf_body
from test_document_corpus_store import MemoryR2

BODY = (Path(__file__).parent / 'fixtures/document_origin_listing.html').read_bytes()
FILING = Filing('ATBANK', '2026Q2', 'unconsolidated')
RESPONSE = {'source_url': LISTING_URL, 'resolved_url': RESULT_URL, 'method': 'POST', 'form': FORM,
            'content_type': 'text/html; charset=utf-8', 'tls_verification': 'certifi_with_globalsign_intermediate'}


def test_four_actual_regulator_rows_match_exact_names_periods_and_bases():
    rows = listing_rows(BODY, json.loads(NAMES_PATH.read_text(encoding='utf-8'))['banks'])
    assert {r['filing']['bank_ticker'] for r in rows} == {'ATBANK', 'AKTIF', 'VAKBN', 'ZIRAATK'}
    assert all(r['filing']['period'] == '2026Q2' and r['filing']['kind'] == 'unconsolidated' for r in rows)
    assert listing_witness(BODY, RESPONSE, FILING)['registry_name'] == 'ARAP TÜRK BANKASI A.Ş.'


@pytest.mark.parametrize('mutation', ['period', 'basis', 'bank', 'host', 'duplicate', 'request', 'no_table'])
def test_ambiguous_or_substituted_listing_witnesses_fail(mutation):
    body, response = BODY, copy.deepcopy(RESPONSE)
    if mutation == 'period':
        body = body.replace(b'BDREki-091-SOLO-2026-06', b'BDREki-091-SOLO-2025-06')
    elif mutation == 'basis':
        body = body.replace(b'BDREki-091-SOLO', b'BDREki-091-KONSOLIDE')
    elif mutation == 'bank':
        body = body.replace('ARAP TÜRK BANKASI A.Ş.'.encode(), b'Other Bank')
    elif mutation == 'host':
        body = body.replace(b'href="/BdrUyg/Home/', b'href="https://example.invalid/BdrUyg/Home/')
    elif mutation == 'duplicate':
        body = body.replace(b'</table>', BODY.split(b'<table>')[1].split(b'</table>')[0] + b'</table>')
    elif mutation == 'request':
        response['form']['EFTKodu'] = 'unobserved'
    else:
        body = b'<html>No report listing here</html>'
    with pytest.raises(ValueError):
        listing_witness(body, response, FILING)


def test_unselected_historical_target_does_not_abort_current_filing_review():
    old = BODY.replace(b'>2026<', b'>2013<').replace(b'2026-06.zip', b'unusual-old-file.pdf')
    merged = BODY.replace(b'</table>', old.split(b'<table>')[1].split(b'</table>')[0] + b'</table>')
    assert listing_witness(merged, RESPONSE, FILING)['filing'] == FILING.as_dict()


def test_alternate_origin_retains_listing_and_prior_official_observation():
    client = MemoryR2(); store = CorpusStore(client, 'test'); key = 'atbank/' + FILING.filename
    body = pdf_body(); client.objects[key] = body; patterns = bank_patterns({'ATBANK': {'name': 'Test Bank'}})
    url = listing_witness(BODY, RESPONSE, FILING)['download_url']
    def fetch(target):
        return client.objects[key], {'source_url': target, 'resolved_url': target}
    previous, artifacts = observe_origin(store, FILING, key, 'https://bank.example/report.pdf', patterns,
                                        fetch=fetch, checked_at='2026-09-07T00:00:00+00:00')
    prior = publish_origin(store, previous, artifacts, patterns)
    result, artifacts = observe_origin(store, FILING, key, url, patterns, fetch=fetch,
                                       listing=(BODY, RESPONSE), checked_at='2026-09-07T01:00:00+00:00')
    saved = publish_origin(store, result, artifacts, patterns)
    assert client.objects[saved['source_listing']['key']] == BODY
    assert client.objects[key] == body
    index = json.loads(client.objects[saved['index_key']])
    assert len(index['revisions']) == 2 and prior['review_key'] in [r['key'] for r in index['revisions']]
    assert saved['source_url'] == url and not saved['semantically_verified']
    writes = list(client.writes)
    publish_origin(store, result, artifacts, patterns)
    assert client.writes == writes
    changed = copy.deepcopy(result); changed['source_listing']['row_cells'][1] = '2025'
    with pytest.raises(ValueError):
        publish_origin(store, changed, artifacts, patterns)
