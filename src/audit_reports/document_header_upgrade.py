"""Add source period-header views to an exact retained structure revision."""
from copy import deepcopy

from .document_corpus import Filing, source_identity
from .document_evidence import verify_evidence_records
from .document_structure import structure_digest, structure_engine, verify_document_structure
from .document_table_headers import add_period_headers

BASE_ENGINE = {'pymupdf': '1.27.2.3',
               'implementation_sha256': 'ca66890e81ae8c2d52a87a701193d3ea46f73ac5d7819e5f2e3d3d8ab5cd12e4'}
# Pin from the final LF-normalized extraction source before publication.
TARGET_ENGINE = {'pymupdf': '1.27.2.3', 'implementation_sha256': 'dda3201c09e2f487cd437283bdc53388217cc9982a3fc7db9a41a7a2fbcdf82a'}


def upgrade_period_headers(pdf_path, evidence, base):
    target = structure_engine()
    if target != TARGET_ENGINE or base.get('engine') != BASE_ENGINE:
        return None
    if not verify_evidence_records(evidence)['valid']:
        raise ValueError('Cannot add headers to invalid native evidence')
    if 'table_period_headers_schema' in base or any('table_period_headers' in p for p in base['pages']):
        raise ValueError('Retained base contains unexpected period-header views')
    if not verify_document_structure(base, evidence)['valid']:
        raise ValueError('Cannot add headers to invalid retained structure')
    source = evidence[0]['source']
    filing = Filing(source['bank_ticker'], source['period'], source['kind'])

    def check_original():
        observed = source_identity(pdf_path, filing)
        if (observed['pdf_sha256'], observed['byte_count']) != (source['pdf_sha256'], source['byte_count']):
            raise ValueError('Header source PDF differs from retained evidence')

    check_original()
    result = deepcopy(base)
    add_period_headers(result, evidence)
    result['engine'] = target
    check_original()
    if not verify_document_structure(result, evidence)['valid']:
        raise ValueError('Period-header view failed complete source verification')
    return result, {'method': 'retained_period_header_upgrade', 'base_engine': base['engine'],
                    'target_engine': target, 'pdf_pages_extracted': 0,
                    'header_tables': [{'page': p['page'], 'table_id': t['table_id']}
                                      for p in result['pages'] for t in p['table_period_headers']['tables']],
                    'semantic_verification': 'not_performed'}


def compare_retained_headers(pdf_path, evidence, fresh, store):
    if fresh['engine'] != TARGET_ENGINE or structure_engine() != TARGET_ENGINE:
        return {'status': 'unsupported_target'}
    base = store.cached_structure(evidence, BASE_ENGINE)
    if base is None:
        return {'status': 'no_supported_retained_base', 'base_engines': [BASE_ENGINE]}
    upgraded = upgrade_period_headers(pdf_path, evidence, base)
    if upgraded is None:
        raise ValueError('Supported period-header replay unexpectedly abstained')
    replay, receipt = upgraded
    if replay != fresh:
        raise ValueError('Retained period-header replay differs from complete fresh extraction')
    return {'status': 'matched', 'base_artifact_sha256': structure_digest(base),
            'fresh_artifact_sha256': structure_digest(fresh), 'replay': receipt}
