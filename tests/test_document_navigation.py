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
