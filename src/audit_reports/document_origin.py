"""Compare a fresh official download with acquired bytes; never replace either.

Matching bytes establish source revision agreement, not text/table accuracy.
Different revisions and unavailable URLs remain explicit review outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import fitz

from .document_acquisition import fetch_source, unwrap_pdf
from .document_corpus import Filing
from .document_corpus_resume import metadata
from .document_corpus_store import PREFIX, _error_code, _json
from .document_quality import source_identity_review


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _validate_bound_selection(entry):
    if not isinstance(entry, dict):
        raise ValueError('Invalid source-bound archive selection')
    filing = Filing(**entry['filing'])
    url = urlsplit(entry['source_url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('Archive selection requires its exact HTTPS source URL')
    if (entry.get('schema_version') != 'document-origin-selection-1'
            or entry.get('semantically_verified') is not False
            or not isinstance(entry.get('member'), str) or not entry['member'].lower().endswith('.pdf')):
        raise ValueError('Invalid source-bound archive selection')
    review = entry['review']
    digests = [entry['transport_sha256'], entry['sha256'], review['origin_observation_sha256']]
    if review['basis'] == 'acquired_pdf_byte_agreement':
        digests.append(review['acquisition_sha256'])
        if review['acquisition_sha256'] != entry['sha256']:
            raise ValueError('Selected archive member differs from the reviewed acquisition')
    elif review['basis'] == 'rendered_financial_report_cover':
        if (review.get('page') != 1 or not isinstance(review.get('text'), str)
                or not review['text'].strip()):
            raise ValueError('Reviewed report selection requires its literal cover text')
    else:
        raise ValueError('Unknown archive selection review basis')
    if any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value) for value in digests):
        raise ValueError('Invalid archive selection source digest')
    return filing, entry['source_url']


def load_archive_selections(path: Path, registered) -> dict:
    """A separate official URL needs its own reviewed, exact-byte selection."""
    packet = json.loads(path.read_text(encoding='utf-8'))
    if packet.get('schema_version') != 'document-origin-selections-1' or not isinstance(packet.get('selections'), list):
        raise ValueError('Invalid official archive selection registry')
    result = {}
    for entry in packet['selections']:
        binding = _validate_bound_selection(entry)
        if binding[0] not in registered or binding in result:
            raise ValueError('Unregistered or duplicate official archive selection')
        result[binding] = entry
    return result


def observe_origin(store, filing: Filing, acquisition_key: str | None, url: str, patterns: dict, *,
                   reviewed_member: dict | None = None, fetch=fetch_source, checked_at: str | None = None,
                   listing: tuple[bytes, dict] | None = None):
    result = {'schema_version': 'document-origin-review-1', 'filing': filing.as_dict(), 'source_url': url,
              'acquisition_key': acquisition_key, 'requested_archive_selection': reviewed_member,
              'checked_at': checked_at or datetime.now(timezone.utc).isoformat(),
              'acquisition': None, 'transport': None, 'origin_pdf': None,
              'semantically_verified': False,
              'engine': {'pymupdf': fitz.VersionBind, 'implementation': {
                  name: _sha(Path(__file__).with_name(name).read_bytes()) for name in
                  ('document_origin.py', 'document_acquisition.py', 'document_quality.py')}}}
    acquired = None
    if acquisition_key:
        try:
            response = store.client.get_object(Bucket=store.bucket, Key=acquisition_key)
        except Exception as error:
            if _error_code(error) not in ('404', 'NoSuchKey'):
                raise
        else:
            try:
                acquired = response['Body'].read()
            finally:
                response['Body'].close()
            if len(acquired) != response['ContentLength']:
                raise ValueError('Acquisition read was truncated during origin comparison')
            result['acquisition'] = {'key': acquisition_key, 'sha256': _sha(acquired), 'bytes': len(acquired),
                                     'version': metadata(acquisition_key, response)}
    artifacts = {}
    if listing is not None:
        from .document_origin_listing import listing_witness
        witness = listing_witness(*listing, filing)
        if witness['download_url'] != url:
            raise ValueError('Origin URL differs from its official listing row')
        result['source_listing'] = witness
        artifacts['source_listing'] = listing[0]
    try:
        transport, response = fetch(url)
    except Exception as error:
        result.update(status='origin_unavailable', error=str(error))
        return result, artifacts
    result.update(response=response, transport={'sha256': _sha(transport), 'bytes': len(transport)})
    artifacts['transport'] = transport
    try:
        bound_selection = reviewed_member and any(k in reviewed_member for k in ('source_url', 'transport_sha256'))
        if bound_selection:
            if _validate_bound_selection(reviewed_member) != (filing, url):
                raise ValueError('Reviewed archive selection belongs to a different filing or source URL')
            review = reviewed_member['review']
            if (review['basis'] == 'acquired_pdf_byte_agreement'
                    and (acquired is None or _sha(acquired) != review['acquisition_sha256'])):
                raise ValueError('Acquisition differs from the reviewed archive selection')
        body, selection = unwrap_pdf(transport, reviewed_member)
        result['selection'] = selection
        result['origin_pdf'] = {'sha256': _sha(body), 'bytes': len(body)}
        artifacts['origin_pdf'] = body
        leading = []
        with fitz.open(stream=body, filetype='pdf') as pdf:
            if pdf.needs_pass or not len(pdf):
                raise ValueError('Origin PDF requires a password or has no pages')
            for number in range(min(3, len(pdf))):
                raw = pdf[number].get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES,
                                           clip=fitz.INFINITE_RECT())
                spans = []
                for block_id, block in enumerate(raw['blocks']):
                    if block['type'] != 0:
                        continue
                    for line_id, line in enumerate(block['lines']):
                        for span in line['spans']:
                            spans.append({'id': len(spans), 'block': block_id, 'line': line_id,
                                          'text': span['text'], 'bbox': list(span['bbox'])})
                leading.append({'page': number + 1, 'spans': spans})
            result['page_count'] = len(pdf)
        result['origin_leading_pages'] = leading
        if bound_selection and reviewed_member['review']['basis'] == 'rendered_financial_report_cover':
            cover = ' '.join(s['text'] for s in leading[0]['spans'])
            if ' '.join(cover.split()) != ' '.join(reviewed_member['review']['text'].split()):
                raise ValueError('Selected PDF cover differs from its source review')
        result['origin_identity'] = source_identity_review(filing, leading, patterns)
        result['related_pdf_content_capture'] = 'pending' if selection.get('unselected_pdf_members') else 'not_applicable'
    except Exception as error:
        result.update(status='origin_needs_review', error=str(error))
        return result, artifacts
    if acquired is None:
        status = 'acquisition_missing'
    elif acquired == body:
        status = 'matches_acquired_bytes'
    else:
        status = 'different_pdf_revision'
        # Only an observed serialized wrapper may be normalized. Metadata,
        # punctuation, PDF objects and visible contents are never discarded.
        if acquired.startswith(b'\xac\xed\x00\x05'):
            try:
                normalized, wrapper = unwrap_pdf(acquired)
            except ValueError as error:
                result['acquisition_wrapper_error'] = str(error)
            else:
                result['acquisition_wrapper'] = wrapper
                if normalized == body:
                    status = 'same_pdf_after_acquisition_wrapper'
    result['status'] = status
    return result, artifacts


def publish_origin(store, result: dict, artifacts: dict[str, bytes], patterns: dict) -> dict:
    """Keep downloaded evidence and an immutable review before updating its index."""
    filing = Filing(**result['filing'])
    if result.get('schema_version') != 'document-origin-review-1' or result.get('semantically_verified') is not False:
        raise ValueError('Invalid source-origin review')
    observed_at = datetime.fromisoformat(result['checked_at'])
    if observed_at.tzinfo is None or observed_at.utcoffset().total_seconds() != 0:
        raise ValueError('Origin observation time must have an explicit UTC offset')
    acquired = result['acquisition']
    if acquired:
        current = metadata(acquired['key'], store.client.head_object(Bucket=store.bucket, Key=acquired['key']))
        if current != acquired['version']:
            raise ValueError('Acquisition changed during origin review')
    expected = {name for name in ('transport', 'origin_pdf', 'source_listing') if result.get(name) is not None}
    if set(artifacts) != expected:
        raise ValueError('Origin review is missing its downloaded evidence')
    def retained_download(_url):
        if 'transport' not in artifacts:
            raise RuntimeError(result['error'])
        return artifacts['transport'], result['response']
    checked, retained = observe_origin(store, filing, result['acquisition_key'], result['source_url'], patterns,
        reviewed_member=result['requested_archive_selection'], fetch=retained_download, checked_at=result['checked_at'],
        listing=(artifacts['source_listing'], result['source_listing']['response']) if 'source_listing' in artifacts else None)
    if checked != result or retained != artifacts:
        raise ValueError('Origin review differs from acquired bytes and retained transport')
    value = dict(result)
    for name, body in artifacts.items():
        record = result[name]
        if _sha(body) != record['sha256'] or len(body) != record['bytes']:
            raise ValueError('Origin artifact differs from its observed bytes')
        if name == 'source_listing':
            key = f"{PREFIX}origin-listings/{record['sha256']}.html"
        else:
            key = (f"{PREFIX}transports/{record['sha256']}/original.bin" if name == 'transport' else
                   f"{PREFIX}sources/{record['sha256']}/original.pdf")
        store._immutable(key, body, 'application/pdf' if name == 'origin_pdf' else 'application/octet-stream')
        value[name] = {**record, 'key': key}
    base = f'{PREFIX}origins/{filing.bank_ticker}/{filing.period}/{filing.kind}/'
    payload = _json(value)
    digest = _sha(payload)
    key = base + digest + '.json'
    store._immutable(key, payload, 'application/json')
    revision = {'key': key, 'sha256': digest, 'bytes': len(payload), 'checked_at': value['checked_at'],
                'status': value['status'], 'acquisition_sha256': acquired['sha256'] if acquired else None}
    for _ in range(8):
        previous, etag = store._read(base + 'index.json')
        index = json.loads(previous) if previous else {'schema_version': 'document-origin-index-1',
            'filing': filing.as_dict(), 'current': None, 'revisions': [], 'semantically_verified': False}
        if (index['filing'] != filing.as_dict() or index['schema_version'] != 'document-origin-index-1'
                or index.get('semantically_verified') is not False):
            raise ValueError('Origin index differs from its filing')
        if revision not in index['revisions']:
            index['revisions'].append(revision)
        index['current'] = max(index['revisions'], key=lambda r: (r['checked_at'], r['sha256']))
        body = _json(index)
        if body == previous:
            return {**value, 'review_key': key, 'index_key': base + 'index.json'}
        try:
            store.client.put_object(Bucket=store.bucket, Key=base + 'index.json', Body=body,
                                    ContentType='application/json', **({'IfMatch': etag} if etag else {'IfNoneMatch': '*'}))
            readback, _ = store._read(base + 'index.json')
            retained_index = json.loads(readback)
            if (retained_index.get('filing') != filing.as_dict()
                    or retained_index.get('schema_version') != 'document-origin-index-1'
                    or retained_index.get('semantically_verified') is not False
                    or revision not in retained_index.get('revisions', [])):
                raise ValueError('Origin index readback does not retain this observation')
            return {**value, 'review_key': key, 'index_key': base + 'index.json'}
        except Exception as error:
            if _error_code(error) not in ('412', 'PreconditionFailed'):
                raise
    raise RuntimeError('Origin index changed concurrently; retry this review')
