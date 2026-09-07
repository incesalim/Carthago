import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations
from src.audit_reports.document_navigation import (
    NAVIGATION_VERSION, document_navigation, verify_document_navigation,
)

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def observed():
    fixture = json.loads((FIXTURES / 'document_navigation_tomk.json').read_text(encoding='utf-8'))
    evidence = fixture['evidence']
    evidence[0]['source'] = {'pdf_sha256': fixture['source_sha256']}
    nav = document_navigation(evidence)
    structure = {'source': evidence[0]['source'], 'navigation_schema': NAVIGATION_VERSION, 'navigation': nav,
                 'sections': nav['sections'], 'contents_items': nav['contents_entries'],
                 'pages': [{'page': n} for n in range(1, 52)]}
    annotation = json.loads((FIXTURES / 'document_annotations/tomk_2023q3_solo.json').read_text(encoding='utf-8'))
    annotation.pop('filing', None)
    annotation['cases'] = [c for c in annotation['cases'] if c.get('kind') == 'document_navigation']
    return evidence, structure, annotation


def test_whole_contents_and_body_navigation_match_independent_original_transcription(observed):
    evidence, structure, annotation = observed
    assert len(annotation['cases']) == 1
    assert check_annotations(structure, evidence, annotation)['passed']
    nav = structure['navigation']
    assert len(nav['contents_entries']) == 57
    assert [(s['page_start'], s['page_end']) for s in nav['sections']] == [
        (6, 8), (9, 16), (17, 25), (26, 37), (38, 45), (46, 46), (47, 51)]
    assert len(nav['folio_observations']) == 45
    assert [m['kind'] for e in nav['contents_entries'][7:13] for m in e['body_title_matches']] == ['section_index_candidate'] * 6


@pytest.mark.parametrize('change', ['truncate', 'drop_entry', 'wrong_folio', 'source_word', 'source_geometry',
                                   'erase_conflict', 'wrong_section', 'drop_navigation', 'paragraph_context'])
def test_navigation_mutations_are_detected(observed, change):
    evidence, structure, annotation = observed
    nav = structure['navigation']
    if change == 'truncate':
        nav['contents_entries'][1]['title'] = nav['contents_entries'][1]['title'][:90]
    elif change == 'drop_entry':
        nav['contents_entries'].pop()
    elif change == 'wrong_folio':
        nav['contents_entries'][0]['page_start'] = 7
    elif change == 'source_word':
        nav['contents_entries'][1]['source_lines'][0]['word_ids'][0] = 0
    elif change == 'source_geometry':
        nav['body_banners'][0]['banner']['bbox'][1] += 20
    elif change == 'erase_conflict':
        nav['issues'] = []
    elif change == 'wrong_section':
        structure['sections'][0]['page_start'] = 7
    elif change == 'drop_navigation':
        del structure['navigation']
    else:
        structure['pages'][5]['narrative_elements'] = [{'section_candidate': None}]
    assert verify_document_navigation(structure, evidence)
    assert not check_annotations(structure, evidence, annotation)['passed']


@pytest.mark.parametrize('mutation', ['missing_folio', 'duplicate_folio', 'missing_banner', 'duplicate_banner', 'out_of_order'])
def test_missing_or_competing_source_locations_are_never_interpolated(observed, mutation):
    evidence, _, _ = observed
    early = evidence[6]
    footer = next(w for w in early['words'] if w['text'] == '1' and w['bbox'][1] > .88 * early['height'])
    if mutation == 'missing_folio':
        early['words'].remove(footer)
    elif mutation == 'duplicate_folio':
        next(w for w in evidence[7]['words'] if w['text'] == '2' and w['bbox'][1] > .88 * evidence[7]['height'])['text'] = '1'
    else:
        first = next(w for w in early['words'] if w['text'] == 'BİRİNCİ')
        if mutation == 'missing_banner':
            first['text'] = 'Unknown'
        elif mutation == 'out_of_order':
            first['text'] = 'İKİNCİ'
            next(w for w in evidence[9]['words'] if w['text'] == 'İKİNCİ')['text'] = 'BİRİNCİ'
        else:
            moved = copy.deepcopy([w for w in early['words'] if w['id'] in (28, 29)])
            for w in moved:
                w['id'] += 100000
            evidence[8]['words'].extend(moved)
    nav = document_navigation(evidence)
    if 'folio' in mutation:
        assert nav['contents_entries'][0]['page_start'] is None
        assert nav['contents_entries'][0]['mapping_status'] == ('ambiguous' if mutation == 'duplicate_folio' else 'unresolved')
    else:
        assert nav['sections'] == []
        assert nav['section_status'] == 'unresolved'


def test_legacy_structure_remains_readable_without_new_navigation_schema():
    assert verify_document_navigation({'pages': []}, []) == []


def crossbank_source(bank):
    fixture = json.loads((FIXTURES / f'document_navigation_{bank}.json').read_text(encoding='utf-8'))
    evidence = fixture['evidence']
    nav = document_navigation(evidence)
    structure = {'source': evidence[0]['source'], 'navigation_schema': NAVIGATION_VERSION, 'navigation': nav,
                 'sections': nav['sections'], 'contents_items': nav['contents_entries'],
                 'pages': [{'page': p['page']} for p in evidence[1:]]}
    period = '2022q4' if bank == 'garan' else '2026q1'
    annotation = json.loads((FIXTURES / f'document_annotations/{bank}_{period}_consolidated.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c.get('kind') == 'navigation_source_selection']
    return evidence, structure, annotation


@pytest.mark.parametrize('bank', ['garan', 'albrk'])
def test_crossbank_navigation_matches_independently_reviewed_original_locations(bank):
    evidence, structure, annotation = crossbank_source(bank)
    assert len(annotation['cases']) == 1
    result = check_annotations(structure, evidence, annotation)
    assert result['passed'], result
    assert result['scope'] == 'annotated_cases_only'
    assert structure['navigation']['semantic_verification'] == 'not_performed'
    if bank == 'garan':
        assert {s['method'] for s in structure['sections']} == {'contents_title_and_body_number'}
        # Page-No belongs to the right column on the same source baseline.
        assert structure['navigation']['contents_pages'][0]['sections'][0]['banner']['text'] == 'SECTION ONE Page No:'
        assert len(structure['navigation']['body_banners'][3]['title_sources']) == 2
    else:
        assert structure['sections'][-1]['title'] == 'Information on Interim Report'
        assert structure['navigation']['contents_pages'][-1]['sections'][-1]['title'] == 'Information on Interim activity report'


@pytest.mark.parametrize('bank', ['garan', 'albrk'])
@pytest.mark.parametrize('change', ['entry_title', 'section', 'count', 'folio', 'body_marker', 'erase_navigation'])
def test_selected_navigation_benchmark_rejects_changed_reviewed_locations(bank, change):
    evidence, structure, annotation = crossbank_source(bank)
    case = annotation['cases'][0]
    # Changing independent expectations must fail even when source recomputation succeeds.
    if change == 'entry_title':
        case['contents'][0]['title'] += ' altered'
    elif change == 'section':
        case['sections'][0]['page_start'] += 1
    elif change == 'count':
        case['contents_counts'][0][1] -= 1
    elif change == 'folio':
        case['folio_pairs'][0][1] += 1
    elif change == 'body_marker':
        case['body_markers'][-1]['text'] += ' altered'
    else:
        structure.pop('navigation')
    assert not check_annotations(structure, evidence, annotation)['passed']


@pytest.mark.parametrize('change', ['remove_number', 'vertical_displacement', 'horizontal_displacement',
                                   'dotted_subsection', 'wrong_number', 'truncate_wrap', 'contents_title',
                                   'duplicate_heading', 'extra_prose'])
def test_numbered_body_heading_requires_complete_unique_source_evidence(change):
    evidence, structure, _ = crossbank_source('garan')
    page = evidence[55]
    heading = structure['navigation']['body_banners'][3]
    marker = next(w for w in page['words'] if w['id'] == heading['banner']['word_ids'][0])
    if change == 'remove_number':
        page['words'].remove(marker)
    elif change == 'vertical_displacement':
        marker['bbox'][1] += 60
        marker['bbox'][3] += 60
    elif change == 'horizontal_displacement':
        marker['bbox'][0] -= 80
        marker['bbox'][2] -= 80
    elif change == 'dotted_subsection':
        marker['text'] = '4.1'
    elif change == 'wrong_number':
        marker['text'] = '5'
    elif change == 'truncate_wrap':
        ids = heading['title_sources'][1]['word_ids']
        page['words'] = [w for w in page['words'] if w['id'] not in ids]
    elif change == 'contents_title':
        title = structure['navigation']['contents_pages'][0]['sections'][3]['title_sources'][0]
        next(w for w in evidence[10]['words'] if w['id'] == title['word_ids'][-1])['text'] += ' changed'
    elif change == 'duplicate_heading':
        ids = heading['banner']['word_ids'] + [i for s in heading['title_sources'] for i in s['word_ids']]
        copied = copy.deepcopy([w for w in page['words'] if w['id'] in ids])
        for w in copied:
            w['id'] += 100000
        evidence[56]['words'].extend(copied)
    else:
        title = heading['title_sources'][0]
        x, y, right, bottom = title['bbox']
        page['words'].append({'id': 100000, 'text': 'prose', 'bbox': [right + 2, y, right + 25, bottom]})
    nav = document_navigation(evidence)
    assert nav['section_status'] == 'unresolved'
    assert nav['sections'] == []


@pytest.mark.parametrize('change', ['unknown_chapter', 'duplicate_chapter', 'prose_reference'])
def test_chapter_banner_is_not_inferred_from_a_missing_or_competing_source(change):
    evidence, structure, _ = crossbank_source('albrk')
    heading = structure['navigation']['body_banners'][-1]
    ids = heading['banner']['word_ids']
    words = [w for w in evidence[94]['words'] if w['id'] in ids]
    if change == 'unknown_chapter':
        next(w for w in words if w['text'] == 'CHAPTER')['text'] = 'Unknown'
    elif change == 'duplicate_chapter':
        copied = copy.deepcopy(words)
        for w in copied:
            w['id'] += 100000
        evidence[95]['words'].extend(copied)
    else:
        box = heading['banner']['bbox']
        evidence[94]['words'].append({'id': 100000, 'text': 'contains', 'bbox': [box[2] + 4, box[1], box[2] + 45, box[3]]})
    assert document_navigation(evidence)['sections'] == []
