import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_table_notes import table_note_links, verify_table_note_links

ROOT = Path(__file__).parent / 'fixtures'


@pytest.fixture
def sample():
    fixture = json.loads((ROOT / 'document_equity_source_rows_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((ROOT / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['kind'] == 'table_note_links']
    assert len(annotation['cases']) == 1
    return fixture['pages'][0], fixture['source_pages'][0], fixture['source'], annotation


def _check(page, source, identity, annotation):
    return check_annotations({'source': identity, 'pages': [page]}, [{'source': identity}, source], annotation)


def test_six_column_identifiers_link_to_complete_native_notes_without_rewriting_content(sample):
    page, source, identity, annotation = sample
    original = copy.deepcopy((page, source))
    view = table_note_links(page, source)
    assert (page, source) == original
    assert len(view['tables']) == 1 and view['semantic_verification'] == 'not_performed'
    notes = view['tables'][0]
    assert [link['column'] for link in notes['links']] == list(range(5, 11))
    assert [link['header_word_ids'] for link in notes['links']] == [[i] for i in range(67, 73)]
    assert notes['links'][-1]['text_span_ids'] == [401, 402]
    assert 'tutarları ifade eder)' in notes['links'][-1]['text']
    assert notes == json.loads((ROOT / 'document_equity_notes_preview_wire.json').read_text(encoding='utf-8'))
    assert not _check(page, source, identity, annotation)['passed']
    page['table_notes'] = view
    assert _check(page, source, identity, annotation)['passed']
    assert not verify_table_note_links(page, source)


@pytest.mark.parametrize('mutation', ['duplicate_text', 'duplicate_marker', 'missing_note', 'shift_marker', 'distant_notes', 'duplicate_table'])
def test_ambiguous_incomplete_or_distant_note_sequences_remain_unlinked(sample, mutation):
    page, source, _identity, _annotation = sample
    by_id = {e['id']: e for e in page['narrative_elements']}
    if mutation in ('duplicate_text', 'duplicate_marker'):
        duplicate = copy.deepcopy(by_id['p15:narrative38' if mutation == 'duplicate_text' else 'p15:narrative37'])
        duplicate['id'] = 'duplicate'
        page['narrative_elements'].append(duplicate)
    if mutation == 'missing_note':
        page['narrative_elements'] = [e for e in page['narrative_elements'] if e['id'] != 'p15:narrative48']
    if mutation == 'shift_marker':
        by_id['p15:narrative37']['bbox'][3] += 10
    if mutation == 'distant_notes':
        next(t for t in page['tables'] if t['id'] == 'p15:ruled0')['bbox'][3] -= 50
    if mutation == 'duplicate_table':
        duplicate = copy.deepcopy(next(t for t in page['tables'] if t['id'] == 'p15:ruled0'))
        duplicate['id'] = 'duplicate_table'; page['tables'].append(duplicate)
    assert table_note_links(page, source)['tables'] == []


@pytest.mark.parametrize('mutation', ['drop_link', 'swap_columns', 'replace_header_word', 'trim_wrapped_note', 'change_native_text', 'wrong_source_region'])
def test_link_corruption_and_independent_source_case_mutations_fail(sample, mutation):
    page, source, identity, annotation = sample
    page['table_notes'] = table_note_links(page, source)
    links = page['table_notes']['tables'][0]['links']
    if mutation == 'drop_link': links.pop()
    if mutation == 'swap_columns': links[0]['column'], links[1]['column'] = links[1]['column'], links[0]['column']
    if mutation == 'replace_header_word': links[0]['header_word_ids'] = [68]
    if mutation == 'trim_wrapped_note': links[-1]['text'] = links[-1]['text'].split('\n')[0]
    if mutation == 'change_native_text':
        next(s for s in source['spans'] if s['id'] == 384)['text'] += ' changed'
    if mutation == 'wrong_source_region': annotation['cases'][0]['links'][0]['text_bbox'][2] = 100
    assert not _check(page, source, identity, annotation)['passed']


def test_older_pages_remain_readable_and_empty_page_has_no_invented_note_links():
    assert verify_table_note_links({}, {}) == []
    assert table_note_links({'page': 1, 'tables': [], 'narrative_elements': []}, {'spans': []})['tables'] == []
