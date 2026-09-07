from copy import deepcopy
import json
from pathlib import Path

import fitz
import pytest

from src.audit_reports import document_structure as structure
from src.audit_reports.document_evidence import page_evidence
from src.audit_reports.document_table_regions import verify_region_refinement


def source_page(rotation=0):
    upright, pdf = fitz.open(), fitz.open()
    page = upright.new_page(width=400, height=300)
    # A different upper grid creates a chain of nearby x coordinates. The page
    # detector used to average those into the lower table's amount column.
    for x in (50, 110, 112, 114, 116, 118, 120, 122, 124, 240, 330):
        page.draw_line((x, 30), (x, 70))
    for y in (30, 50, 70):
        page.draw_line((50, y), (330, y))
    page.insert_text((60, 45), 'Other grid', fontsize=8)
    for x in (50, 110, 240, 330):
        page.draw_line((x, 140), (x, 200))
    for y in (140, 160, 180, 200):
        page.draw_line((50, y), (330, y))
    for x, y, text in [(60, 155, 'Item'), (125, 155, 'Current'), (250, 155, 'Prior'),
                       (60, 175, 'Loans'), (111, 175, '153.702.651'), (250, 175, '-'),
                       (60, 195, 'Total'), (111, 195, '153.702.651'), (250, 195, '0')]:
        page.insert_text((x, y), text, fontsize=10)
    size = (300, 400) if rotation in (90, 270) else (400, 300)
    shown = pdf.new_page(width=size[0], height=size[1])
    shown.show_pdf_page(shown.rect, upright, 0, rotate=rotation)
    shown.set_rotation(rotation)
    upright.close()
    return pdf


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_distant_grid_cannot_cut_first_digits_off_amounts(monkeypatch, rotation):
    with source_page(rotation) as pdf:
        page = pdf[0]
        source = page_evidence(page)
        before = pdf.tobytes(no_new_id=True)
        with monkeypatch.context() as old:
            old.setattr(structure, 'refine_ruled_regions', lambda page, source, tables, *args: tables)
            baseline = structure._ruled_candidates(page, source)[-1]
        current = structure._ruled_candidates(page, source)[-1]
        expected = [['Item', 'Current', 'Prior'], ['Loans', '153.702.651', '-'],
                    ['Total', '153.702.651', '0']]
        assert [[c['text'] for c in r['cells']] for r in baseline['rows']] != expected
        assert [[c['text'] for c in r['cells']] for r in current['rows']] == expected
        assert all(c['source_text_matches'] for r in current['rows'] for c in r['cells'])
        assert current['region_refinement']['initial_bbox'] == baseline['bbox']
        assert verify_region_refinement(current, source) == []
        assert pdf.tobytes(no_new_id=True) == before


@pytest.mark.parametrize('change', ['missing_word', 'changed_region', 'changed_clip', 'missing_digit', 'approval'])
def test_region_provenance_cannot_hide_changed_source_occurrences(change):
    with source_page() as pdf:
        source = page_evidence(pdf[0])
        table = structure._ruled_candidates(pdf[0], source)[-1]
    record = table['region_refinement']
    if change == 'missing_word':
        record['source_word_ids'].pop()
    elif change == 'changed_region':
        record['initial_bbox'][3] = 160
    elif change == 'changed_clip':
        record['clip'][0] += 1
    elif change == 'approval':
        record['semantic_verification'] = 'verified'
    else:
        table['rows'][1]['cells'][1]['text'] = '53.702.651'
    assert verify_region_refinement(table, source)


@pytest.mark.parametrize('failure', ['competing_tables', 'missing_text', 'duplicate_text', 'changed_word_region'])
def test_ambiguous_or_lossy_second_pass_keeps_original_candidate(monkeypatch, failure):
    from src.audit_reports.document_table_regions import refine_ruled_regions
    with source_page() as pdf:
        page = pdf[0]
        source = page_evidence(page)
        with monkeypatch.context() as old:
            old.setattr(structure, 'refine_ruled_regions', lambda page, source, tables, *args: tables)
            tables = structure._ruled_candidates(page, source)
        base = tables[-1]
        proposed = deepcopy(structure._ruled_candidates(page, source)[-1])
        proposed.pop('region_refinement')
        if failure == 'missing_text':
            proposed['rows'][1]['cells'][1]['text'] = '53.702.651'
        elif failure == 'duplicate_text':
            proposed['rows'][1]['cells'][1]['text'] += '153.702.651'
        elif failure == 'changed_word_region':
            proposed['bbox'][3] = 180

        class Found:
            tables = [object(), object()] if failure == 'competing_tables' else [object()]

        class Page:
            rect = page.rect

            def find_tables(self, **kwargs):
                return Found()

        result = refine_ruled_regions(Page(), source, [base], [], [], lambda table, id: proposed)
        assert result == [base]


def test_complete_exim_source_table_and_footnote_require_uncut_amounts():
    from src.audit_reports.document_benchmark import check_annotations
    folder = Path(__file__).parent / 'fixtures'
    fixture = json.loads((folder / 'document_region_refinement_exim.json').read_text(encoding='utf-8'))
    annotation = json.loads((folder / 'document_annotations/exim_2023q3_unconsolidated.json').read_text(encoding='utf-8'))
    evidence = [{'source': fixture['source']}, fixture['source_page']]
    observed = {'source': fixture['source'], 'pages': [fixture['original_page']]}
    assert not check_annotations(observed, evidence, annotation)['passed']
    observed['pages'][0]['tables'] = [fixture['refined_table']]
    assert check_annotations(observed, evidence, annotation)['passed']
    assert verify_region_refinement(fixture['refined_table'], fixture['source_page']) == []
    for change in ('digit', 'currency', 'row', 'footnote', 'unit'):
        changed, source = deepcopy(observed), deepcopy(evidence)
        table = changed['pages'][0]['tables'][0]
        if change == 'digit':
            table['rows'][2]['cells'][1]['text'] = '53.702.651'
        elif change == 'currency':
            cells = table['rows'][2]['cells']
            cells[1]['text'], cells[2]['text'] = cells[2]['text'], cells[1]['text']
        elif change == 'row':
            table['rows'].pop(2)
        elif change == 'footnote':
            source[1]['spans'] = [s for s in source[1]['spans'] if s['id'] != 224]
        else:
            source[1]['spans'][3]['text'] = 'Amounts expressed in millions of Turkish Lira.'
        assert not check_annotations(changed, source, annotation)['passed'], change
