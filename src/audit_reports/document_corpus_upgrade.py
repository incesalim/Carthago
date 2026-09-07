"""Route exact retained-structure transitions before full PDF extraction.

This adapter is deliberately outside the extraction engine hash. Both ends of
each transition are exact byte identities, including the PyMuPDF version. A later
extraction change disables its shortcut until separately proven equivalent.
The retained base must come through CorpusStore's immutable-byte checks.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import fitz

from .document_cell_fragments import link_cell_fragments, word_character_geometry
from .document_corpus import Filing, source_identity
from .document_evidence import verify_evidence_records
from .document_structure import build_document_structure, structure_engine, verify_document_structure
from .document_table_context import table_context
from .document_table_notes import table_note_links
from .document_table_rows import table_source_rows


BASE_ENGINE = {
    'pymupdf': '1.27.2.3',
    'implementation_sha256': 'c6e429ce49dad46d4217c68d0ea35d8c5fe4acc6b508ea690f03c55bed83a463',
}
TARGET_ENGINE = {
    'pymupdf': '1.27.2.3',
    'implementation_sha256': '9d4a83ae8331be87f793b2fd9878463f35178a4f40f70766f2e6010a81a4b438',
}


def _cell_issues(tables):
    result = []
    for table in tables:
        if table.get('word_boundary_observations'):
            result.append({'kind': 'word_crosses_table_cells', 'table_id': table['id'],
                           'word_ids': [o['word_id'] for o in table['word_boundary_observations']]})
        for row in table['rows']:
            for cell in row['cells']:
                if not cell['source_text_matches']:
                    result.append({'kind': 'table_cell_source_mismatch', 'table_id': table['id'],
                                   'row': row['index'], 'column': cell.get('column', cell.get('col_index'))})
    return result


def upgrade_cell_fragments(pdf_path: Path, evidence: list[dict], base: dict) -> tuple[dict, dict] | None:
    """Retain the full structure and read original glyphs only where needed.

The supported diff changes neither table detection nor narrative/layout rules.
Those rules use unchanged table bounds, not the repaired cell word references.
Headers, source rows and note links are recomputed with the target engine.
Return None for an unsupported version; invalid eligible inputs must fail.
"""
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
    inspected, changed = [], []
    with fitz.open(pdf_path) as pdf:
        if len(pdf) != len(result['pages']):
            raise ValueError('Upgrade PDF page inventory differs from retained structure')
        for page, observed in zip(result['pages'], evidence[1:], strict=True):
            tables = page['tables']
            eligible = [t for t in tables if t['method'] == 'pymupdf_lines_strict'
                        and any(not c['source_text_matches'] for r in t['rows'] for c in r['cells'])]
            if not eligible:
                continue
            old_issues = _cell_issues(tables)
            # The old engine emits one contiguous block of cell diagnostics.
            # Do not silently repair an unexpected/corrupted diagnostic history.
            indexes = [i for i, issue in enumerate(page['issues'])
                       if issue['kind'] == 'table_cell_source_mismatch']
            if (not indexes or indexes != list(range(indexes[0], indexes[0] + len(old_issues)))
                    or [page['issues'][i] for i in indexes] != old_issues):
                raise ValueError('Retained cell diagnostics differ from the supported base')
            geometry = word_character_geometry(pdf[observed['page'] - 1], observed,
                                               {w['id'] for w in observed['words']})
            inspected.append(page['page'])
            for index, table in enumerate(tables):
                if table not in eligible:
                    continue
                linked = link_cell_fragments(table, observed, geometry)
                if linked != table:
                    tables[index] = linked
                    changed.append({'page': page['page'], 'table_id': table['id']})
            page['issues'][indexes[0]:indexes[-1] + 1] = _cell_issues(tables)
    for page, observed in zip(result['pages'], evidence[1:], strict=True):
        page['table_source_rows'] = table_source_rows(page, observed)
    for page, context in zip(result['pages'], table_context(result['pages']), strict=True):
        page['table_context'] = context
    for page, observed in zip(result['pages'], evidence[1:], strict=True):
        page['table_notes'] = table_note_links(page, observed)
    result['engine'] = target
    assert_source()
    check = verify_document_structure(result, evidence)
    if not check['valid']:
        raise ValueError(f'Upgraded structure failed source accounting: {check["errors"]}')
    return result, {'method': 'retained_cell_fragment_upgrade', 'base_engine': base['engine'],
                    'target_engine': target, 'glyph_pages_inspected': inspected,
                    'changed_tables': changed, 'semantic_verification': 'not_performed'}


def build_or_reuse_structure(pdf_path: Path, evidence: list[dict], store=None) -> tuple[dict, dict]:
    """Use byte-verified cache entries; read-only probes remain fresh by default."""
    target = structure_engine()
    if store is not None:
        cached = store.cached_structure(evidence, target)
        if cached is not None:
            return cached, {'method': 'exact_engine_cache'}
        from . import document_narrative_upgrade as narrative
        if target == narrative.TARGET_ENGINE:
            base = store.cached_structure(evidence, narrative.BASE_ENGINE)
            if base is not None:
                upgraded = narrative.upgrade_narrative(pdf_path, evidence, base)
                if upgraded is not None:
                    return upgraded
        from . import document_header_upgrade as headers
        if target == headers.TARGET_ENGINE:
            base = store.cached_structure(evidence, headers.BASE_ENGINE)
            if base is not None:
                upgraded = headers.upgrade_period_headers(pdf_path, evidence, base)
                if upgraded is not None:
                    return upgraded
        if target == TARGET_ENGINE:
            base = store.cached_structure(evidence, BASE_ENGINE)
            if base is not None:
                upgraded = upgrade_cell_fragments(pdf_path, evidence, base)
                if upgraded is not None:
                    return upgraded
        from . import document_region_upgrade as region
        if target == region.TARGET_ENGINE:
            for engine in region.SUPPORTED_BASE_ENGINES:
                base = store.cached_structure(evidence, engine)
                if base is not None:
                    upgraded = region.upgrade_table_regions(pdf_path, evidence, base)
                    if upgraded is not None:
                        return upgraded
    return build_document_structure(pdf_path, evidence), {'method': 'fresh_extraction'}


def compare_retained_structure(pdf_path, evidence, fresh, store):
    from . import document_narrative_upgrade as narrative
    if fresh['engine'] == narrative.TARGET_ENGINE:
        return narrative.compare_retained_narrative(pdf_path, evidence, fresh, store)
    from . import document_header_upgrade as headers
    if fresh['engine'] == headers.TARGET_ENGINE:
        return headers.compare_retained_headers(pdf_path, evidence, fresh, store)
    from .document_region_upgrade import compare_retained_regions
    return compare_retained_regions(pdf_path, evidence, fresh, store)
