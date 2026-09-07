"""Independent full-table and prose acceptance for original TOMK pages 36–37."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations, paragraph_digest

FOLDER = Path(__file__).parent / 'fixtures'


@pytest.fixture
def review():
    fixture = json.loads((FOLDER / 'document_leverage_risk_prose_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((FOLDER / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in fixture['case_ids']]
    return ({'source': fixture['source'], 'pages': fixture['pages']},
            [{'source': fixture['source']}, *fixture['source_pages']], annotation)


def test_two_complete_tables_and_ten_complete_paragraphs_match_original_source(review):
    before = deepcopy(review)
    result = check_annotations(*review)
    assert result['passed'] and result['cases_checked'] == 12
    assert len(result['reviewed_tables']) == 2
    assert sum(len(t['physical_rows']) for t in result['reviewed_tables']) == 49
    assert sum(len(row) for t in result['reviewed_tables'] for row in t['physical_rows']) == 223
    paragraphs = [c for c in review[2]['cases'] if c['kind'] == 'narrative']
    assert len(paragraphs) == 10
    assert all(paragraph_digest(c['text']) == c['text_sha256'] for c in paragraphs)
    tables = {c['id']: c for c in review[2]['cases'] if c['kind'] == 'complete_physical_table'}
    leverage = tables['complete_leverage_current_and_prior']
    assert leverage['rows'][2][2:] == ['1.670.348', '1.513.102']
    assert leverage['rows'][-1][2:] == ['%93,47', '%98,79']
    assert leverage['rows'][1][2:] == ['', '']
    assert leverage['source_text_regions'][1]['text'].startswith('(*) Tabloda')
    rwa = tables['complete_risk_weighted_assets']
    assert rwa['rows'][0][3] is None
    assert rwa['rows'][-1][2:] == ['1.662.104', '1.513.102', '132.968']
    assert review == before


@pytest.mark.parametrize('change', ['one_lira', 'shifted_periods', 'blank_zero',
                                   'prose_text_only', 'prose_text_and_digest', 'wrong_heading'])
def test_review_rejects_transcription_source_and_association_errors(review, change):
    cases = {c['id']: c for c in review[2]['cases']}
    if change == 'one_lira':
        cases['complete_leverage_current_and_prior']['rows'][2][2] = '1.670.349'
    elif change == 'shifted_periods':
        row = cases['complete_risk_weighted_assets']['rows'][2]
        row[2], row[3] = row[3], row[2]
    elif change == 'blank_zero':
        cases['complete_leverage_current_and_prior']['rows'][1][2] = '0'
    else:
        paragraph = cases['complete_risk_paragraph_p36_2']
        if change == 'wrong_heading':
            paragraph['heading_path'] = ['VII. RİSK YÖNETİMİNE İLİŞKİN AÇIKLAMALAR']
        else:
            paragraph['text'] = 'Bulunmaktadır.'
            if change == 'prose_text_and_digest':
                paragraph['text_sha256'] = paragraph_digest(paragraph['text'])
    result = check_annotations(*review)
    assert not result['passed'] and 'reviewed_tables' not in result
