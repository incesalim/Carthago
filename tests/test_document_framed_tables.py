"""Whole source regions, distinct periods, and fail-closed assignment checks."""
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from src.audit_reports.document_framed_tables import SCHEMA, framed_table_candidates, verify_framed_tables
from src.audit_reports.document_table_context import _grid


@pytest.fixture(scope='module')
def pages():
    path = Path(__file__).parent / 'fixtures/document_framed_tables_garan.json.gz'
    fixture = json.loads(gzip.decompress(path.read_bytes()))
    for source, wire in zip(fixture['pages'], fixture['structures'], strict=True):
        assert wire['tables'][-1:] == framed_table_candidates(source)
        assert wire['table_context']['tables'][-1]['physical_grid'] == _grid(wire['tables'][-1])
    return fixture['pages']


@pytest.mark.parametrize('index,body_rows,total', [
    (0, 47, ['723,172,072', '580,406,411', '1,303,578,483', '414,793,046', '435,682,554', '850,475,600']),
    (1, 49, ['661,691,961', '641,886,522', '1,303,578,483', '322,633,454', '527,842,146', '850,475,600']),
    (2, 86, ['2,435,014,236', '3,821,593,203', '6,256,607,439', '1,445,704,362', '2,731,337,749', '4,177,042,111']),
])
def test_all_native_words_columns_dates_and_units_survive(pages, index, body_rows, total):
    source = pages[index]
    tables = framed_table_candidates(source)
    assert len(tables) == 1
    table = tables[0]
    assert table['n_cols'] == 8 and table['row_count'] == body_rows + 4
    assert _grid(table) is not None
    assert table['header_association_verified'] is False
    assert table['review_status'] == 'unreviewed'
    assert [c['text'] for c in table['rows'][-1]['cells'][2:]] == total
    assert table['rows'][0]['cells'][2]['text'] == 'THOUSANDS OF TURKISH LIRA (TL)'
    assert table['rows'][1]['cells'][2]['text'] == 'CURRENT PERIOD'
    assert table['rows'][1]['cells'][5]['text'] == 'PRIOR PERIOD'
    assert table['rows'][2]['cells'][2]['text'] == '31 December 2022'
    assert table['rows'][2]['cells'][5]['text'] == '31 December 2021'
    assert [c['text'] for c in table['rows'][3]['cells'][2:]] == ['TL', 'FC', 'Total'] * 2
    assert table['rows'][0]['cells'][1]['text'] == 'Footnotes'
    x0, y0, x1, y1 = table['bbox']
    expected = Counter(w['id'] for w in source['words']
                       if x0 < (w['bbox'][0] + w['bbox'][2]) / 2 < x1
                       and y0 < (w['bbox'][1] + w['bbox'][3]) / 2 < y1)
    actual = Counter(i for row in table['rows'] for cell in row['cells'] for i in cell['word_ids'])
    assert actual == expected and all(n == 1 for n in actual.values())
    by_id = {w['id']: w for w in source['words']}
    for row in table['rows']:
        for cell in row['cells']:
            assert Counter((cell['text'] or '').split()) == Counter(by_id[i]['text'] for i in cell['word_ids'])


def test_nested_notes_signed_values_and_wrapped_labels_remain_literal(pages):
    assets = framed_table_candidates(pages[0])[0]
    row = next(r for r in assets['rows'] if (r['cells'][0]['text'] or '').startswith('1.1.1 '))
    assert [c['text'] for c in row['cells'][2:]] == ['9,205,355', '130,364,387', '139,569,742',
                                                   '13,530,186', '110,393,448', '123,923,634']
    associates = next(r for r in assets['rows'] if (r['cells'][0]['text'] or '').startswith('4.1 Associates'))
    assert associates['cells'][1]['text'] == '5.1.10'
    liabilities = framed_table_candidates(pages[1])[0]
    recycled = next(r for r in liabilities['rows'] if (r['cells'][0]['text'] or '').startswith('16.4 '))
    assert recycled['cells'][3]['text'] == '(177,731)' and recycled['cells'][6]['text'] == '(750,153)'
    # This is still a baseline view: preserve both parts of the wrapped XIII
    # label and mark the empty upper-line amount cells blank, never zero.
    wrapped = next(i for i, r in enumerate(liabilities['rows']) if (r['cells'][0]['text'] or '').startswith('XIII.'))
    assert liabilities['rows'][wrapped]['cells'][2]['text'] == ''
    assert liabilities['rows'][wrapped + 1]['cells'][0]['text'] == 'DISCONTINUED OPERATIONS (Net)'
    assert liabilities['rows'][wrapped + 1]['cells'][2]['text'] == '-'


@pytest.mark.parametrize('mutation', ['table', 'row', 'column', 'cell', 'note', 'date', 'unit', 'word',
                                    'duplicate', 'method', 'geometry', 'review', 'schema'])
def test_structural_validator_detects_corruption_including_whole_table_deletion(pages, mutation):
    source = pages[0]
    page = {'tables': framed_table_candidates(source), 'framed_tables_schema': SCHEMA}
    assert verify_framed_tables(page, source) == []
    table = page['tables'][0]
    if mutation == 'table':
        page['tables'] = []
    elif mutation == 'row':
        table['rows'].pop(10)
    elif mutation == 'column':
        for row in table['rows']:
            row['cells'].pop()
    elif mutation in ('cell', 'note', 'date', 'unit'):
        r, c = {'cell': (5, 2), 'note': (5, 1), 'date': (2, 5), 'unit': (0, 2)}[mutation]
        table['rows'][r]['cells'][c]['text'] = ''
    elif mutation == 'word':
        table['rows'][5]['cells'][2]['word_ids'] = []
    elif mutation == 'duplicate':
        table['rows'][5]['cells'][2]['word_ids'] *= 2
    elif mutation == 'method':
        table['method'] = 'legacy_numeric_geometry'
    elif mutation == 'geometry':
        table['rows'][5]['cells'][2]['bbox'][0] += 2
    elif mutation == 'review':
        table['header_association_verified'] = True
    else:
        del page['framed_tables_schema']
    assert verify_framed_tables(page, source)


@pytest.mark.parametrize('mutation', ['currency_header', 'date_header', 'frame', 'amount_word', 'alignment', 'actualtext'])
def test_ambiguous_inputs_abstain_instead_of_using_legacy_column_guesses(pages, mutation):
    source = deepcopy(pages[0])
    table = framed_table_candidates(source)[0]
    if mutation == 'actualtext':
        source['actualtext_changes_word_view'] = True
    elif mutation == 'frame':
        source['drawings'].pop()
    else:
        r, c = (3, 2) if mutation == 'currency_header' else (2, 5) if mutation == 'date_header' else (5, 2)
        wid = table['rows'][r]['cells'][c]['word_ids'][-1]
        word = next(w for w in source['words'] if w['id'] == wid)
        if mutation == 'alignment':
            word['bbox'][0] -= 10
            word['bbox'][2] -= 10
        else:
            word['text'] = 'ambiguous'
    assert framed_table_candidates(source) == []


def test_more_than_two_disclosed_periods_are_retained():
    source = {'page': 1, 'words': [], 'drawings': []}

    def word(text, x, y, width=None):
        source['words'].append({'id': len(source['words']), 'text': text,
                                'bbox': [x, y, x + (width or len(text) * 3), y + 6]})

    for box in ([0, 0, .4, 150], [799.6, 0, 800, 150], [0, 0, 800, .4],
                [0, 40, 800, 40.4], [0, 149.6, 800, 150]):
        source['drawings'].append({'id': len(source['drawings']), 'bbox': box, 'path_items': 1})
    word('ASSETS', 30, 15)
    word('Footnotes', 165, 15)
    word('THOUSANDS OF TL', 360, 3)
    for group in range(3):
        word(['CURRENT', 'PRIOR', 'RESTATED'][group], 260 + group * 180, 12)
        word(str(2022 - group), 275 + group * 180, 21)
        for col, label in enumerate(['TL', 'FC', 'Total']):
            word(label, 250 + (group * 3 + col) * 60, 31)
    for row in range(8):
        word(f'{row + 1}. Assets', 30, 45 + row * 12)
        if row == 0:
            word('5.1.1', 170, 45)
        for col in range(9):
            # Distinct literal zero and dash; an omitted word is a blank cell.
            if row == 2 and col == 0:
                continue
            value = '0' if row == 0 else '-' if row == 1 else str(100 + row * 10 + col)
            width = len(value) * 3
            word(value, 272 + col * 60 - width, 45 + row * 12, width)
    tables = framed_table_candidates(source)
    assert len(tables) == 1
    table = tables[0]
    assert table['n_cols'] == 11
    assert [table['rows'][2]['cells'][i]['text'] for i in (2, 5, 8)] == ['2022', '2021', '2020']
    assert [table['rows'][i]['cells'][2]['text'] for i in (4, 5, 6)] == ['0', '-', '']
    assert _grid(table) is not None
