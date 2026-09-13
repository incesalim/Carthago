"""Independently read equity rows, native-word accounting and abstention cases."""
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from src.audit_reports.document_equity_tables import SCHEMA, equity_table_candidates, verify_equity_tables
from src.audit_reports.document_table_context import _grid


@pytest.fixture(scope='module')
def fixture():
    return json.loads(gzip.decompress((Path(__file__).parent / 'fixtures/document_equity_table_garan.json.gz').read_bytes()))


def test_every_printed_amount_and_header_is_retained(fixture):
    source = fixture['source']
    table, = equity_table_candidates(source)
    assert table == fixture['structure']['tables'][-1]
    assert (table['row_count'], table['n_cols']) == (41, 18)
    rows = table['rows']
    assert rows[0]['cells'][2]['text'] == 'THOUSANDS OF TURKISH LIRA (TL)'
    assert rows[1]['cells'][6]['text'] == 'Other Comprehensive Income/Expense Items\nnot to be Recycled to Profit or Loss'
    assert rows[1]['cells'][9]['text'] == 'Other Comprehensive Income/Expense Items to\nbe Recycled to Profit or Loss'
    assert rows[2]['cells'][7]['text'] == "Defined\nBenefit Plans'\nActuarial\nGains/Losses"
    assert rows[2]['cells'][10]['text'] == 'Income/Expenses\nfrom Valuation\nand/or\nReclassification of\nFinancial Assets\nMeasured at\nFVOCI'
    assert [p['text'] for p in table['period_bands']] == ['PRIOR PERIOD\n(01/01/2021-31/12/2021)', 'CURRENT PERIOD\n(01/01/2022-31/12/2022)']
    body = [r for r in rows[3:] if r['cells'][2]['text']]
    assert len(body) == 34 and sum(bool(c['text']) for r in body for c in r['cells'][2:]) == 544
    # Read independently from the matching rendered original, including the
    # reserve/prior-profit transfer between prior closing and current opening.
    assert [c['text'] for c in rows[21]['cells'][12:]] == ['51,937,355', '548,851', '13,466,741', '79,981,339', '319,516', '80,300,855']
    assert [c['text'] for c in rows[24]['cells'][12:]] == ['51,937,355', '14,015,592', '-', '79,981,339', '319,516', '80,300,855']
    assert [c['text'] for c in rows[-1]['cells'][2:]] == ['4,200,000', '11,880', '-', '772,554', '5,405,144', '(1,315,532)', '471,809', '15,758,923', '8,711,262', '(4,556,136)', '63,782,784', '1,111,319', '58,285,378', '152,639,385', '484,735', '153,124,120']
    assert rows[9]['cells'][1]['text'] == rows[28]['cells'][1]['text'] == '5.5'
    grid = _grid(table)
    assert grid == fixture['structure']['table_context']['tables'][-1]['physical_grid']
    assert {'row': 1, 'column': 6, 'row_span': 1, 'column_span': 3} in grid['anchors']
    assert table['review_status'] == 'unreviewed' and table['header_association_verified'] is False
    x0, y0, x1, y1 = table['bbox']
    selected = [w for w in source['words'] if x0 < (w['bbox'][0] + w['bbox'][2]) / 2 < x1
                and y0 < (w['bbox'][1] + w['bbox'][3]) / 2 < y1]
    assert Counter(i for r in rows for c in r['cells'] for i in c['word_ids']) == Counter(w['id'] for w in selected)
    assert all('accompanying notes' not in (c['text'] or '') for r in rows for c in r['cells'])
    assert rows[21]['cells'][0]['text'] == 'Balances at end of the period (III+IV+…+X+XI)'


@pytest.mark.parametrize('mutation', ['table', 'row', 'column', 'header', 'amount', 'note', 'period', 'unit', 'word', 'schema', 'review'])
def test_structural_verifier_detects_source_corruption(fixture, mutation):
    source = fixture['source']
    page = {'tables': equity_table_candidates(source), 'equity_tables_schema': SCHEMA}
    assert verify_equity_tables(page, source) == []
    t = page['tables'][0]
    if mutation == 'table':
        page['tables'] = []
    elif mutation == 'row':
        t['rows'].pop(24)
    elif mutation == 'column':
        for r in t['rows']:
            r['cells'].pop(7)
    elif mutation in ('header', 'amount', 'note', 'unit'):
        r, c = {'header': (1, 6), 'amount': (29, 7), 'note': (28, 1), 'unit': (0, 2)}[mutation]
        t['rows'][r]['cells'][c]['text'] = ''
    elif mutation == 'period':
        t['period_bands'][0]['text'] = '2022'
    elif mutation == 'word':
        t['rows'][24]['cells'][13]['word_ids'] = []
    elif mutation == 'schema':
        page.pop('equity_tables_schema')
    else:
        t['review_status'] = 'verified'
    assert verify_equity_tables(page, source)


@pytest.mark.parametrize('mutation', ['frame', 'period', 'date', 'leaf', 'parent_overlap', 'amount_text', 'amount_collision', 'actualtext'])
def test_ambiguous_source_does_not_get_guessed_assignments(fixture, mutation):
    s = deepcopy(fixture['source'])
    t, = equity_table_candidates(s)
    if mutation == 'frame':
        s['drawings'].pop(4)
    elif mutation == 'actualtext':
        s['actualtext_changes_word_view'] = True
    else:
        r, c = {'period': (22, 0), 'date': (23, 0), 'leaf': (2, 8), 'parent_overlap': (1, 6),
                'amount_text': (24, 6), 'amount_collision': (24, 6)}[mutation]
        ids = t['rows'][r]['cells'][c]['word_ids']
        words = [w for w in s['words'] if w['id'] in ids]
        if mutation == 'leaf':
            s['words'] = [w for w in s['words'] if w['id'] not in ids]
        elif mutation in ('parent_overlap', 'amount_collision'):
            for w in words:
                w['bbox'][0] += 35
                w['bbox'][2] += 35
        else:
            words[0]['text'] = 'ambiguous'
    assert equity_table_candidates(s) == []


def test_partial_row_keeps_blank_dash_and_zero_distinct(fixture):
    s = deepcopy(fixture['source'])
    t, = equity_table_candidates(s)
    blank = t['rows'][24]['cells'][7]['word_ids']
    zero = t['rows'][24]['cells'][8]['word_ids']
    s['words'] = [w for w in s['words'] if w['id'] not in blank]
    for w in s['words']:
        if w['id'] in zero:
            w['text'] = '0'
    table, = equity_table_candidates(s)
    assert [table['rows'][24]['cells'][c]['text'] for c in (4, 7, 8, 9)] == ['-', '', '0', '10,662,419']


def test_no_fixed_page_position_row_count_or_amount_column_limit(fixture):
    s = deepcopy(fixture['source'])
    t, = equity_table_candidates(s)
    # Remove a complete, ungrouped column from the source, including its header.
    # The new inventory is 15 amounts, not a fabricated blank sixteenth column.
    removed = {i for row in t['rows'] for i in row['cells'][3]['word_ids']}
    removed.update(i for c in t['rows'][12]['cells'] for i in c['word_ids'])
    s['words'] = [w for w in s['words'] if w['id'] not in removed]
    for item in [*s['words'], *s['drawings']]:
        item['bbox'] = [v * 1.1 + (12 if i % 2 == 0 else 8) for i, v in enumerate(item['bbox'])]
    s['page'] = 80
    table, = equity_table_candidates(s)
    assert table['id'].startswith('p80:') and table['n_cols'] == 17 and table['row_count'] == 40
    assert table['rows'][-1]['cells'][-1]['text'] == '153,124,120'
