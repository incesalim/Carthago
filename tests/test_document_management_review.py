from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_narrative import narrative_candidates, verify_narrative


@pytest.fixture
def management():
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_management_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in fixture['case_ids']]
    assert len(annotation['cases']) == 9
    return {'source': fixture['source'], 'pages': fixture['pages']}, [{'source': fixture['source']}, *fixture['source_pages']], annotation


def test_complete_page_management_tables_and_prose_are_distinct_and_source_bound(management):
    structure, evidence, annotation = management
    page, source = structure['pages'][0], evidence[1]
    before = deepcopy((structure, evidence))
    result = check_annotations(structure, evidence, annotation)
    assert result['passed'] and len(result['reviewed_tables']) == 5
    assert sum(len(c['rows']) for c in annotation['cases'] if c['kind'] == 'complete_physical_table') == 29
    paragraphs = [e for e in page['narrative_elements'] if e['kind'] == 'paragraph_candidate']
    assert len(paragraphs) == 4
    assert [e['heading_path'][0]['text'] for e in paragraphs] == [
        'III. Ortaklık Yapısı', 'IV. 2023 Yılında Esas Sözleşmede Yapılan Değişiklikler',
        'V. Başlıca Finansal Göstergeler', 'V. Başlıca Finansal Göstergeler']
    assert paragraphs[1]['text'].strip() == 'Bulunmamaktadır.'
    assert all(e['table_ids'] == [] and e['candidate_table_ids'] == ['p50:numeric1'] for e in paragraphs)
    assert len([e for e in page['narrative_elements'] if e['kind'] == 'table_text']) == 5
    assert next(t for t in page['tables'] if t['id'] == 'p50:numeric1')['bbox'][1] < paragraphs[0]['bbox'][1]
    expected = Counter(s['id'] for s in source['spans'] if s['text'].strip())
    actual = Counter(i for e in page['narrative_elements'] for i in e['span_ids'] if next(s for s in source['spans'] if s['id'] == i)['text'].strip())
    assert expected == actual and all(n == 1 for n in actual.values())
    assert not verify_narrative(page, source)
    assert (structure, evidence) == before
    # A whole-page numeric rectangle cannot absorb the paragraphs, even when
    # its inferred bounds are widened to include every source span.
    isolated = deepcopy(page)
    reference = deepcopy(page)
    narrative_candidates([reference], [evidence[0], source], [])
    next(t for t in isolated['tables'] if t['id'] == 'p50:numeric1')['bbox'] = [0, 0, source['width'], source['height']]
    narrative_candidates([isolated], [evidence[0], source], [])
    assert [(e['kind'], e['text'], e['heading_path']) for e in isolated['narrative_elements']] == [
        (e['kind'], e['text'], e['heading_path']) for e in reference['narrative_elements']]


@pytest.mark.parametrize('change', ['wrong_heading', 'lose_negation', 'swap_paragraphs', 'wrong_period', 'liability_total_label',
                                  'ratio', 'pay_unit', 'drop_paragraph', 'drop_table', 'wrong_source_occurrence'])
def test_page_review_rejects_source_and_context_corruption(management, change):
    structure, evidence, annotation = management
    page = structure['pages'][0]
    paragraphs = [e for e in page['narrative_elements'] if e['kind'] == 'paragraph_candidate']
    if change == 'wrong_heading':
        paragraphs[1]['heading_path'] = deepcopy(paragraphs[0]['heading_path'])
    elif change == 'lose_negation':
        paragraphs[0]['text'] = paragraphs[0]['text'].replace('bulunmamaktadır', 'bulunmaktadır')
    elif change == 'swap_paragraphs':
        paragraphs[2]['span_ids'], paragraphs[3]['span_ids'] = paragraphs[3]['span_ids'], paragraphs[2]['span_ids']
    elif change == 'wrong_period':
        next(c for c in annotation['cases'] if c['id'] == 'complete_management_profit_loss')['rows'][0][2] = '30 Eylül 2022'
    elif change == 'liability_total_label':
        next(c for c in annotation['cases'] if c['id'] == 'complete_management_liabilities')['rows'][-1][0] = 'Toplam Pasifler'
    elif change == 'ratio':
        next(c for c in annotation['cases'] if c['id'] == 'complete_management_ratios')['rows'][1][1] = '93,75'
    elif change == 'pay_unit':
        next(c for c in annotation['cases'] if c['id'] == 'complete_management_ownership')['rows'][0][1] = 'Pay Tutarları (Bin TL)'
    elif change == 'drop_paragraph':
        page['narrative_elements'].remove(paragraphs[1])
    elif change == 'drop_table':
        page['tables'] = [t for t in page['tables'] if t['id'] != 'p50:ruled4']
    else:
        paragraphs[1]['span_ids'] = paragraphs[0]['span_ids']
    assert not check_annotations(structure, evidence, annotation)['passed']


@pytest.mark.parametrize('change', ['drop', 'invent', 'duplicate'])
def test_uncertain_candidate_membership_stays_visible_and_verifiable(management, change):
    structure, evidence, _ = management
    page = structure['pages'][0]
    element = next(e for e in page['narrative_elements'] if e['kind'] == 'paragraph_candidate')
    element['candidate_table_ids'] = [] if change == 'drop' else ['other'] if change == 'invent' else ['p50:numeric1'] * 2
    assert 'narrative_candidate_table_membership_mismatch' in verify_narrative(page, evidence[1])


def test_independent_garanti_balance_sheet_region_stays_table_text():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_narrative_table_holdout_garan.json').read_text(encoding='utf-8'))
    page, source = fixture['page'], fixture['source_page']
    box = fixture['reviewed_table_body_region']
    selected = {s['id'] for s in source['spans'] if s['text'].strip()
                and box[0] <= (s['bbox'][0] + s['bbox'][2]) / 2 <= box[2]
                and box[1] <= (s['bbox'][1] + s['bbox'][3]) / 2 <= box[3]}
    assert selected
    narrative_candidates([page], [{'source': fixture['source']}, source], [])
    owners = [e for e in page['narrative_elements'] if selected & set(e['span_ids'])]
    assert owners and all(e['kind'] == 'table_text' for e in owners)
    assert selected <= {i for e in owners for i in e['span_ids']}
    assert not verify_narrative(page, source)
