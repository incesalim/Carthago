import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_segmented_tables import segmented_table_candidates, verify_segmented_tables
from src.audit_reports.document_table_context import table_context

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def tax():
    packet = json.loads((FIXTURES / 'document_segmented_tax_tomk.json').read_text(encoding='utf-8'))
    return packet['pages'][0], packet['source_pages'][0], packet['source']


def _add(page, source):
    page['tables'].extend(segmented_table_candidates(source, page['tables']))
    page['segmented_tables_schema'] = 'segmented-table-candidates-1'
    page['table_context'] = table_context([page])[0]


def _check(page, source, identity):
    annotation = json.loads((FIXTURES / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] == 'complete-deferred-tax-table-with-grouped-headings']
    assert len(annotation['cases']) == 1
    return check_annotations({'source': identity, 'pages': [page]}, [{'source': identity}, source], annotation)


def test_complete_source_table_preserves_every_word_grouped_heading_blank_and_literal_total(tax):
    page, source, identity = tax
    original_page, original_source = copy.deepcopy(page), copy.deepcopy(source)
    candidates = segmented_table_candidates(source, page['tables'])
    assert page == original_page and source == original_source and len(candidates) == 1
    table = candidates[0]
    used = Counter(i for row in table['rows'] for c in row['cells'] for i in c['word_ids'])
    assert used == Counter(range(52, 121)) and all(n == 1 for n in used.values())
    assert table['rows'][7]['cells'][1]['text'] == '' and table['rows'][0]['cells'][2]['text'] is None
    assert table['rows'][4]['cells'][1]['text'] == '55.203'  # Retain the printed rounded total.
    assert table['semantic_verification'] == 'not_performed'
    assert not _check(page, source, identity)['passed']
    _add(page, source)
    assert page['tables'][:-1] == original_page['tables']
    assert _check(page, source, identity)['passed'] and not verify_segmented_tables(page, source)
    wire = json.loads((FIXTURES / 'document_segmented_tax_preview_wire.json').read_text(encoding='utf-8'))
    assert wire == {'table': table, 'context': page['table_context']['tables'][-1]}


@pytest.mark.parametrize('mutation', ['remove_period_rule', 'overlapping_header_groups', 'truncated_header_block', 'cross_amount_column', 'missing_net_value'])
def test_ambiguous_header_or_amount_source_abstains(tax, mutation):
    page, source, _identity = tax
    if mutation == 'remove_period_rule':
        source['drawings'] = [d for d in source['drawings'] if d['id'] != 3]
    if mutation == 'overlapping_header_groups':
        next(w for w in source['words'] if w['id'] == 54)['block'] = 5
    if mutation == 'truncated_header_block':
        source['words'][0]['block'] = 4
    if mutation == 'cross_amount_column':
        next(w for w in source['words'] if w['id'] == 83)['bbox'][0] = 340
    if mutation == 'missing_net_value':
        source['words'] = [w for w in source['words'] if w['id'] != 120]
    assert segmented_table_candidates(source, page['tables']) == []


@pytest.mark.parametrize('mutation', ['drop_table', 'rule_witness', 'header_span', 'duplicate_word', 'swap_repeated_values', 'blank_to_zero', 'source_units'])
def test_source_validation_or_full_region_benchmark_rejects_corruption(tax, mutation):
    page, source, identity = tax
    _add(page, source)
    table = page['tables'][-1]
    if mutation == 'drop_table': page['tables'].pop()
    if mutation == 'rule_witness': table['rule_witnesses'][0]['drawing_ids'].pop()
    if mutation == 'header_span': table['rows'][0]['cells'][1]['bbox'][2] -= 10
    if mutation == 'duplicate_word': table['rows'][2]['cells'][1]['word_ids'] *= 2
    if mutation == 'swap_repeated_values':
        a, b = table['rows'][5]['cells'][1], table['rows'][6]['cells'][1]
        a['word_ids'], b['word_ids'] = b['word_ids'], a['word_ids']
    if mutation == 'blank_to_zero': table['rows'][7]['cells'][1]['text'] = '0'
    if mutation == 'source_units':
        span = next(s for s in source['spans'] if 'belirtilmedikçe' in s['text'])
        span['text'] = span['text'].replace('Bin Türk', 'Milyon Türk')
    assert verify_segmented_tables(page, source) or not _check(page, source, identity)['passed']


def test_older_capture_without_view_remains_readable(tax):
    page, source, _identity = tax
    assert verify_segmented_tables(page, source) == []
