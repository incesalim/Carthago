#!/usr/bin/env python3
"""Capture every other PDF in one filing's verified source archive, in Actions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.document_acquisition import unwrap_pdf  # noqa: E402
from src.audit_reports.document_corpus import Filing, source_identity  # noqa: E402
from src.audit_reports.document_corpus_store import CorpusStore  # noqa: E402
from src.audit_reports.document_evidence import capture_source_evidence, save_evidence  # noqa: E402
from src.audit_reports.document_related import RelatedCorpusStore, related_sources, related_identity_review  # noqa: E402
from src.audit_reports.document_quality import bank_patterns  # noqa: E402
from src.audit_reports.document_structure import build_document_structure, structure_jsonl  # noqa: E402
from build_document_corpus import _write_bytes, _write_json  # noqa: E402


def recover_pages(store, original, filing, page_count, output, publish):
    from src.audit_reports import document_ocr as ocr
    from src.audit_reports.document_recovery import RecoveryStore, make_packet, recovery_identity, verify_packet
    from src.audit_reports.document_recovery_tables import capture_recovery_tables
    from src.audit_reports.document_recovery_text import check_text_regions
    from src.audit_reports.document_font_mapping import font_mapping_page

    recovery = RecoveryStore(store)
    source = source_identity(original, filing)
    model_directory = output.parent.parent / 'models'
    lock = ocr.ensure_models(model_directory)
    engine = recovery_identity(ocr._engine(lock, 300, 'eng+tur'), None)
    if publish:
        recovery.record_selection(source, {'method': 'all_related_document_pages', 'page_count': page_count,
            'pages': list(range(1, page_count + 1)), 'selection_completeness_verified': True})
    outcomes = []
    for number in range(1, page_count + 1):
        try:
            cached = recovery.cached(source, number, engine, original, None)
            if cached:
                observed, derivative = cached[0]['ocr'], cached[1]
            else:
                observed, derivative = ocr.capture_ocr_page(original, filing, number, model_directory,
                                                           dpi=300, language='eng+tur')
            layout = capture_recovery_tables(observed, None, derivative)
            benchmarks = {'text_regions': check_text_regions(observed, REPO / 'tests/fixtures/document_recovery_text_annotations')}
            font = font_mapping_page(original, filing, number)
            if font['missing_unicode_trace_characters']:
                benchmarks['font_text_regions'] = check_text_regions(font, REPO / 'tests/fixtures/document_recovery_text_annotations',
                                                                     word_reference='font_word_ids')
            else:
                font = None
            packet = make_packet(observed, None, benchmarks, engine, table_layout=layout, font_mapping=font)
            verify_packet(packet, derivative, original, None)
            _write_json(output / f'p{number}.recovery.json', packet)
            _write_bytes(output / f'p{number}.ocr.pdf', derivative)
            if publish:
                recovery.publish(packet, derivative, original)
            outcomes.append({'page': number, 'status': 'recovery_candidates', 'ocr_words': len(observed['words']),
                             'reused_raw_ocr': bool(cached), 'benchmarks': benchmarks})
        except Exception as error:
            outcomes.append({'page': number, 'status': 'failed', 'error': str(error)})
            if publish:
                recovery.record_failure(source, number, str(error))
        _write_json(output / 'recovery-results.json', {'source': source, 'pages': outcomes, 'semantically_verified': False})
    return outcomes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--filing', required=True, help='BANK|YYYYQn|consolidated or unconsolidated')
    parser.add_argument('--output-dir', type=Path, default=REPO / 'data/audit_capture/related-v1')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('Related-document capture and recovery belong in Actions')
    try:
        filing = Filing(*args.filing.split('|'))
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    from src.audit_reports import r2_storage
    store = CorpusStore(r2_storage.get_client(), r2_storage._bucket())
    patterns = bank_patterns(json.loads((REPO / 'data/banks/audit_report_urls.json').read_text(encoding='utf-8'))['banks'])
    report = {'schema_version': 'related-document-run-1', 'filing': filing.as_dict(),
              'documents': [], 'status': 'running', 'published': args.publish, 'semantically_verified': False}
    _write_json(args.output_dir / 'related-results.json', report)
    try:
        receipt, sources = related_sources(store, filing)
        report['origin_observation'] = {'checked_at': receipt['checked_at'], 'transport': receipt['transport'],
                                        'primary_pdf': receipt['origin_pdf']}
        report['expected_related_documents'] = len(sources)
        for relation, raw in sources:
            outcome = {'relationship': relation, 'status': 'running'}
            report['documents'].append(outcome)
            related = RelatedCorpusStore(store, relation)
            try:
                body, wrapper = unwrap_pdf(raw)
                folder = args.output_dir / 'sources' / relation['member']['sha256']
                original = folder / filing.filename
                _write_bytes(original, body)
                records = capture_source_evidence(original, filing, source_url=receipt['source_url'])
                evidence = folder / 'source.jsonl.gz'
                save_evidence(records, evidence)
                if args.publish:
                    related.publish(records, original, evidence)
                identity = related.publish_identity_review(records, patterns) if args.publish else related_identity_review(records, patterns)
                _write_json(folder / 'identity-review.json', identity)
                outcome['identity_review'] = identity['identity_review']
                structure = build_document_structure(original, records)
                _write_bytes(folder / 'structure.jsonl', structure_jsonl(structure))
                if args.publish:
                    related.publish_structure(structure, records)
                outcome.update(source=records[0]['source'], page_count=records[0]['page_count'], wrapper=wrapper,
                               index_key=related.index_key(filing), native_status='structured_candidates')
                outcome['recovery_pages'] = recover_pages(store, original, filing, records[0]['page_count'], folder, args.publish)
                if any(p['status'] == 'failed' for p in outcome['recovery_pages']):
                    raise ValueError('Related source preserved; at least one recovery page failed')
                outcome['status'] = 'structured_and_recovery_candidates'
            except Exception as error:
                outcome.update(status='failed', error=str(error))
                if args.publish:
                    related.record_failure(filing, str(error))
            _write_json(args.output_dir / 'related-results.json', report)
        report['status'] = 'failed' if any(d['status'] == 'failed' for d in report['documents']) else 'captured_candidates'
    except Exception as error:
        report.update(status='failed', error=str(error))
    _write_json(args.output_dir / 'related-results.json', report)
    print(f"{filing.filename}: {report['status']}; {len(report['documents'])} related document outcomes", flush=True)
    return int(report['status'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
