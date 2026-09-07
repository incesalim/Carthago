from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_cell_fragments import cell_word_fragments
from src.audit_reports.document_table_review import reviewed_logical_rows


@pytest.fixture
def capital_review():
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_period_headers_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'].startswith('complete_capital_disclosure_page_')]
    assert len(annotation['cases']) == 4
    return {'source': fixture['source'], 'pages': fixture['pages']}, [{'source': fixture['source']}, *fixture['source_pages']], annotation


def selected(observed, evidence, annotation, number):
    page = next(p for p in observed['pages'] if p['page'] == number)
    table = next(t for t in page['tables'] if t['id'] == f'p{number}:ruled0')
    source = next(p for p in evidence[1:] if p['page'] == number)
    case = next(c for c in annotation['cases'] if c['page'] == number)
    return table, source, case


def test_complete_four_page_capital_disclosure_and_logical_rows(capital_review):
    observed, evidence, annotation = capital_review
    before = deepcopy((observed, evidence, annotation))
    assert check_annotations(observed, evidence, annotation)['passed']
    assert sum(len(r) for c in annotation['cases'] for r in c['rows']) == 321
    for number in (26, 27, 28, 29):
        table, source, case = selected(*capital_review, number)
        rows = reviewed_logical_rows(table, source, case)
        words = {w['id']: w for w in source['words']}
        physical = Counter((p['word_id'], i) for r in table['rows'] for c in r['cells']
                           for p in cell_word_fragments(c, words) for i in range(p['start'], p['end']))
        logical = Counter((p['word_id'], i) for r in rows for c in r['cells']
                          for p in c['source_fragments'] for i in range(p['start'], p['end']))
        assert physical == logical and all(v == 1 for v in logical.values())
        if number == 26:
            assert [c['text'] for c in rows[0]['cells']] == [
                'ÇEKİRDEK SERMAYE', 'Cari Dönem\n30 Eylül 2023', 'Önceki Dönem\n31 Aralık 2022']
            assert table['rows'][0]['cells'][1]['text'] is None
        if number == 28:
            assert 've finansal' in rows[9]['cells'][0]['text']
            assert rows[9]['cells'][1]['text'] == '-'
            assert table['rows'][9]['cells'][1]['text'] == 'l\n-'
            assert rows[27]['cells'][1]['text'] == '93,75'
    assert (observed, evidence, annotation) == before


def test_receipt_wire_contains_the_exact_reviewed_source_records(capital_review):
    import gzip
    import base64
    from src.audit_reports.document_structure import structure_jsonl
    observed, evidence, annotation = capital_review
    result = check_annotations(observed, evidence, annotation)
    wire = json.loads((Path(__file__).parent / 'fixtures/document_table_review_wire.json').read_text(encoding='utf-8'))
    assert wire['index']['resume_receipt']['benchmark']['checks'][0] == result
    lines = [json.loads(line) for line in gzip.decompress(base64.b64decode(wire['structure_gzip'])).splitlines()]
    for page in observed['pages']:
        assert lines[page['page']] == {'type': 'structured_page', **page}
    manifest = json.loads(structure_jsonl(observed).splitlines()[0])
    for index, record in enumerate(result['reviewed_tables']):
        assert record['structure_page_sha256'] == manifest['page_sha256'][index]
    observed['pages'][0]['tables'] = []
    failed = check_annotations(observed, evidence, annotation)
    assert not failed['passed'] and 'reviewed_tables' not in failed


@pytest.mark.parametrize('change', ['digit', 'period', 'blank', 'merge', 'missing_row', 'unit', 'ending'])
def test_complete_capital_checks_reject_physical_or_context_changes(capital_review, change):
    observed, evidence, annotation = capital_review
    table, source, _ = selected(*capital_review, 26)
    if change == 'digit':
        table['rows'][1]['cells'][1]['text'] = '1.500.001'
    elif change == 'period':
        table['rows'][0]['cells'][0]['text'] = table['rows'][0]['cells'][0]['text'].replace('2022', '2021')
    elif change == 'merge':
        table['rows'][0]['cells'][1]['text'] = ''
    elif change == 'missing_row':
        table['rows'].pop()
    elif change == 'blank':
        table, _, _ = selected(*capital_review, 29)
        table['rows'][0]['cells'][1]['text'] = '-'
    elif change == 'unit':
        next(s for s in source['spans'] if 'Tutarlar aksi' in s['text'])['text'] = 'Tutarlar milyon TL'
    else:
        _, source, _ = selected(*capital_review, 29)
        next(s for s in source['spans'] if 'fark bulunmamaktadır.' in s['text'])['text'] = 'Fark bulunmaktadır.'
    assert not check_annotations(observed, evidence, annotation)['passed']


@pytest.mark.parametrize('change', ['zero', 'duplicate_word', 'missing_word', 'different_occurrence',
                                  'wrong_column', 'wrong_row', 'duplicate_row', 'text_order', 'missing_review'])
def test_reviewed_rows_reject_changed_assignments_and_invented_values(capital_review, change):
    observed, evidence, annotation = capital_review
    table, source, case = selected(*capital_review, 28)
    review = case['logical_rows'][0]
    cell = review['cells'][0]
    if change == 'zero':
        review['cells'][1]['text'] = '0'
    elif change == 'duplicate_word':
        cell['source_word_ids'].append(cell['source_word_ids'][0])
    elif change == 'missing_word':
        cell['source_word_ids'].pop()
    elif change == 'different_occurrence':
        word = next(w for w in source['words'] if w['id'] == cell['source_word_ids'][0])
        cell['source_word_ids'][0] = next(w['id'] for w in source['words'] if w['text'] == word['text'] and w['id'] != word['id'])
    elif change == 'wrong_column':
        review['cells'][0], review['cells'][1] = review['cells'][1], review['cells'][0]
    elif change == 'wrong_row':
        review['row'] -= 1
    elif change == 'duplicate_row':
        case['logical_rows'].append(deepcopy(review))
    elif change == 'text_order':
        cell['source_word_ids'][0], cell['source_word_ids'][1] = cell['source_word_ids'][1], cell['source_word_ids'][0]
    else:
        review['source_review'] = ''
    with pytest.raises(ValueError):
        reviewed_logical_rows(table, source, case)
    assert not check_annotations(observed, evidence, annotation)['passed']
