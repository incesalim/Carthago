from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_table_headers import add_period_headers, table_period_headers, verify_period_headers


@pytest.fixture
def source():
    data = json.loads((Path(__file__).parent / 'fixtures/document_period_headers_tomk.json').read_text(encoding='utf-8'))
    return {'source': data['source'], 'pages': data['pages']}, [{'source': data['source']}, *data['source_pages']]


def test_original_capital_pages_keep_separate_dated_headers_despite_merged_physical_cell(source):
    structure, evidence = source
    before = deepcopy(structure)
    add_period_headers(structure, evidence)
    expected = ['Cari Dönem\n30 Eylül 2023', 'Önceki Dönem\n31 Aralık 2022']
    for page, source_page, row in zip(structure['pages'][:3], evidence[1:4], [0, 0, 1], strict=True):
        header = page['table_period_headers']['tables'][0]
        assert header['status'] == 'unique_printed_band'
        assert header['table_id'] == f"p{page['page']}:ruled0"
        band = header['bands'][0]
        assert band['source_row'] == row
        assert [c['text'] for c in band['columns'][1:]] == expected
        # Independently visible source amount-column headings are on the right,
        # above the first data row, never in the left label column.
        for column, left, right in [(band['columns'][1], 410, 477), (band['columns'][2], 474, 539)]:
            assert left <= column['bbox'][0] < column['bbox'][2] <= right
        assert band['bbox'][1] <= min(c['bbox'][1] for c in band['columns'] if c['bbox'])
        assert page['tables'] == before['pages'][page['page'] - 26]['tables']
    first = structure['pages'][0]['table_period_headers']['tables'][0]['bands'][0]
    assert first['columns'][0]['text'] == 'ÇEKİRDEK SERMAYE'
    assert structure['pages'][3]['table_period_headers']['tables'] == []
    assert verify_period_headers(structure, evidence) == []


@pytest.mark.parametrize('change', ['date', 'swapped_sources', 'missing_word', 'duplicated_word', 'band_bounds',
                                  'missing_page', 'missing_all_views', 'missing_schema', 'all_markers_removed', 'invented_prior_header'])
def test_changed_headers_cannot_pass_source_recomputation(source, change):
    structure, evidence = source
    add_period_headers(structure, evidence)
    band = structure['pages'][0]['table_period_headers']['tables'][0]['bands'][0]
    if change == 'date':
        band['columns'][1]['text'] = 'Cari Dönem\n30 Eylül 2024'
    elif change == 'swapped_sources':
        band['columns'][1]['source_fragments'], band['columns'][2]['source_fragments'] = (
            band['columns'][2]['source_fragments'], band['columns'][1]['source_fragments'])
    elif change == 'missing_word':
        band['columns'][1]['source_fragments'].pop()
    elif change == 'duplicated_word':
        band['columns'][1]['source_fragments'].append(band['columns'][1]['source_fragments'][0])
    elif change == 'band_bounds':
        band['bbox'][3] += 10
    elif change == 'missing_page':
        del structure['pages'][1]['table_period_headers']
    elif change == 'missing_all_views':
        for page in structure['pages']:
            del page['table_period_headers']
    elif change == 'missing_schema':
        del structure['table_period_headers_schema']
    elif change == 'all_markers_removed':
        from src.audit_reports.document_header_upgrade import TARGET_ENGINE
        structure['engine'] = TARGET_ENGINE
        del structure['table_period_headers_schema']
        for page in structure['pages']:
            del page['table_period_headers']
    else:
        structure['pages'][3]['table_period_headers'] = deepcopy(structure['pages'][2]['table_period_headers'])
    assert verify_period_headers(structure, evidence)


@pytest.mark.parametrize('change', ['crossing_column', 'missing_cell_source', 'extra_source_word', 'unsupported_grid'])
def test_ambiguous_header_geometry_abstains(source, change):
    structure, evidence = source
    page, native = structure['pages'][0], evidence[1]
    table = next(t for t in page['tables'] if t['id'] == 'p26:ruled0')
    header_ids = table['rows'][0]['cells'][0]['word_ids']
    if change == 'crossing_column':
        word = next(w for w in native['words'] if w['id'] == header_ids[0])
        word['bbox'][0], word['bbox'][2] = 400, 430
    elif change == 'missing_cell_source':
        header_ids.pop()
    elif change == 'extra_source_word':
        word = deepcopy(next(w for w in native['words'] if w['id'] == header_ids[0]))
        word['id'] = 999999
        native['words'].append(word)
    else:
        table['rows'][3]['cells'][1]['bbox'][2] -= 5
    assert not table_period_headers(page, native)['tables']


def test_registered_source_header_cases_reject_missing_view_and_changed_printed_dates(source):
    from src.audit_reports.document_benchmark import check_annotations
    path = Path(__file__).parent / 'fixtures/document_annotations/tomk_2023q3_solo.json'
    annotation = json.loads(path.read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('kind') == 'table_period_headers']
    assert len(annotation['cases']) == 4
    structure, evidence = source
    assert not check_annotations(structure, evidence, annotation)['passed']
    add_period_headers(structure, evidence)
    assert check_annotations(structure, evidence, annotation)['passed']
    word = next(w for w in evidence[1]['words'] if w['id'] == 160)
    assert word['text'] == '2023'
    word['text'] = '2024'
    add_period_headers(structure, evidence)
    assert not check_annotations(structure, evidence, annotation)['passed']
