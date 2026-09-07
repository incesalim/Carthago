import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations


@pytest.fixture
def sample():
    directory = Path(__file__).parent / 'fixtures'
    fixture = json.loads((directory / 'document_complete_table_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((directory / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('page') == 6]
    return ({'source': fixture['source'], 'pages': [fixture['page']]},
            [{'source': fixture['source']}, fixture['source_page']], annotation)


def test_every_slot_period_span_and_unit_witness_matches_the_reviewed_source(sample):
    assert check_annotations(*sample)['passed']
    assert len(sample[2]['cases'][0]['rows']) == 8
    assert sum(map(len, sample[2]['cases'][0]['rows'])) == 40


@pytest.mark.parametrize('mutation', ['drop_row', 'drop_slot', 'duplicate_row', 'swap_periods',
                                     'swap_same_value_source', 'change_name', 'null_to_blank',
                                     'null_to_zero', 'extra_source_word', 'unit_change', 'wrong_pdf'])
def test_full_table_check_rejects_omissions_and_false_associations(sample, mutation):
    structure, evidence, annotation = sample
    table = next(t for t in structure['pages'][0]['tables'] if t['method'] == 'pymupdf_lines_strict')
    if mutation == 'drop_row':
        table['rows'].pop()
    elif mutation == 'drop_slot':
        table['rows'][0]['cells'].pop()
    elif mutation == 'duplicate_row':
        table['rows'][3] = copy.deepcopy(table['rows'][2])
    elif mutation == 'swap_periods':
        table['rows'][0]['cells'][1]['text'], table['rows'][0]['cells'][3]['text'] = (
            table['rows'][0]['cells'][3]['text'], table['rows'][0]['cells'][1]['text'])
    elif mutation == 'swap_same_value_source':
        first, second = table['rows'][2]['cells'][1], table['rows'][2]['cells'][3]
        first['word_ids'], second['word_ids'] = second['word_ids'], first['word_ids']
    elif mutation == 'change_name':
        table['rows'][2]['cells'][0]['text'] = 'Another shareholder'
    elif mutation in ('null_to_blank', 'null_to_zero'):
        table['rows'][0]['cells'][2]['text'] = '' if mutation == 'null_to_blank' else '0'
    elif mutation == 'extra_source_word':
        evidence[1]['words'].append({'id': 100000, 'text': '999', 'bbox': [250, 530, 270, 535]})
    elif mutation == 'unit_change':
        span = next(s for s in evidence[1]['spans'] if 'Tutarlar aksi' in s['text'])
        span['text'] = span['text'].replace('Bin Türk Lirası', 'Milyon Türk Lirası')
    else:
        annotation['pdf_sha256'] = 'f' * 64
    assert not check_annotations(structure, evidence, annotation)['passed']
