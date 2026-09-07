import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_rule_tables import underline_candidates


@pytest.fixture
def sample():
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_underlined_table_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('page') == 30]
    return fixture, annotation


def test_complete_prior_rate_table_survives_segmented_borders_and_literal_units(sample):
    fixture, annotation = sample
    source = fixture['source_page']
    tables = underline_candidates(source, fixture['existing_tables'])
    assert len(tables) == 1
    assert [[c['text'] for c in r['cells']] for r in tables[0]['rows']] == [
        ['', 'USD', 'EURO'], ['Bilanço değerleme kuru', '18,6983 TL', '19,9349 TL']]
    assert tables[0]['source_drawing_ids'] == [11, 13, 15, 16, 18, 20]
    structure = {'source': fixture['source'], 'pages': [{'page': 30, 'tables': tables}]}
    evidence = [{'source': fixture['source']}, source]
    assert len(annotation['cases']) == 1 and check_annotations(structure, evidence, annotation)['passed']
    damaged = copy.deepcopy(structure)
    damaged['pages'][0]['tables'][0]['rows'][1]['cells'][1]['text'] = '18,6983'
    assert not check_annotations(damaged, evidence, annotation)['passed']


@pytest.mark.parametrize('change', ['drop_top_segment', 'shift_top_column', 'covered_table', 'missing_value_column'])
def test_unmatched_rules_or_missing_columns_do_not_create_the_small_table(sample, change):
    fixture, _ = sample
    source, existing = fixture['source_page'], fixture['existing_tables']
    if change == 'drop_top_segment':
        source['drawings'] = [d for d in source['drawings'] if d['id'] != 13]
    elif change == 'shift_top_column':
        next(d for d in source['drawings'] if d['id'] == 13)['bbox'][0] += 15
    elif change == 'covered_table':
        existing.append({'bbox': [125, 420, 540, 460]})
    else:
        source['words'] = [w for w in source['words'] if w['id'] not in (249, 250)]
    assert underline_candidates(source, existing) == []
