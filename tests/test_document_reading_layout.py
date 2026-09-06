import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_reading_layout import reading_layout, verify_reading_layout


@pytest.fixture
def sample():
    directory = Path(__file__).parent / 'fixtures'
    fixture = json.loads((directory / 'document_reading_layout_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((directory / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['kind'] == 'reading_layout']
    return fixture, annotation


def test_original_footer_order_bullets_and_six_signatory_columns(sample):
    fixture, annotation = sample
    before = copy.deepcopy(fixture)
    for page, source in zip(fixture['pages'], fixture['source_pages'], strict=True):
        view = reading_layout(page, source)
        assert not view['issues']
        assert Counter(view['element_order']) == Counter(e['id'] for e in page['narrative_elements'])
        assert view['reading_order_verified'] is False
        assert view['paragraph_boundaries_verified'] is False
        page['reading_layout'] = view
    structure = {'source': fixture['source'], 'pages': fixture['pages']}
    evidence = [{'source': fixture['source']}, *fixture['source_pages']]
    assert len(annotation['cases']) == 2
    assert check_annotations(structure, evidence, annotation)['passed']
    for original, page in zip(before['pages'], fixture['pages'], strict=True):
        assert original['narrative_elements'] == page['narrative_elements']
    assert fixture['source_pages'] == before['source_pages']


@pytest.mark.parametrize('change', ['drop', 'duplicate', 'footer_first', 'remove_pair', 'wrong_column', 'change_source_text'])
def test_source_layout_mutations_fail(sample, change):
    fixture, annotation = sample
    for page, source in zip(fixture['pages'], fixture['source_pages'], strict=True):
        page['reading_layout'] = reading_layout(page, source)
    first, second = fixture['pages']
    if change == 'drop':
        first['reading_layout']['element_order'].pop()
    elif change == 'duplicate':
        first['reading_layout']['element_order'].append('p2:narrative0')
    elif change == 'footer_first':
        first['reading_layout']['element_order'].insert(0, first['reading_layout']['element_order'].pop())
    elif change == 'remove_pair':
        second['reading_layout']['list_pairs'].pop()
    elif change == 'wrong_column':
        annotation['cases'][1]['column_groups'][1][1].append('p4:narrative28')
    else:
        first['narrative_elements'][0]['text'] += ' altered'
    assert not check_annotations({'source': fixture['source'], 'pages': fixture['pages']},
                                 [{'source': fixture['source']}, *fixture['source_pages']], annotation)['passed']


def test_nonunique_bullet_association_stays_separate(sample):
    fixture, _ = sample
    page, source = fixture['pages'][1], fixture['source_pages'][1]
    other = copy.deepcopy(page['narrative_elements'][7])
    other['id'] = 'alternative'
    page['narrative_elements'].append(other)
    view = reading_layout(page, source)
    assert ['p4:narrative6', 'p4:narrative7'] not in view['list_pairs']
    assert view['issues']
    assert set(view['element_order']) == {e['id'] for e in page['narrative_elements']}


def test_overlapping_elements_keep_source_order_with_explicit_issue(sample):
    fixture, _ = sample
    page, source = fixture['pages'][0], fixture['source_pages'][0]
    page['narrative_elements'] = page['narrative_elements'][:2]
    page['narrative_elements'][0]['bbox'] = page['narrative_elements'][1]['bbox']
    view = reading_layout(page, source)
    assert view['tree']['kind'] == 'unresolved_overlap'
    assert view['element_order'] == ['p2:narrative0', 'p2:narrative1']
    assert len(view['issues']) == 1


def test_old_pages_remain_readable_and_empty_pages_have_no_invented_content():
    assert verify_reading_layout({}, {}) == []
    view = reading_layout({'narrative_elements': []}, {'spans': []})
    assert view['tree'] is None and view['element_order'] == [] and view['list_pairs'] == []
