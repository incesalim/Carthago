"""Original-page checks for the three complete primary balance-sheet tables."""
import base64
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_cell_fragments import cell_word_fragments
from src.audit_reports.document_table_review import reviewed_logical_rows


FOLDER = Path(__file__).parent / 'fixtures'


@pytest.fixture
def balance_review():
    fixtures = [json.loads((FOLDER / name).read_text(encoding='utf-8')) for name in (
        'document_balance_assets_tomk.json', 'document_balance_liabilities_tomk.json',
        'document_offbalance_tomk.json')]
    annotation = json.loads((FOLDER / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    ids = {i for f in fixtures for i in f['case_ids']}
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in ids]
    return ({'source': fixtures[0]['source'], 'pages': [p for f in fixtures for p in f['pages']]},
            [{'source': fixtures[0]['source']}, *[p for f in fixtures for p in f['source_pages']]], annotation)


def selected(bundle, number):
    structure, evidence, annotation = bundle
    table = next(t for p in structure['pages'] if p['page'] == number for t in p['tables'] if t['id'] == f'p{number}:ruled0')
    return table, next(p for p in evidence[1:] if p['page'] == number), next(c for c in annotation['cases'] if c['page'] == number)


def test_three_complete_tables_keep_all_original_characters_and_source_anomalies(balance_review):
    before = deepcopy(balance_review)
    result = check_annotations(*balance_review)
    assert result['passed'] and len(result['reviewed_tables']) == 3
    for number, count in [(10, 50), (11, 44), (12, 69)]:
        table, source, case = selected(balance_review, number)
        rows = reviewed_logical_rows(table, source, case)
        assert len(rows) == count and all(len(r['cells']) == 8 for r in rows)
        assert table['row_count'] == 5 and table['n_cols'] == (4 if number == 12 else 8)
        actual = [[None if c['text'] is None else ' '.join(c['text'].split()) for c in r['cells']] for r in rows]
        assert actual == [[c['text'] for c in r] for r in case['reviewed_grid']['rows']]
        assert actual[2] == [None, None, 'TP', 'YP', 'Toplam', 'TP', 'YP', 'Toplam']
        assert actual[1][2] == 'Cari Dönem (30 Eylül 2023)'
        assert actual[1][5] == 'Önceki Dönem (31 Aralık 2022)'
        words = {w['id']: w for w in source['words']}
        physical = Counter((p['word_id'], i) for r in table['rows'] for c in r['cells']
                           for p in cell_word_fragments(c, words) for i in range(p['start'], p['end']))
        logical = Counter((p['word_id'], i) for r in rows for c in r['cells']
                          for p in c['source_fragments'] for i in range(p['start'], p['end']))
        assert logical == physical and all(v == 1 for v in logical.values())
        if number == 10:
            index = next(i for i, r in enumerate(actual) if r[0] and r[0].startswith('III.'))
            assert actual[index][2:] == actual[index + 1][2:] == ['-'] * 6
            assert actual[index + 1][0] == 'İLİŞKİN DURAN VARLIKLAR (NET)'
            assert actual[-1][2:] == ['1.639.066', '31.283', '1.670.349', '1.513.102', '-', '1.513.102']
        elif number == 11:
            assert actual[-2] == ['14.6.2 Dönem Net Kâr veya Zararı', '', '148.071', '-', '148.071', '(1.870)', '-', '(1.870)']
            profit = rows[-2]['cells']
            assert min(p['bbox'][1] for p in profit[2]['source_fragments']) > max(p['bbox'][3] for p in profit[0]['source_fragments'])
            assert next(r for r in actual if r[0] and r[0].startswith('14.4'))[2:] == ['-'] * 6
        else:
            assert actual[-1][2:] == ['900.145', '12.028', '912.173', '-', '-', '-']
            assert all(r[1] == '' for r in actual[3:])
            assert case['source_text_regions'][-1]['text'].endswith('parçasıdır')
    assert balance_review == before


@pytest.mark.parametrize('number', [10, 11, 12])
@pytest.mark.parametrize('change', [
    'digit', 'date', 'currency', 'dash_zero', 'empty_zero', 'covered_blank', 'word_loss', 'word_duplicate',
    'occurrence_swap', 'column_swap', 'row_swap', 'word_order', 'missing_wording', 'word_bool',
    'edge_removal', 'edge_outside', 'edge_reversed', 'edge_nan', 'edge_bool',
    'span_overlap', 'span_duplicate', 'span_outside', 'span_at_covered', 'missing_review', 'mixed_view',
    'empty_source_row', 'borrow_footer',
])
def test_source_grid_rejects_corruption_before_a_review_can_pass(balance_review, number, change):
    table, source, case = selected(balance_review, number)
    grid = case['reviewed_grid']
    rows = grid['rows']
    if change == 'digit':
        rows[-1][2]['text'] += '0'
    elif change == 'date':
        rows[1][5]['text'] = rows[1][5]['text'].replace('2022', '2023')
    elif change == 'currency':
        rows[2][3]['text'] = 'TP'
    elif change == 'dash_zero':
        next(c for r in rows[3:] for c in r if c['text'] == '-')['text'] = '0'
    elif change == 'empty_zero':
        rows[3][1]['text'] = '0'
    elif change == 'covered_blank':
        rows[0][1]['text'] = ''
    elif change == 'word_loss':
        rows[3][0]['source_word_ids'].pop()
    elif change == 'word_duplicate':
        rows[3][0]['source_word_ids'].append(rows[3][0]['source_word_ids'][0])
    elif change == 'occurrence_swap':
        dashes = [c for r in rows[3:] for c in r if c['text'] == '-']
        dashes[0]['source_word_ids'], dashes[1]['source_word_ids'] = dashes[1]['source_word_ids'], dashes[0]['source_word_ids']
    elif change == 'column_swap':
        rows[-1][2], rows[-1][3] = rows[-1][3], rows[-1][2]
    elif change == 'row_swap':
        rows[3], rows[4] = rows[4], rows[3]
    elif change == 'word_order':
        rows[0][0]['source_word_ids'].reverse()
    elif change == 'missing_wording':
        del rows[3][1]['text']
    elif change == 'word_bool':
        rows[3][0]['source_word_ids'][0] = True
    elif change == 'edge_removal':
        grid['y_edges'][3] += 1
    elif change == 'edge_outside':
        grid['x_edges'][-1] += 1
    elif change == 'edge_reversed':
        grid['x_edges'][1], grid['x_edges'][2] = grid['x_edges'][2], grid['x_edges'][1]
    elif change == 'edge_nan':
        grid['x_edges'][3] = float('nan')
    elif change == 'edge_bool':
        grid['x_edges'][3] = True
    elif change == 'span_overlap':
        grid['spans'][1]['column_span'] = 2
    elif change == 'span_duplicate':
        grid['spans'].append(deepcopy(grid['spans'][0]))
    elif change == 'span_outside':
        grid['spans'][0]['column_span'] = 9
    elif change == 'span_at_covered':
        grid['spans'].append({'row': 0, 'column': 1, 'row_span': 1, 'column_span': 2})
    elif change == 'missing_review':
        grid['source_review'] = ' '
    elif change == 'mixed_view':
        case['logical_rows'] = [{'row': 3}]
    elif change == 'empty_source_row':
        rows[3] = [{'text': '', 'source_word_ids': []} for _ in range(8)]
    else:
        w = next(w for w in source['words'] if w['bbox'][1] > table['bbox'][3] and w['text'])
        rows[-1][1] = {'text': w['text'], 'source_word_ids': [w['id']]}
    with pytest.raises(ValueError):
        reviewed_logical_rows(table, source, case)
    failed = check_annotations(*balance_review)
    assert not failed['passed'] and 'reviewed_tables' not in failed


def test_python_receipt_and_original_pages_are_exactly_the_worker_fixture(balance_review):
    wire = json.loads((FOLDER / 'document_table_review_balance_wire.json').read_text(encoding='utf-8'))
    assert wire['index']['resume_receipt']['benchmark']['checks'][0] == check_annotations(*balance_review)
    for kind, pages in [('source', balance_review[1][1:]), ('structure', balance_review[0]['pages'])]:
        decoded = [json.loads(line) for line in gzip.decompress(base64.b64decode(wire[f'{kind}_gzip'])).splitlines()]
        for page in pages:
            assert decoded[page['page']] == {'type': 'source_page' if kind == 'source' else 'structured_page', **page}
