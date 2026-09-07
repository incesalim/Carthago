"""Source-based acceptance of the complete equity statement and five risk tables."""
import base64
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_cell_fragments import cell_word_fragments
from src.audit_reports.document_table_review import reviewed_logical_rows

FOLDER = Path(__file__).parent / 'fixtures'


@pytest.fixture
def review():
    fixtures = [json.loads((FOLDER / name).read_text(encoding='utf-8')) for name in (
        'document_equity_complete_tomk.json', 'document_risk_tomk.json')]
    ids = {i for f in fixtures for i in f['case_ids']}
    annotation = json.loads((FOLDER / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in ids]
    return ({'source': fixtures[0]['source'], 'pages': sorted([p for f in fixtures for p in f['pages']], key=lambda p: p['page'])},
            [{'source': fixtures[0]['source']}, *sorted([p for f in fixtures for p in f['source_pages']], key=lambda p: p['page'])], annotation)


def test_all_six_tables_conserve_every_printed_occurrence_and_literal_distinction(review):
    before = deepcopy(review)
    result = check_annotations(*review)
    assert result['passed'] and result['cases_checked'] == 7 and len(result['reviewed_tables']) == 6
    context = next(t['source_context'] for t in result['reviewed_tables'] if t['page'] == 15)
    assert len(context) == 8
    assert [c['text'].split('.')[0] for c in context[2:]] == ['1', '2', '3', '4', '5', '6']
    assert context[-1]['text'].endswith('tutarları ifade eder)')
    reviewed = {}
    for record in result['reviewed_tables']:
        page = next(p for p in review[0]['pages'] if p['page'] == record['page'])
        table = next(t for t in page['tables'] if t['id'] == record['table_id'])
        source = next(p for p in review[1][1:] if p['page'] == record['page'])
        case = next(c for c in review[2]['cases'] if c['id'] == record['review_id'])
        rows = reviewed_logical_rows(table, source, case)
        words = {w['id']: w for w in source['words']}
        physical = Counter((p['word_id'], i) for r in table['rows'] for c in r['cells']
                           for p in cell_word_fragments(c, words) for i in range(p['start'], p['end']))
        logical = Counter((p['word_id'], i) for r in rows for c in r['cells']
                          for p in c['source_fragments'] for i in range(p['start'], p['end']))
        assert logical == physical and all(v == 1 for v in logical.values())
        actual = [[None if c['text'] is None else ' '.join(c['text'].split()) for c in r['cells']] for r in rows]
        expected = [[c['text'] for c in r] for r in case['reviewed_grid']['rows']] if 'reviewed_grid' in case else case['rows']
        assert actual == expected
        reviewed[case['id']] = actual
    assert sum(len(r) for r in reviewed.values()) == 99
    assert sum(len(row) for r in reviewed.values() for row in r) == 746
    equity = reviewed['complete_equity_change_with_six_numbered_columns']
    assert equity[1][5:11] == ['1', '2', '3', '4', '5', '6']
    assert equity[2] == ['CARİ DÖNEM 30.09.2023', *([''] * 16)]
    assert equity[-1][6] == '(5)' and equity[-1][12:15] == ['(1.870)', '148.071', '1.646.196']
    assert equity[-1][16] == '1.646.196'
    assert reviewed['complete_fx_daily_rates'][1][1:] == reviewed['complete_fx_daily_rates'][2][1:]
    assert reviewed['complete-prior-fx-table-and-currency-units'][1][1:] == ['18,6983 TL', '19,9349 TL']
    assert reviewed['complete_current_liquidity_high_low'][1][1] == '80.980.325'
    assert reviewed['complete_prior_liquidity_coverage'][-1][2:] == ['', '', '142.085.400', '-']
    assert review == before


def test_python_review_records_and_source_pages_match_the_worker_wire(review):
    wire = json.loads((FOLDER / 'document_table_review_risk_wire.json').read_text(encoding='utf-8'))
    assert wire['index']['resume_receipt']['benchmark']['checks'][0] == check_annotations(*review)
    for kind, pages in [('source', review[1][1:]), ('structure', review[0]['pages'])]:
        decoded = [json.loads(line) for line in gzip.decompress(base64.b64decode(wire[f'{kind}_gzip'])).splitlines()]
        for page in pages:
            assert decoded[page['page']] == {'type': 'source_page' if kind == 'source' else 'structured_page', **page}


def test_two_cases_cannot_count_the_same_physical_table_twice(review):
    duplicate = deepcopy(next(c for c in review[2]['cases'] if c['id'] == 'complete-prior-fx-table-and-currency-units'))
    duplicate['id'] = 'another_name_for_the_same_table'
    review[2]['cases'].append(duplicate)
    result = check_annotations(*review)
    assert not result['passed'] and 'reviewed_tables' not in result
    assert any(f['kind'] == 'duplicate_complete_table_review' for f in result['failures'])


@pytest.mark.parametrize('change', ['liquidity_digit', 'prior_rate', 'empty_zero', 'missing_row', 'unit', 'equity_note_column'])
def test_review_fails_on_numeric_period_missingness_and_source_changes(review, change):
    cases = {c['id']: c for c in review[2]['cases']}
    if change == 'liquidity_digit':
        cases['complete_current_liquidity_high_low']['rows'][1][1] = '809.080.325'
    elif change == 'prior_rate':
        cases['complete-prior-fx-table-and-currency-units']['rows'][1][1] = '27,3767 TL'
    elif change == 'empty_zero':
        cases['complete_prior_liquidity_coverage']['rows'][-1][2] = '0'
    elif change == 'missing_row':
        cases['complete_fx_exposure_current_and_prior']['rows'].pop()
    elif change == 'unit':
        cases['complete_fx_daily_rates']['source_text_regions'][0]['text'] = 'Tutarlar milyon TL'
    else:
        cases['complete_equity_change_with_six_numbered_columns']['reviewed_grid']['rows'][1][6]['text'] = '3'
    result = check_annotations(*review)
    assert not result['passed'] and 'reviewed_tables' not in result
