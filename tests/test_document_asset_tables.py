import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations

ROOT = Path(__file__).parent / 'fixtures'


@pytest.fixture
def asset_tables():
    fixture = json.loads((ROOT / 'document_asset_tables_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((ROOT / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('page') == 38]
    assert len(annotation['cases']) == 4
    return fixture, annotation


def _check(fixture, annotation):
    return check_annotations({'source': fixture['source'], 'pages': [fixture['page']]},
                             [{'source': fixture['source']}, fixture['source_page']], annotation)


def test_all_four_complete_tables_match_independent_source_transcriptions_and_qualifications(asset_tables):
    fixture, annotation = asset_tables
    assert sum(len(case['rows']) * len(case['rows'][0]) for case in annotation['cases']) == 121
    assert _check(fixture, annotation)['passed']
    assert fixture['page']['tables'][-1]['rows'][-1]['cells'][-1]['text'] == '1.545'


@pytest.mark.parametrize('table_index', range(4))
@pytest.mark.parametrize('mutation', ['drop_table', 'swap_repeated_occurrences', 'blank_to_zero', 'changed_units'])
def test_complete_source_cases_detect_omission_wrong_occurrence_and_invented_values(asset_tables, table_index, mutation):
    fixture, annotation = asset_tables
    case = annotation['cases'][table_index]
    annotation['cases'] = [case]
    table = fixture['page']['tables'][table_index]
    if mutation == 'drop_table': fixture['page']['tables'].remove(table)
    if mutation == 'swap_repeated_occurrences':
        cells = [c for row in table['rows'] for c in row['cells'] if c['word_ids']]
        first, second = next((a, b) for i, a in enumerate(cells) for b in cells[i + 1:] if a['text'] == b['text'])
        first['word_ids'], second['word_ids'] = second['word_ids'], first['word_ids']
    if mutation == 'blank_to_zero': table['rows'][0]['cells'][0]['text'] = '0'
    if mutation == 'changed_units':
        unit = next(s for s in fixture['source_page']['spans'] if 'belirtilmedikçe' in s['text'])
        unit['text'] = unit['text'].replace('Bin Türk', 'Milyon Türk')
    assert not _check(fixture, annotation)['passed']


def test_financial_asset_source_asterisk_qualification_cannot_be_dropped(asset_tables):
    fixture, annotation = asset_tables
    annotation['cases'] = [annotation['cases'][1]]
    fixture['source_page']['spans'] = [s for s in fixture['source_page']['spans'] if 'Fonları’ndan' not in s['text']]
    assert not _check(fixture, annotation)['passed']
