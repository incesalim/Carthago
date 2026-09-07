import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from src.audit_reports.document_table_rows import table_source_rows, verify_table_source_rows


@pytest.fixture
def sample():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_table_source_rows_tomk.json')
                         .read_text(encoding='utf-8'))
    return fixture['pages'][0], fixture['source_pages'][0]


def test_source_lines_keep_note_references_and_dates_in_their_original_columns(sample):
    page, source = sample
    original = copy.deepcopy(page)
    result = table_source_rows(page, source)
    assert page == original
    split = result['tables'][0]['split_rows'][0]
    assert split['source_row'] == 1 and len(split['lines']) == 64
    rows = [[c['text'] for c in line['cells']] for line in split['lines']]
    assert rows[0] == ['I. KAR PAYI GELİRLERİ', '(1)', '112.338', '-']
    assert rows[-2] == ['XXIV. NET DÖNEM KARI/ZARARI (XIII+XXIII)', '(11)', '148.071', '-']
    assert rows[-1] == ['Hisse Başına Kar/Zarar (Tam TL)', '', '0,09871', '-']
    table = next(t for t in page['tables'] if t['id'] == result['tables'][0]['table_id'])
    observed = Counter(i for line in split['lines'] for c in line['cells'] for i in c['word_ids'])
    assert observed == Counter(i for c in table['rows'][1]['cells'] for i in c['word_ids'])
    assert not observed.keys() & {i for c in table['rows'][0]['cells'] for i in c['word_ids']}
    assert all('value' not in c for line in split['lines'] for c in line['cells'])
    assert result['logical_rows_verified'] is False


@pytest.mark.parametrize('mutation', ['drop_word', 'duplicate_word', 'move_word', 'extra_word', 'overlap_lines'])
def test_incomplete_or_ambiguous_source_bindings_do_not_create_a_line_view(sample, mutation):
    page, source = sample
    table = next(t for t in page['tables'] if t['method'] == 'pymupdf_lines_strict')
    cell = table['rows'][1]['cells'][2]
    word = next(w for w in source['words'] if w['id'] == cell['word_ids'][0])
    if mutation == 'drop_word':
        cell['word_ids'].pop()
    elif mutation == 'duplicate_word':
        cell['word_ids'].append(cell['word_ids'][0])
    elif mutation == 'move_word':
        word['bbox'][0] = word['bbox'][2] = 550
    elif mutation == 'extra_word':
        source['words'].append({**word, 'id': 100000})
    else:
        # A glyph overlaps another baseline but has a different vertical center.
        word['bbox'][1] -= 4
        word['bbox'][3] += 5
    assert table_source_rows(page, source)['tables'] == []


@pytest.mark.parametrize('change', ['text', 'geometry', 'word_ref', 'drop_line', 'duplicate_line', 'drop_table'])
def test_saved_line_views_are_recomputed_from_source_not_trusted(sample, change):
    page, source = sample
    page['table_source_rows'] = table_source_rows(page, source)
    assert verify_table_source_rows(page, source) == []
    rows = page['table_source_rows']['tables'][0]['split_rows'][0]['lines']
    if change == 'text':
        rows[-2]['cells'][2]['text'] = '0'
    elif change == 'geometry':
        rows[-2]['cells'][2]['bbox'][0] += 10
    elif change == 'word_ref':
        rows[-2]['cells'][2]['word_ids'] = rows[0]['cells'][2]['word_ids']
    elif change == 'drop_line':
        rows.pop()
    elif change == 'duplicate_line':
        rows.append(copy.deepcopy(rows[0]))
    else:
        page['table_source_rows']['tables'] = []
    assert verify_table_source_rows(page, source) == ['table_source_rows_mismatch']


def test_independent_source_annotations_require_exact_text_and_column_positions(sample):
    from src.audit_reports.document_benchmark import check_annotations
    folder = Path(__file__).parent / 'fixtures'
    identity = json.loads((folder / 'document_table_source_rows_tomk.json').read_text(encoding='utf-8'))['source']
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['kind'] == 'source_table_line' and c['page'] == 13]
    assert len(annotation['cases']) == 3
    page, source = sample
    structure, evidence = {'source': identity, 'pages': [page]}, [{'source': identity}, source]
    assert not check_annotations(structure, evidence, annotation)['passed']
    page['table_source_rows'] = table_source_rows(page, source)
    assert check_annotations(structure, evidence, annotation)['passed']
    annotation['cases'][1]['columns'][1] = '-11'
    assert not check_annotations(structure, evidence, annotation)['passed']


@pytest.fixture
def cashflow():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_cashflow_columns_tomk.json').read_text(encoding='utf-8'))
    return fixture['pages'][0], fixture['source_pages'][0], fixture['source']


def test_cashflow_projection_preserves_the_physical_merge_and_every_source_occurrence(cashflow):
    page, source, _identity = cashflow
    original = copy.deepcopy(page)
    result = table_source_rows(page, source)
    split = result['tables'][0]['split_rows'][0]
    assert page == original and split['source_row'] == 2
    assert split['column_projection']['header_row'] == 1
    assert split['column_projection']['rule_witnesses'][0]['column_boundary'] == 3
    assert split['column_projection']['physical_cells_unchanged'] is True
    lines = split['lines']; assert len(lines) == 49
    assert [c['text'] for c in lines[47]['cells']] == ['VI. Dönem Başındaki Nakit ve Nakde Eşdeğer Varlıklar', '', '995.854', '-']
    assert [c['text'] for c in lines[48]['cells']] == ['VII. Dönem Sonundaki Nakit ve Nakde Eşdeğer Varlıklar', '', '391.720', '-']
    assert [c['text'] for c in lines[43]['cells']] == ['', '', '', '-']
    table = next(t for t in page['tables'] if t['id'] == 'p16:ruled0')
    assert Counter(i for line in lines for c in line['cells'] for i in c['word_ids']) == Counter(i for c in table['rows'][2]['cells'] for i in c['word_ids'])
    assert result['logical_rows_verified'] is False and all('value' not in c for line in lines for c in line['cells'])


@pytest.mark.parametrize('mutation', ['no_rule', 'long_gap', 'shift_rule', 'wide_rule', 'cross_column_word', 'missing_header', 'duplicate_word'])
def test_merged_column_projection_abstains_without_sufficient_unique_source_evidence(cashflow, mutation):
    page, source, _identity = cashflow
    table = next(t for t in page['tables'] if t['id'] == 'p16:ruled0')
    rules = [d for d in source['drawings'] if abs((d['bbox'][0] + d['bbox'][2]) / 2 - 470.23) < .5 and d['bbox'][1] >= 144]
    if mutation == 'no_rule': source['drawings'] = [d for d in source['drawings'] if d not in rules]
    if mutation == 'long_gap': source['drawings'] = [d for d in source['drawings'] if d not in rules or not 200 < d['bbox'][1] < 260]
    if mutation == 'shift_rule':
        for d in rules: d['bbox'][0] += 5; d['bbox'][2] += 5
    if mutation == 'wide_rule':
        for d in rules: d['bbox'][0] -= 3
    if mutation == 'cross_column_word':
        word = next(w for w in source['words'] if w['id'] == 452)
        word['bbox'][0] = 468; word['bbox'][2] = 476
    if mutation == 'missing_header': table['rows'][1]['cells'][3]['word_ids'] = []
    if mutation == 'duplicate_word': table['rows'][2]['cells'][2]['word_ids'].append(452)
    assert table_source_rows(page, source)['tables'] == []


def test_independent_cashflow_source_cases_require_the_projected_columns(cashflow):
    from src.audit_reports.document_benchmark import check_annotations
    page, source, identity = cashflow
    annotation = json.loads((Path(__file__).parent / 'fixtures/document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('page') == 16 and c.get('kind') == 'source_table_line']
    assert len(annotation['cases']) == 3
    structure, evidence = {'source': identity, 'pages': [page]}, [{'source': identity}, source]
    assert not check_annotations(structure, evidence, annotation)['passed']
    page['table_source_rows'] = table_source_rows(page, source)
    assert check_annotations(structure, evidence, annotation)['passed']
    saved = page['table_source_rows']['tables'][0]['split_rows'][0]
    saved['column_projection']['rule_witnesses'][0]['source_drawing_ids'].pop()
    assert verify_table_source_rows(page, source) == ['table_source_rows_mismatch']


@pytest.fixture
def equity():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_equity_source_rows_tomk.json').read_text(encoding='utf-8'))
    return fixture['pages'][0], fixture['source_pages'][0], fixture['source']


def test_equity_spanning_label_cell_keeps_body_and_final_balance_once(equity):
    page, source, _identity = equity
    original = copy.deepcopy(page)
    result = table_source_rows(page, source)
    assert page == original and len(result['tables']) == 1
    split = result['tables'][0]['split_rows'][0]
    assert split['source_row'] == 2 and split['row_group']['source_rows'] == [2, 3]
    assert split['row_group']['spanning_cells'] == [{'row': 2, 'column': 0, 'row_span': 2, 'column_span': 1}]
    assert len(split['lines']) == 19 and all(len(line['cells']) == 17 for line in split['lines'])
    assert [c['text'] for c in split['lines'][18]['cells']] == [
        'Dönem Sonu Bakiyesi (III+IV+…...+X+XI)', '1.500.000', '-', '-', '-', '-', '(5)', '-', '-', '-', '-', '-',
        '(1.870)', '148.071', '1.646.196', '-', '1.646.196']
    table = next(t for t in page['tables'] if t['id'] == 'p15:ruled0')
    expected = Counter(i for row in table['rows'][2:4] for c in row['cells'] for i in c['word_ids'])
    observed = Counter(i for line in split['lines'] for c in line['cells'] for i in c['word_ids'])
    assert expected == observed and all(n == 1 for n in observed.values())
    assert not observed.keys() & {i for row in table['rows'][:2] for c in row['cells'] for i in c['word_ids']}
    assert result['logical_rows_verified'] is False


@pytest.mark.parametrize('mutation', ['missing_balance', 'duplicate_balance', 'broken_span', 'cross_column', 'overlap_lines'])
def test_equity_line_group_abstains_on_incomplete_or_ambiguous_source(equity, mutation):
    page, source, _identity = equity
    table = next(t for t in page['tables'] if t['id'] == 'p15:ruled0')
    last = table['rows'][3]['cells'][16]
    if mutation == 'missing_balance': last['word_ids'] = []
    if mutation == 'duplicate_balance': last['word_ids'].append(last['word_ids'][0])
    if mutation == 'broken_span': table['rows'][2]['cells'][0]['bbox'][3] -= 1
    if mutation == 'cross_column':
        word = next(w for w in source['words'] if w['id'] == table['rows'][2]['cells'][13]['word_ids'][0])
        word['bbox'][0] = 602
    if mutation == 'overlap_lines':
        word = next(w for w in source['words'] if w['id'] == last['word_ids'][0])
        word['bbox'][1] -= 6
    assert table_source_rows(page, source)['tables'] == []


def test_equity_source_cases_fail_before_grouping_and_reject_a_minted_row_witness(equity):
    from src.audit_reports.document_benchmark import check_annotations
    page, source, identity = equity
    annotation = json.loads((Path(__file__).parent / 'fixtures/document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('page') == 15 and c.get('kind') == 'source_table_line']
    assert len(annotation['cases']) == 4
    structure, evidence = {'source': identity, 'pages': [page]}, [{'source': identity}, source]
    assert not check_annotations(structure, evidence, annotation)['passed']
    page['table_source_rows'] = table_source_rows(page, source)
    assert check_annotations(structure, evidence, annotation)['passed']
    page['table_source_rows']['tables'][0]['split_rows'][0]['row_group']['source_rows'].pop()
    assert verify_table_source_rows(page, source) == ['table_source_rows_mismatch']
