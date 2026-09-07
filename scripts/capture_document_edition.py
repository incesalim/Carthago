#!/usr/bin/env python3
"""Capture one retained official PDF edition in Actions, without replacing a filing."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.document_corpus import Filing, source_identity  # noqa: E402
from src.audit_reports.document_corpus_store import CorpusStore  # noqa: E402
from src.audit_reports.document_editions import EditionCorpusStore  # noqa: E402
from src.audit_reports.document_evidence import capture_source_evidence, engine_identity, save_evidence  # noqa: E402
from src.audit_reports.document_structure import build_document_structure, structure_engine, structure_jsonl  # noqa: E402
from build_document_corpus import _write_bytes, _write_json  # noqa: E402
from capture_related_documents import recover_pages  # noqa: E402
from recover_document_corpus import select_pages  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--filing', required=True)
    parser.add_argument('--observation', required=True, help='Exact retained origin review SHA-256')
    parser.add_argument('--output-dir', type=Path, default=REPO / 'data/audit_capture/edition-v1')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('Full edition capture and recovery belong in Actions')
    try:
        filing = Filing(*args.filing.split('|'))
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    from src.audit_reports import r2_storage
    store = CorpusStore(r2_storage.get_client(), r2_storage._bucket())
    report = {'schema_version': 'document-edition-run-1', 'filing': filing.as_dict(),
              'observation_sha256': args.observation, 'published': args.publish, 'status': 'running',
              'semantically_verified': False,
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    _write_json(args.output_dir / 'edition-results.json', report)
    edition = None
    try:
        edition = EditionCorpusStore(store, filing, args.observation)
        report.update(origin_observation=edition.reference, origin_pdf=edition.receipt['origin_pdf'],
                      acquisition_observed=edition.receipt['acquisition'], index_key=edition.index_key(filing))
        folder = args.output_dir / 'sources' / edition.pdf_sha256
        original = folder / filing.filename
        _write_bytes(original, edition.pdf)
        source = source_identity(original, filing, source_url=edition.receipt['source_url'])
        records = edition.cached_evidence(source, engine_identity())
        report['native_reused'] = records is not None
        if records is None:
            records = capture_source_evidence(original, filing, source_url=edition.receipt['source_url'])
        evidence = folder / 'source.jsonl.gz'
        save_evidence(records, evidence)
        if args.publish:
            edition.publish(records, original, evidence)
        report.update(source=records[0]['source'], page_count=records[0]['page_count'],
                      text_characters=records[0]['text_characters'])
        structure = edition.cached_structure(records, structure_engine())
        report['structure_reused'] = structure is not None
        if structure is None:
            structure = build_document_structure(original, records)
        _write_bytes(folder / 'structure.jsonl', structure_jsonl(structure))
        if args.publish:
            edition.publish_structure(structure, records)
        report.update(table_candidates=sum(len(p['tables']) for p in structure['pages']),
                      text_blocks=sum(len(p['text_blocks']) for p in structure['pages']))
        selection = select_pages(original, [])
        report['selection'] = selection
        report['recovery_pages'] = recover_pages(store, original, filing, records[0]['page_count'], folder,
                                                 args.publish, selection=selection)
        if ([p['page'] for p in report['recovery_pages']] != selection['pages']
                or any(p['status'] == 'failed' for p in report['recovery_pages'])):
            raise ValueError('Edition preserved; selected recovery pages are incomplete or failed')
        report['status'] = 'structured_and_recovery_candidates'
    except Exception as error:
        report.update(status='failed', error=str(error))
        if args.publish and edition is not None:
            edition.record_failure(filing, str(error))
    _write_json(args.output_dir / 'edition-results.json', report)
    print(f"{filing.filename}: {report['status']}", flush=True)
    return int(report['status'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
