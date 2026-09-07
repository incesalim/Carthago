#!/usr/bin/env python3
"""Fresh official-source comparison with retained transport and named differences.

Publishing writes only independent origin evidence under document-corpus/v1/.
Acquired PDFs, core filing indexes, analytical lanes and D1 are never changed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.document_corpus import Filing, registered_sources  # noqa: E402
from src.audit_reports.document_corpus_store import CorpusStore  # noqa: E402
from src.audit_reports.document_origin import observe_origin, publish_origin  # noqa: E402
from src.audit_reports.document_quality import bank_patterns  # noqa: E402
from build_document_corpus import _write_bytes, _write_json, filing_shard  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=REPO / 'data/banks/audit_report_urls.json')
    parser.add_argument('--output-dir', type=Path, default=REPO / 'data/audit_capture/origins-v1')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--source', choices=['registered', 'bddk'], default='registered')
    parser.add_argument('--bank')
    parser.add_argument('--period')
    parser.add_argument('--kind', choices=['consolidated', 'unconsolidated'])
    parser.add_argument('--filings', help='Exact comma-separated BANK|YYYYQn|basis selections; no broad filters')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--shard-count', type=int, default=1)
    parser.add_argument('--shard-index', type=int, default=0)
    args = parser.parse_args(argv)
    if args.limit < 0 or args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error('Invalid limit or filing group')
    if os.environ.get('GITHUB_ACTIONS') != 'true' and (args.publish or not 1 <= args.limit <= 4):
        parser.error('Origin publication and full reviews belong in Actions; local samples require --limit 1..4')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    banks = {b.strip().upper() for b in args.bank.split(',')} if args.bank else None
    if banks is not None and banks - set(config['banks']):
        parser.error('Unknown registered bank')
    if args.period:
        try:
            Filing(next(iter(config['banks'])), args.period, 'consolidated')
        except ValueError as error:
            parser.error(str(error))
    registered = registered_sources(config)
    selected = [f for f in sorted(registered) if (not banks or f.bank_ticker in banks)
                and (not args.period or f.period == args.period) and (not args.kind or f.kind == args.kind)]
    requested = None
    if args.filings is not None:
        if args.bank or args.period or args.kind:
            parser.error('Exact filings cannot be combined with broad bank/period/basis filters')
        try:
            requested = [Filing(*value.strip().split('|')) for value in args.filings.split(',')]
        except (TypeError, ValueError) as error:
            parser.error(f'Invalid exact filing selection: {error}')
        if len(requested) != len(set(requested)) or set(requested) - registered.keys():
            parser.error('Exact filing selection contains duplicates or unregistered filings')
        if args.limit and len(requested) > args.limit:
            parser.error('The limit cannot truncate an exact filing selection')
        selected = sorted(requested)
    elif args.limit:
        selected = selected[:args.limit]
    if not selected:
        parser.error('No registered filing matches the origin review scope')
    assigned = [f for f in selected if filing_shard(f.as_dict(), args.shard_count) == args.shard_index]
    from src.audit_reports import r2_storage
    store = CorpusStore(r2_storage.get_client(), r2_storage._bucket())
    acquired = defaultdict(list)
    for bank, period, kind, key in r2_storage.list_audit_pdfs():
        acquired[Filing(bank, period, kind)].append(key)
    patterns = bank_patterns(config['banks'])
    report = {'schema_version': 'document-origin-run-1', 'selected_filings': len(selected),
              'origin_source': args.source,
              'requested_filings': [f.as_dict() for f in sorted(requested)] if requested is not None else None,
              'assigned_filings': len(assigned), 'shard_count': args.shard_count, 'shard_index': args.shard_index,
              'filings': [], 'semantically_verified': False, 'published_evidence': args.publish}
    _write_json(args.output_dir / 'origin-results.json', report)
    listing, listing_error = None, None
    if args.source == 'bddk':
        from src.audit_reports.document_origin_listing import fetch_listing, listing_witness
        try:
            listing = fetch_listing()
        except Exception as error:
            listing_error = str(error)
    for filing in assigned:
        result = {'filing': filing.as_dict()}
        try:
            urls = registered[filing]
            if len(urls) != 1 or len(acquired[filing]) > 1:
                raise ValueError('Origin comparison requires an unambiguous URL and acquisition binding')
            key = acquired[filing][0] if acquired[filing] else f'{filing.bank_ticker.lower()}/{filing.filename}'
            member = config['banks'][filing.bank_ticker].get('archive_selection', {}).get(filing.kind, {}).get(filing.period)
            url = urls[0]
            if args.source == 'bddk':
                if listing_error:
                    raise ValueError(f'Official listing unavailable: {listing_error}')
                url = listing_witness(*listing, filing)['download_url']
                # A reviewed archive member is bound to its original URL; a
                # different official archive needs its own unambiguous selection.
                if url != urls[0]:
                    member = None
            result, artifacts = observe_origin(store, filing, key, url, patterns, reviewed_member=member,
                                                **({'listing': listing} if listing is not None else {}))
            if args.publish:
                result = publish_origin(store, result, artifacts, patterns)
            else:
                # Bounded read-only runs retain these originals as Actions
                # artifacts. Fleet proof publication retains them in private R2.
                folder = args.output_dir / 'sources' / filing.filename.removesuffix('.pdf')
                for name, body in artifacts.items():
                    suffix = 'pdf' if name == 'origin_pdf' else 'html' if name == 'source_listing' else 'bin'
                    _write_bytes(folder / f'{name}.{suffix}', body)
        except Exception as error:
            result = {**result, 'observation_status': result.get('status'), 'status': 'failed', 'error': str(error)}
        report['filings'].append(result)
        report['summary'] = dict(Counter(row['status'] for row in report['filings']))
        report['identity_summary'] = dict(Counter(row.get('origin_identity', {}).get('status', 'not_observed')
                                                  for row in report['filings']))
        _write_json(args.output_dir / 'origin-results.json', report)
        print(f"{filing.filename}: {result['status']}", flush=True)
    matches = {'matches_acquired_bytes', 'same_pdf_after_acquisition_wrapper'}
    return int(any(row['status'] not in matches
                   or row.get('origin_identity', {}).get('status') == 'source_text_conflict'
                   for row in report['filings']))


if __name__ == '__main__':
    raise SystemExit(main())
