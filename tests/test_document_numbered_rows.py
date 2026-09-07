from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_numbered_rows import numbered_source_rows
from src.audit_reports.document_table_review import reviewed_logical_rows


@pytest.fixture
def sample():
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_numbered_rows_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in fixture['case_ids']]
    assert len(annotation['cases']) == 1
    return fixture, annotation


def test_complete_statement_groups_all_source_lines_and_retains_notes_units_and_repeated_codes(sample):
    fixture, annotation = sample
    page, source = fixture['pages'][0], fixture['source_pages'][0]
    before = deepcopy((page, source))
    result = numbered_source_rows(page, source)['tables']
    assert len(result) == 1
    view = result[0]
    assert view['witness_columns'] == [2, 3] and view['unresolved_lines'] == []
    assert len(view['rows']) == 62
    assert [i for row in view['rows'] for i in row['source_line_indices']] == list(range(64))
    literal = [[' '.join(c['text'].split()) for c in row['cells']] for row in view['rows']]
    assert literal == annotation['cases'][0]['numbered_rows'][0]['rows']
    assert literal[-2] == ['XXIV. NET DÖNEM KARI/ZARARI (XIII+XXIII)', '(11)', '148.071', '-']
    assert literal[-1] == ['Hisse Başına Kar/Zarar (Tam TL)', '', '0,09871', '-']
    assert [r['identifier'] for r in view['rows']].count('XIII.') == 2
    assert [r['source_line_indices'] for r in view['rows'] if len(r['source_line_indices']) > 1] == [[37, 38], [39, 40]]
    assert (page, source) == before
    check = check_annotations({'source': fixture['source'], 'pages': [page]},
                              [{'source': fixture['source']}, source], annotation)
    assert check['passed'] and len(check['reviewed_tables']) == 1
    table = next(t for t in page['tables'] if t['id'] == view['table_id'])
    rows = reviewed_logical_rows(table, source, annotation['cases'][0])
    assert len(rows) == 63 and len(table['rows']) == 2
    assert [r['source_row'] for r in rows] == [0] + [1] * 62
    assert all('value' not in c for row in rows for c in row['cells'])
    actual = Counter((p['word_id'], i) for row in rows for cell in row['cells']
                     for p in cell['source_fragments'] for i in range(p['start'], p['end']))
    expected = Counter((w['id'], i) for w in source['words']
                       if table['bbox'][0] <= (w['bbox'][0] + w['bbox'][2]) / 2 <= table['bbox'][2]
                       and table['bbox'][1] <= (w['bbox'][1] + w['bbox'][3]) / 2 <= table['bbox'][3]
                       for i in range(len(w['text'])))
    assert actual == expected and all(n == 1 for n in actual.values())


@pytest.mark.parametrize('change', ['figure', 'note_as_number', 'eps_unit', 'duplicate_word', 'missing_word',
                                  'different_dash_occurrence', 'wrong_column', 'row_order', 'missing_row',
                                  'duplicate_split', 'missing_review', 'empty_row', 'merge_printed_rows'])
def test_reviewed_split_rejects_corruption_and_row_misassociation(sample, change):
    fixture, annotation = sample
    case = annotation['cases'][0]
    split = case['row_splits'][0]
    rows = split['rows']
    if change == 'figure':
        rows[-2]['cells'][2]['text'] = '148.070'
    elif change == 'note_as_number':
        rows[-2]['cells'][1]['text'] = '-11'
    elif change == 'eps_unit':
        rows[-1]['cells'][0]['text'] = 'Hisse Başına Kar/Zarar (Bin TL)'
    elif change == 'duplicate_word':
        rows[0]['cells'][0]['source_word_ids'] *= 2
    elif change == 'missing_word':
        rows[0]['cells'][0]['source_word_ids'].pop()
    elif change == 'different_dash_occurrence':
        a, b = rows[1]['cells'][3], rows[2]['cells'][3]
        a['source_word_ids'], b['source_word_ids'] = b['source_word_ids'], a['source_word_ids']
    elif change == 'wrong_column':
        rows[-2]['cells'][1], rows[-2]['cells'][2] = rows[-2]['cells'][2], rows[-2]['cells'][1]
    elif change == 'row_order':
        rows[1], rows[2] = rows[2], rows[1]
    elif change == 'missing_row':
        rows.pop()
    elif change == 'duplicate_split':
        case['row_splits'].append(deepcopy(split))
    elif change == 'missing_review':
        split['source_review'] = ''
    elif change == 'empty_row':
        rows.insert(1, {'cells': [{'text': '', 'source_word_ids': []} for _ in range(4)]})
    else:
        for a, b in zip(rows[1]['cells'], rows[2]['cells'], strict=True):
            a['text'] += ' ' + b['text']
            a['source_word_ids'] += b['source_word_ids']
        rows.pop(2)
    result = check_annotations({'source': fixture['source'], 'pages': fixture['pages']},
                               [{'source': fixture['source']}, *fixture['source_pages']], annotation)
    assert not result['passed'] and 'reviewed_tables' not in result


def test_duplicate_complete_candidates_are_rejected_without_stopping_the_benchmark(sample):
    fixture, annotation = sample
    page = fixture['pages'][0]
    duplicate = deepcopy(next(t for t in page['tables'] if t['id'] == 'p13:ruled0'))
    duplicate['id'] = 'p13:duplicate'
    page['tables'].append(duplicate)
    result = check_annotations({'source': fixture['source'], 'pages': [page]},
                               [{'source': fixture['source']}, *fixture['source_pages']], annotation)
    assert not result['passed'] and 'reviewed_tables' not in result


def test_numbered_assembly_code_invalidates_table_receipts_only(tmp_path, monkeypatch):
    from src.audit_reports import document_numbered_rows
    from src.audit_reports.document_corpus_resume import annotation_identity
    folder = tmp_path / 'annotations'
    folder.mkdir()
    (folder / 'one.json').write_text(json.dumps({'cases': [{'kind': 'source_word', 'text': 'original'}]}))
    before = annotation_identity(folder)
    source_before = annotation_identity(folder, source_only=True)
    changed = tmp_path / 'numbered.py'
    changed.write_text('changed numbered assembly implementation')
    monkeypatch.setattr(document_numbered_rows, '__file__', str(changed))
    assert annotation_identity(folder) != before
    assert annotation_identity(folder, source_only=True) == source_before


@pytest.fixture(params=[14, 16])
def further_statement(request):
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_numbered_cf_oci_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] in fixture['case_ids'] and c['page'] == request.param]
    assert len(annotation['cases']) == 1
    return fixture, annotation


def test_complete_statements_keep_wrapping_merged_amounts_and_unassigned_marks(further_statement):
    fixture, annotation = further_statement
    case = annotation['cases'][0]
    page = next(p for p in fixture['pages'] if p['page'] == case['page'])
    source = next(p for p in fixture['source_pages'] if p['page'] == case['page'])
    table = next(t for t in page['tables'] if t['id'] == f"p{case['page']}:ruled0")
    grouped = numbered_source_rows(page, source)['tables'][0]
    rows = reviewed_logical_rows(table, source, case)
    assert len(rows) == (18 if case['page'] == 14 else 51)
    assert len(table['rows']) == 3
    assert [[" ".join(c['text'].split()) for c in row['cells']] for row in rows[2:]] == case['numbered_rows'][0]['rows']
    if case['page'] == 16:
        assert grouped['unresolved_lines'] == [35, 43, 45]
        assert [row['identifier'] for row in grouped['rows'] if row['identifier'] in ['A.', 'B.', 'C.']] == ['A.', 'B.', 'C.']
        assert table['rows'][2]['cells'][3]['text'] is None
        assert [i for i, row in enumerate(rows[2:]) if not row['cells'][0]['text']] == [35, 43, 45]
        assert all([c['text'] for c in rows[i + 2]['cells']] == ['', '', '', '-'] for i in [35, 43, 45])
        assert [c['text'] for c in rows[-1]['cells']] == ['VII. Dönem Sonundaki Nakit ve Nakde Eşdeğer Varlıklar', '', '391.720', '-']
    else:
        assert not grouped['unresolved_lines']
        assert len(grouped['rows'][10]['source_line_indices']) == 2
        assert 'Sınırlandırılmayacak' in rows[9]['cells'][0]['text']
    assert check_annotations({'source': fixture['source'], 'pages': fixture['pages']},
                             [{'source': fixture['source']}, *fixture['source_pages']], annotation)['passed']


@pytest.mark.parametrize('change', ['figure', 'date', 'row_merge', 'word_drop', 'wrong_column'])
def test_additional_statement_corruption_fails(further_statement, change):
    fixture, annotation = further_statement
    case = annotation['cases'][0]
    rows = case['row_splits'][0]['rows']
    if change == 'figure':
        rows[-1]['cells'][-2]['text'] = '0'
    elif change == 'date':
        case['rows'][1][-1] = 'Prior period 2021'
    elif change == 'row_merge':
        for a, b in zip(rows[1]['cells'], rows[2]['cells'], strict=True):
            a['text'] += ' ' + b['text']
            a['source_word_ids'] += b['source_word_ids']
        rows.pop(2)
    elif change == 'word_drop':
        rows[-1]['cells'][0]['source_word_ids'].pop()
    else:
        rows[-1]['cells'][-1], rows[-1]['cells'][-2] = rows[-1]['cells'][-2], rows[-1]['cells'][-1]
    assert not check_annotations({'source': fixture['source'], 'pages': fixture['pages']},
                                 [{'source': fixture['source']}, *fixture['source_pages']], annotation)['passed']


@pytest.mark.parametrize('change', ['omit', 'wrong_line', 'duplicate', 'missing_review'])
def test_unassigned_source_lines_require_an_exact_explicit_review(change):
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_numbered_cf_oci_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['id'] == 'complete_cash_flow_with_unassigned_printed_marks']
    group = annotation['cases'][0]['numbered_rows'][0]
    if change == 'omit':
        del group['unresolved_lines']
    elif change == 'wrong_line':
        group['unresolved_lines'][0] = 34
    elif change == 'duplicate':
        group['unresolved_lines'].append(35)
    else:
        del group['source_review']
    assert not check_annotations({'source': fixture['source'], 'pages': fixture['pages']},
                                 [{'source': fixture['source']}, *fixture['source_pages']], annotation)['passed']
