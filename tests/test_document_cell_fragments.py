"""Occurrence-level regressions for ruled cells that split one PDF word."""
from copy import deepcopy
import json
from pathlib import Path

import fitz
import pytest

from src.audit_reports.document_cell_fragments import (
    link_cell_fragments, verify_cell_fragments, word_character_geometry,
)
from src.audit_reports.document_evidence import page_evidence
from src.audit_reports.document_structure import _ruled_candidates


def sample(rotation=0):
    with fitz.open() as upright, fitz.open() as encoded:
        page = upright.new_page(width=400, height=300)
        for x in (50, 110, 240, 330):
            page.draw_line((x, 50), (x, 140))
        for y in (50, 80, 110, 140):
            page.draw_line((50, y), (330, y))
        for x, y, text in [(60, 70, 'No'), (120, 70, 'Item'), (250, 70, 'Value'),
                           (103.9, 100, '1Label'), (250, 100, '-'),
                           (103.9, 130, '2Other'), (250, 130, '0')]:
            page.insert_text((x, y), text, fontsize=10)
        size = (300, 400) if rotation in (90, 270) else (400, 300)
        shown = encoded.new_page(width=size[0], height=size[1])
        shown.show_pdf_page(shown.rect, upright, 0, rotate=rotation)
        shown.set_rotation(rotation)
        source = page_evidence(shown)
        original = encoded.tobytes(no_new_id=True)
        table = _ruled_candidates(shown, source)[0]
        geometry = word_character_geometry(shown, source, {w['id'] for w in source['words']})
        assert encoded.tobytes(no_new_id=True) == original
    return source, table, geometry


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_split_row_numbers_keep_exact_word_offsets_and_cell_geometry(rotation):
    source, table, geometry = sample(rotation)
    before = deepcopy(table)
    result = link_cell_fragments(table, source, geometry)
    assert table == before
    assert [[c['text'] for c in r['cells']] for r in result['rows']] == [
        ['No', 'Item', 'Value'], ['1', 'Label', '-'], ['2', 'Other', '0']]
    assert sum(not c['source_text_matches'] for r in table['rows'] for c in r['cells']) == 4
    assert all(c['source_text_matches'] for r in result['rows'] for c in r['cells'])
    for row in result['rows'][1:]:
        ordinal, label = [cell['source_fragments'][0] for cell in row['cells'][:2]]
        assert ordinal['word_id'] == label['word_id']
        assert (ordinal['start'], ordinal['end'], label['start'], label['end']) == (0, 1, 1, 6)
    assert all(o['review_status'] == 'unreviewed' for o in result['word_boundary_observations'])
    assert verify_cell_fragments(result, source) == []


@pytest.mark.parametrize('change', ['offset', 'unknown_word', 'text', 'duplicate', 'drop_cell', 'drop_geometry', 'drop_review'])
def test_corrupted_fragment_reference_cannot_pass(change):
    source, table, geometry = sample()
    result = link_cell_fragments(table, source, geometry)
    cell = result['rows'][1]['cells'][1]
    if change == 'offset':
        cell['source_fragments'][0]['start'] = 0
    elif change == 'unknown_word':
        cell['source_fragments'][0]['word_id'] = 9999
    elif change == 'text':
        cell['source_fragments'][0]['text'] = 'Wrong'
    elif change == 'duplicate':
        cell['source_fragments'].append(deepcopy(cell['source_fragments'][0]))
    elif change == 'drop_cell':
        del cell['source_fragments']
    elif change == 'drop_geometry':
        del result['word_fragment_geometry']
    else:
        del result['word_boundary_observations']
    assert verify_cell_fragments(result, source)


def test_reordered_or_changed_cell_text_does_not_gain_source_links():
    source, table, geometry = sample()
    for text in ('LabIe', 'Lbael', 'Label 0'):
        changed = deepcopy(table)
        changed['rows'][1]['cells'][1]['text'] = text
        assert link_cell_fragments(changed, source, geometry) == changed


def test_missing_character_and_ambiguous_border_abstain():
    source, table, geometry = sample()
    word = next(w for w in source['words'] if w['text'] == '1Label')
    for change in ('missing', 'ambiguous'):
        observed = deepcopy(next(g for g in geometry if g['word_id'] == word['id']))
        if change == 'missing':
            observed['characters'].pop(0)
        else:
            char = observed['characters'][0]
            char['bbox'][0], char['bbox'][2] = 109, 111
        assert link_cell_fragments(table, source, [observed]) == table


def test_actualtext_positions_are_not_inferred_from_literal_glyphs():
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 70), '1Label')
        source = page_evidence(page)
        source['actualtext_changes_word_view'] = True
        assert word_character_geometry(page, source, {0}) == []


def test_full_liquidity_source_grid_requires_fragment_references():
    from src.audit_reports.document_benchmark import check_annotations
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_liquidity_fragments_tomk.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/tomk_2024q1_solo.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['page'] == 35]
    assert len(annotation['cases']) == 1 and sum(map(len, annotation['cases'][0]['rows'])) == 186
    source, page = fixture['source_page'], fixture['page']
    structure, evidence = {'source': fixture['source'], 'pages': [page]}, [{'source': fixture['source']}, source]
    assert not check_annotations(structure, evidence, annotation)['passed']
    page['tables'] = [link_cell_fragments(page['tables'][0], source, fixture['character_geometry'])]
    assert check_annotations(structure, evidence, annotation)['passed']
    for mutation in ('blank_to_zero', 'same_value_wrong_source', 'drop_fragment', 'double_fragment', 'unit', 'period'):
        changed, records = deepcopy(structure), deepcopy(evidence)
        table = changed['pages'][0]['tables'][0]
        if mutation == 'blank_to_zero':
            table['rows'][13]['cells'][2]['text'] = '0'
        elif mutation == 'same_value_wrong_source':
            table['rows'][28]['cells'][4]['word_ids'] = table['rows'][3]['cells'][4]['word_ids']
        elif mutation == 'drop_fragment':
            table['rows'][3]['cells'][0]['source_fragments'] = []
        elif mutation == 'double_fragment':
            cell = table['rows'][3]['cells'][0]
            cell['source_fragments'].append(deepcopy(cell['source_fragments'][0]))
        else:
            field, replacement = ('Bin Türk Lirası', 'Milyon Türk Lirası') if mutation == 'unit' else ('31 MART 2024', '31 MART 2023')
            for span in records[1]['spans']:
                span['text'] = span['text'].replace(field, replacement)
        assert not check_annotations(changed, records, annotation)['passed'], mutation


def test_tall_cell_line_view_keeps_split_row_numbers_separate():
    from src.audit_reports.document_table_rows import table_source_rows, verify_table_source_rows
    with fitz.open() as pdf:
        page = pdf.new_page(width=400, height=400)
        for x in (50, 110, 240, 330):
            page.draw_line((x, 50), (x, 300))
        for y in (50, 80, 300):
            page.draw_line((50, y), (330, y))
        for x, text in [(60, 'No'), (120, 'Item'), (250, 'Value')]:
            page.insert_text((x, 70), text, fontsize=10)
        for i in range(1, 10):
            page.insert_text((103.9, 85 + i*20), f'{i}Label', fontsize=10)
            page.insert_text((250, 85 + i*20), str(100*i), fontsize=10)
        source = page_evidence(page)
        table = _ruled_candidates(page, source)[0]
        geometry = word_character_geometry(page, source, {w['id'] for w in source['words']})
        table = link_cell_fragments(table, source, geometry)
    structured = {'page': 1, 'tables': [table]}
    structured['table_source_rows'] = table_source_rows(structured, source)
    lines = structured['table_source_rows']['tables'][0]['split_rows'][0]['lines']
    assert [[c['text'] for c in line['cells']] for line in lines] == [[str(i), 'Label', str(100*i)] for i in range(1, 10)]
    assert all(c['source_fragments'] for line in lines for c in line['cells'])
    assert verify_table_source_rows(structured, source) == []
    lines[0]['cells'][1]['source_fragments'][0]['start'] = 0
    assert verify_table_source_rows(structured, source) == ['table_source_rows_mismatch']


def test_document_build_keeps_fragment_links_and_boundary_observations(tmp_path):
    from src.audit_reports.document_corpus import Filing
    from src.audit_reports.document_evidence import capture_source_evidence
    from src.audit_reports.document_structure import build_document_structure, verify_document_structure
    path = tmp_path / 'TEST_2026Q1_consolidated.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=400, height=300)
        for x in (50, 110, 240, 330):
            page.draw_line((x, 50), (x, 110))
        for y in (50, 80, 110):
            page.draw_line((50, y), (330, y))
        for x, y, text in [(60, 70, 'No'), (120, 70, 'Item'), (250, 70, 'Value'),
                           (103.9, 100, '1Label'), (250, 100, '0')]:
            page.insert_text((x, y), text, fontsize=10)
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2026Q1', 'consolidated'))
    structure = build_document_structure(path, evidence)
    table = next(t for t in structure['pages'][0]['tables'] if t['method'] == 'pymupdf_lines_strict')
    assert table['rows'][1]['cells'][0]['source_fragments'][0]['text'] == '1'
    assert any(i['kind'] == 'word_crosses_table_cells' for i in structure['pages'][0]['issues'])
    assert verify_document_structure(structure, evidence)['valid']
    saved_issues = structure['pages'][0]['issues']
    structure['pages'][0]['issues'] = [i for i in saved_issues if i['kind'] != 'word_crosses_table_cells']
    assert not verify_document_structure(structure, evidence)['valid']
    structure['pages'][0]['issues'] = saved_issues
    del table['word_boundary_observations']
    assert not verify_document_structure(structure, evidence)['valid']
