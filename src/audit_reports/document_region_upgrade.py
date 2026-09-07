"""Replay region isolation from one exact retained pre-isolation engine.

The source's first-pass grids, numeric candidates and native evidence already
exist. Reobserve local ruled regions, then rebuild every dependent projection.
This adapter is outside the extraction fingerprint and has a fixed target gate.
"""
from copy import deepcopy

import fitz

from .document_cell_fragments import link_cell_fragments, word_character_geometry
from .document_corpus import Filing, source_identity
from .document_corpus_upgrade import _cell_issues
from .document_evidence import text_characters, verify_evidence_records
from .document_narrative import narrative_candidates
from .document_reading_layout import reading_layout
from .document_rule_tables import underline_candidates
from .document_segmented_tables import segmented_table_candidates
from .document_structure import _refine_ruled_candidates, structure_digest, structure_engine, verify_document_structure
from .document_table_context import table_context
from .document_table_notes import table_note_links
from .document_table_rows import table_source_rows


BASE_ENGINE = {'pymupdf': '1.27.2.3',
               'implementation_sha256': '9d4a83ae8331be87f793b2fd9878463f35178a4f40f70766f2e6010a81a4b438'}
TARGET_ENGINE = {'pymupdf': '1.27.2.3',
                 'implementation_sha256': 'ca66890e81ae8c2d52a87a701193d3ea46f73ac5d7819e5f2e3d3d8ab5cd12e4'}


def _whole_word_table(table, source):
    """Reverse only the pinned fragment step; all literal cells stay intact."""
    original = deepcopy(table)
    if 'word_fragment_geometry' not in original:
        return original
    original.pop('word_fragment_geometry')
    original.pop('word_boundary_observations')
    for row in original['rows']:
        for cell in row['cells']:
            cell.pop('source_fragments', None)
            box = cell['bbox']
            refs = [w for w in source['words'] if box
                    and box[0] <= (w['bbox'][0] + w['bbox'][2]) / 2 <= box[2]
                    and box[1] <= (w['bbox'][1] + w['bbox'][3]) / 2 <= box[3]]
            cell['word_ids'] = [w['id'] for w in refs]
            cell['source_text_matches'] = text_characters(''.join(w['text'] for w in refs)) == text_characters(
                cell['text'] or '')
    return original


def _replace_table_issues(page, tables):
    expected = _cell_issues(page['tables'])
    indexes = [i for i, issue in enumerate(page['issues'])
               if issue['kind'] in ('table_cell_source_mismatch', 'word_crosses_table_cells')]
    if [page['issues'][i] for i in indexes] != expected:
        raise ValueError('Retained table diagnostics differ from the supported base')
    if indexes:
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise ValueError('Retained table diagnostics are not contiguous')
        start, end = indexes[0], indexes[-1] + 1
    else:
        suffix = {'legacy_text_not_conserved', 'image_content_unreviewed', 'drawing_content_unreviewed',
                  'unreadable_content', 'replacement_characters', 'actualtext_geometry_unverified',
                  'native_text_span_unresolved'}
        start = end = next((i for i, issue in enumerate(page['issues']) if issue['kind'] in suffix),
                           len(page['issues']))
    page['issues'][start:end] = _cell_issues(tables)


def upgrade_table_regions(pdf_path, evidence, base):
    target = structure_engine()
    if target != TARGET_ENGINE or base.get('engine') != BASE_ENGINE:
        return None
    if not verify_evidence_records(evidence)['valid']:
        raise ValueError('Cannot upgrade invalid source evidence')
    check = verify_document_structure(base, evidence)
    if not check['valid']:
        raise ValueError(f'Cannot upgrade invalid retained structure: {check["errors"]}')
    source = evidence[0]['source']
    filing = Filing(source['bank_ticker'], source['period'], source['kind'])

    def assert_source():
        observed = source_identity(pdf_path, filing)
        if (observed['pdf_sha256'], observed['byte_count']) != (source['pdf_sha256'], source['byte_count']):
            raise ValueError('Upgrade PDF differs from source evidence')

    assert_source()
    result = deepcopy(base)
    inspected, refined, glyph_pages = [], [], []
    with fitz.open(pdf_path) as pdf:
        if len(pdf) != len(result['pages']):
            raise ValueError('Upgrade PDF page inventory differs from retained structure')
        for page, observed in zip(result['pages'], evidence[1:], strict=True):
            old_ruled = [t for t in page['tables'] if t['method'] == 'pymupdf_lines_strict']
            if not old_ruled:
                continue
            inspected.append(page['page'])
            raw = [_whole_word_table(t, observed) for t in old_ruled]
            ruled = _refine_ruled_candidates(pdf[observed['page'] - 1], observed, raw)
            refined.extend({'page': page['page'], 'table_id': t['id']} for t in ruled if t.get('region_refinement'))
            if any(not c['source_text_matches'] for t in ruled for r in t['rows'] for c in r['cells']):
                glyph_pages.append(page['page'])
                geometry = word_character_geometry(pdf[observed['page'] - 1], observed,
                                                   {w['id'] for w in observed['words']})
                ruled = [link_cell_fragments(t, observed, geometry) if any(
                    not c['source_text_matches'] for r in t['rows'] for c in r['cells']) else t for t in ruled]
            numeric = [t for t in page['tables'] if t['method'] == 'legacy_numeric_geometry']
            tables = numeric + ruled
            tables.extend(underline_candidates(observed, tables))
            tables.extend(segmented_table_candidates(observed, tables))
            tables.extend(t for t in page['tables'] if t['method'] == 'native_image_replacement_geometry')
            _replace_table_issues(page, tables)
            page['tables'] = tables
    narrative_candidates(result['pages'], evidence, result['sections'])
    for page, observed in zip(result['pages'], evidence[1:], strict=True):
        page['table_source_rows'] = table_source_rows(page, observed)
        page['reading_layout'] = reading_layout(page, observed)
    for page, context in zip(result['pages'], table_context(result['pages']), strict=True):
        page['table_context'] = context
    for page, observed in zip(result['pages'], evidence[1:], strict=True):
        page['table_notes'] = table_note_links(page, observed)
    result['engine'] = target
    assert_source()
    check = verify_document_structure(result, evidence)
    if not check['valid']:
        raise ValueError(f'Upgraded structure failed source accounting: {check["errors"]}')
    return result, {'method': 'retained_table_region_upgrade', 'base_engine': base['engine'],
                    'target_engine': target, 'ruled_pages_inspected': inspected,
                    'glyph_pages_inspected': glyph_pages, 'refined_tables': refined,
                    'semantic_verification': 'not_performed'}


def compare_retained_regions(pdf_path, evidence, fresh, store):
    """Read-only probes compare the whole replay result, never just its checks."""
    if fresh['engine'] != TARGET_ENGINE or structure_engine() != TARGET_ENGINE:
        return {'status': 'unsupported_target'}
    base = store.cached_structure(evidence, BASE_ENGINE)
    if base is None:
        return {'status': 'no_supported_retained_base', 'base_engine': BASE_ENGINE}
    result = upgrade_table_regions(pdf_path, evidence, base)
    if result is None:
        raise ValueError('Supported retained region replay unexpectedly abstained')
    replay, receipt = result
    if replay != fresh:
        raise ValueError('Retained region replay differs from complete fresh extraction')
    return {'status': 'matched', 'base_artifact_sha256': structure_digest(base),
            'fresh_artifact_sha256': structure_digest(fresh), 'replay': receipt}
