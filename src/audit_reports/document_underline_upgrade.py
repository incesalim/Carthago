"""Rebuild horizontal-rule candidates from exact retained native evidence."""
from copy import deepcopy

from .document_corpus import Filing, source_identity
from .document_evidence import verify_evidence_records
from .document_narrative_upgrade import refresh_narrative_views
from .document_region_upgrade import _replace_table_issues
from .document_rule_tables import underline_candidates
from .document_segmented_tables import segmented_table_candidates
from .document_structure import structure_digest, structure_engine, verify_document_structure
from .document_table_headers import add_period_headers
from .document_table_rows import table_source_rows

BASE_ENGINE = {'pymupdf': '1.27.2.3',
               'implementation_sha256': '35500cc8dab5d08a2892fa6d8c947aa9356589147f60773f276340feea8692a4'}
TARGET_ENGINE = {'pymupdf': '1.27.2.3',
                 'implementation_sha256': 'c9134d44f552379513ddcc3e5e11fb67fbb69df8489584d5ac5c5c38b1fa1a38'}


def refresh_underline_views(base, evidence):
    """Rebuild all table-dependent projections in the same order as extraction."""
    result = deepcopy(base)
    methods = {'legacy_numeric_geometry', 'pymupdf_lines_strict', 'horizontal_rule_cells',
               'segmented_rules_and_source_lines', 'native_image_replacement_geometry'}
    for page, source in zip(result['pages'], evidence[1:], strict=True):
        if any(t['method'] not in methods for t in page['tables']):
            raise ValueError('Unsupported retained table method')
        tables = [t for t in page['tables'] if t['method'] in ('legacy_numeric_geometry', 'pymupdf_lines_strict')]
        tables.extend(underline_candidates(source, tables))
        tables.extend(segmented_table_candidates(source, tables))
        tables.extend(t for t in page['tables'] if t['method'] == 'native_image_replacement_geometry')
        _replace_table_issues(page, tables)
        page['tables'] = tables
        page['table_source_rows'] = table_source_rows(page, source)
    result = refresh_narrative_views(result, evidence)
    add_period_headers(result, evidence)
    return result


def upgrade_underlines(pdf_path, evidence, base):
    target = structure_engine()
    if target != TARGET_ENGINE or base.get('engine') != BASE_ENGINE:
        return None
    if not verify_evidence_records(evidence)['valid'] or not verify_document_structure(base, evidence)['valid']:
        raise ValueError('Cannot rebuild tables from invalid retained evidence')
    source = evidence[0]['source']
    filing = Filing(source['bank_ticker'], source['period'], source['kind'])

    def check_original():
        observed = source_identity(pdf_path, filing)
        if (observed['pdf_sha256'], observed['byte_count']) != (source['pdf_sha256'], source['byte_count']):
            raise ValueError('Table source PDF differs from retained evidence')

    check_original()
    result = refresh_underline_views(base, evidence)
    result['engine'] = target
    check_original()
    if not verify_document_structure(result, evidence)['valid']:
        raise ValueError('Rebuilt tables failed complete source verification')
    changed = [p['page'] for p, old in zip(result['pages'], base['pages'], strict=True) if p['tables'] != old['tables']]
    return result, {'method': 'retained_underline_upgrade', 'base_engine': base['engine'],
                    'target_engine': target, 'pdf_pages_extracted': 0, 'changed_pages': changed,
                    'semantic_verification': 'not_performed'}


def compare_retained_underlines(pdf_path, evidence, fresh, store):
    if fresh['engine'] != TARGET_ENGINE or structure_engine() != TARGET_ENGINE:
        return {'status': 'unsupported_target'}
    base = store.cached_structure(evidence, BASE_ENGINE)
    if base is None:
        return {'status': 'no_supported_retained_base', 'base_engines': [BASE_ENGINE]}
    upgraded = upgrade_underlines(pdf_path, evidence, base)
    if upgraded is None:
        raise ValueError('Supported underline replay unexpectedly abstained')
    replay, receipt = upgraded
    if replay != fresh:
        raise ValueError('Retained underline replay differs from complete fresh extraction')
    return {'status': 'matched', 'base_artifact_sha256': structure_digest(base),
            'fresh_artifact_sha256': structure_digest(fresh), 'replay': receipt}
