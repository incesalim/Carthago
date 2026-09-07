"""Rebuild narrative views from exact retained evidence without extracting PDFs."""
from copy import deepcopy

from .document_corpus import Filing, source_identity
from .document_evidence import verify_evidence_records
from .document_narrative import narrative_candidates
from .document_reading_layout import reading_layout
from .document_table_notes import table_note_links
from .document_table_context import table_context
from .document_structure import structure_digest, structure_engine, verify_document_structure

BASE_ENGINE = {'pymupdf': '1.27.2.3',
               'implementation_sha256': 'dda3201c09e2f487cd437283bdc53388217cc9982a3fc7db9a41a7a2fbcdf82a'}
TARGET_ENGINE = {'pymupdf': '1.27.2.3',
                 'implementation_sha256': '35500cc8dab5d08a2892fa6d8c947aa9356589147f60773f276340feea8692a4'}


def refresh_narrative_views(base, evidence):
    """Rebuild every dependent view; callers verify source identity and versions."""
    result = deepcopy(base)
    narrative_candidates(result['pages'], evidence, result['sections'])
    for page, source in zip(result['pages'], evidence[1:], strict=True):
        page['reading_layout'] = reading_layout(page, source)
    for page, context in zip(result['pages'], table_context(result['pages']), strict=True):
        page['table_context'] = context
    for page, source in zip(result['pages'], evidence[1:], strict=True):
        page['table_notes'] = table_note_links(page, source)
    return result


def upgrade_narrative(pdf_path, evidence, base):
    target = structure_engine()
    if target != TARGET_ENGINE or base.get('engine') != BASE_ENGINE:
        return None
    if not verify_evidence_records(evidence)['valid'] or not verify_document_structure(base, evidence)['valid']:
        raise ValueError('Cannot rebuild narrative from invalid retained evidence')
    source = evidence[0]['source']
    filing = Filing(source['bank_ticker'], source['period'], source['kind'])

    def check_original():
        observed = source_identity(pdf_path, filing)
        if (observed['pdf_sha256'], observed['byte_count']) != (source['pdf_sha256'], source['byte_count']):
            raise ValueError('Narrative source PDF differs from retained evidence')

    check_original()
    result = refresh_narrative_views(base, evidence)
    result['engine'] = target
    check_original()
    if not verify_document_structure(result, evidence)['valid']:
        raise ValueError('Rebuilt narrative failed complete source verification')
    changed = [p['page'] for p, old in zip(result['pages'], base['pages'], strict=True)
               if p['narrative_elements'] != old['narrative_elements']]
    return result, {'method': 'retained_narrative_upgrade', 'base_engine': base['engine'],
                    'target_engine': target, 'pdf_pages_extracted': 0, 'changed_pages': changed,
                    'semantic_verification': 'not_performed'}


def compare_retained_narrative(pdf_path, evidence, fresh, store):
    if fresh['engine'] != TARGET_ENGINE or structure_engine() != TARGET_ENGINE:
        return {'status': 'unsupported_target'}
    base = store.cached_structure(evidence, BASE_ENGINE)
    if base is None:
        return {'status': 'no_supported_retained_base', 'base_engines': [BASE_ENGINE]}
    upgraded = upgrade_narrative(pdf_path, evidence, base)
    if upgraded is None:
        raise ValueError('Supported narrative replay unexpectedly abstained')
    replay, receipt = upgraded
    if replay != fresh:
        raise ValueError('Retained narrative replay differs from complete fresh extraction')
    return {'status': 'matched', 'base_artifact_sha256': structure_digest(base),
            'fresh_artifact_sha256': structure_digest(fresh), 'replay': receipt}
