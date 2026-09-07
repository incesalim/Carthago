"""Fill explicit acquisition gaps without replacing an existing source object.

Keep the downloaded transport, chosen PDF and selection/identity observations.
An ambiguous archive or conflicting cover is retained for review, never silently
assigned to a filing. This does not publish analytical figures or approve text.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import fitz

from .document_corpus import Filing
from .document_corpus_store import PREFIX, _error_code, _json
from .document_quality import fold, source_identity_review


def is_zip_transport(body: bytes) -> bool:
    # Some complete BDDK ZIPs retain the four-byte spanning marker before their
    # local file header. ZipFile validates the central directory and CRCs; the
    # marker is recorded, never removed from retained transport bytes.
    return body.startswith((b'PK\x03\x04', b'PK\x07\x08PK\x03\x04'))


def unwrap_pdf(body: bytes, reviewed_member: dict | None = None, *, _archive_depth: int = 0) -> tuple[bytes, dict]:
    selection = {'method': 'direct_pdf', 'archive_members': []}
    if is_zip_transport(body):
        end = body.rfind(b'PK\x05\x06', max(0, len(body) - 65_557))
        if end < 0 or end + 22 > len(body) or end + 22 + int.from_bytes(body[end + 20:end + 22], 'little') != len(body):
            raise ValueError('Archive has an incomplete or ambiguous end record')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            expected_start = 4 if body.startswith(b'PK\x07\x08') else 0
            if not archive.infolist() or min(i.header_offset for i in archive.infolist()) != expected_start:
                # A truncated outer ZIP can otherwise be read as its inner ZIP,
                # silently discarding the actual downloaded container.
                raise ValueError('Archive local headers differ from the retained container')
            members = [i for i in archive.infolist() if not i.is_dir()]
            selection['archive_members'] = [{'name': i.filename, 'bytes': i.file_size,
                                             'sha256': hashlib.sha256(archive.read(i)).hexdigest()} for i in members]
            if body.startswith(b'PK\x07\x08'):
                selection.update(archive_prefix_format='zip_spanning_marker', archive_prefix_bytes=4)
            if len({i.filename for i in members}) != len(members):
                raise ValueError('Archive needs source selection: duplicate member names')
            if len(members) == 1 and members[0].filename.lower().endswith('.zip'):
                if _archive_depth or reviewed_member:
                    raise ValueError('Nested archive needs source selection: unsupported depth or member override')
                chosen = members[0]
                nested = archive.read(chosen)
                if not is_zip_transport(nested):
                    raise ValueError('Nested archive member does not contain a ZIP')
                pdf, inner = unwrap_pdf(nested, _archive_depth=1)
                # Only the independently observed one-wrapper/one-PDF shape is
                # automatic. Additional inner files require their own inventory
                # and attachment handling; never silently hide them here.
                if len(inner['archive_members']) != 1 or inner.get('unselected_pdf_members'):
                    raise ValueError('Nested archive needs source selection: additional inner members')
                selection.update(method='single_nested_zip', archive_member=chosen.filename,
                                 nested_selection=inner, unselected_pdf_members=[])
                return pdf, selection
            pdfs = [i for i in members if i.filename.lower().endswith('.pdf')]
            statements = [i for i in pdfs if not any(w in fold(i.filename) for w in ('faaliyet', 'activity'))]
            if reviewed_member:
                statements = [i for i in pdfs if i.filename == reviewed_member['member']]
            if len(statements) != 1:
                raise ValueError(f'Archive needs source selection: {len(statements)} non-activity PDFs')
            chosen = statements[0]
            selection.update(method='single_non_activity_pdf', archive_member=chosen.filename)
            body = archive.read(chosen)
            if reviewed_member:
                if hashlib.sha256(body).hexdigest() != reviewed_member['sha256']:
                    raise ValueError('Reviewed archive member bytes changed')
                selection.update(method='source_reviewed_archive_member', reviewed_member=reviewed_member)
            selection['unselected_pdf_members'] = [row for row in selection['archive_members']
                                                  if row['name'].lower().endswith('.pdf') and row['name'] != chosen.filename]
    elif reviewed_member:
        raise ValueError('Reviewed archive selection requires the source archive')
    # Some BDDK archives contain a serialized byte array as their PDF member.
    # Apply the wrapper check after archive selection as well as to direct URLs.
    if body.startswith(b'\xac\xed\x00\x05') and b'%PDF' in body[:64]:
        start = body.index(b'%PDF')
        selection.update(prefix_bytes=start, prefix_format='java_object_stream',
                         wrapped_pdf_sha256=hashlib.sha256(body).hexdigest())
        if selection['method'] == 'direct_pdf':
            selection['method'] = 'java_stream_prefix_removed'
        body = body[start:]
    if not body.startswith(b'%PDF-'):
        raise ValueError('Source did not contain a PDF')
    return body, selection


def fetch_source(url: str) -> tuple[bytes, dict]:
    import requests
    from urllib.parse import urlsplit
    from src.scrapers._http import bddk_verify

    hostname = (urlsplit(url).hostname or '').lower()
    # ICBC's server omits the same GlobalSign RSA OV SSL CA 2018 intermediate
    # as BDDK. Supply that existing chain with certifi roots; normal certificate
    # and hostname validation remain enabled. Limit this to the observed hosts.
    incomplete_chain = hostname in ('www.bddk.org.tr', 'bddk.org.tr', 'www.bddk.gov.tr', 'bddk.gov.tr',
                                    'www.icbc.com.tr', 'icbc.com.tr')
    verify = bddk_verify() if incomplete_chain else True
    response = requests.get(url, timeout=120, verify=verify, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        'Accept': 'application/pdf,application/zip,application/octet-stream,*/*'})
    response.raise_for_status()
    return response.content, {'source_url': url, 'resolved_url': response.url,
                              'content_type': response.headers.get('Content-Type'),
                              'tls_verification': 'certifi_with_globalsign_intermediate' if incomplete_chain else 'default_ca_bundle'}


def _existing(store, key):
    try:
        return store.client.head_object(Bucket=store.bucket, Key=key)
    except Exception as error:
        if _error_code(error) in ('404', 'NoSuchKey'):
            return None
        raise


def acquire_filing(store, filing: Filing, url: str, patterns: dict, *, fetch=fetch_source,
                   reviewed_member: dict | None = None) -> dict:
    """Only create a missing acquisition key; retain bytes before interpreting them."""
    key = f'{filing.bank_ticker.lower()}/{filing.filename}'
    result = {'filing': filing.as_dict(), 'acquisition_key': key, 'source_url': url,
              'semantic_verification': 'not_performed'}
    if _existing(store, key) is not None:
        return {**result, 'status': 'already_acquired', 'source_revision_review': 'not_performed'}
    transport, response = fetch(url)
    transport_sha = hashlib.sha256(transport).hexdigest()
    transport_key = f'{PREFIX}transports/{transport_sha}/original.bin'
    store._immutable(transport_key, transport, 'application/octet-stream')
    manifest = {**result, 'response': response, 'transport_sha256': transport_sha,
                'transport_key': transport_key, 'transport_bytes': len(transport),
                'assessment_engine': {'pymupdf': fitz.VersionBind, 'implementation': {
                    name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                    for name in ('document_acquisition.py', 'document_quality.py')}}}
    try:
        body, selection = unwrap_pdf(transport, reviewed_member)
        sha = hashlib.sha256(body).hexdigest()
        original_key = f'{PREFIX}sources/{sha}/original.pdf'
        store._immutable(original_key, body, 'application/pdf')
        manifest.update(selection=selection, pdf_sha256=sha, pdf_bytes=len(body), original_key=original_key,
                        related_pdf_content_capture='pending' if selection.get('unselected_pdf_members') else 'not_applicable')
        with fitz.open(stream=body, filetype='pdf') as pdf:
            if pdf.needs_pass or not len(pdf):
                raise ValueError('Source PDF requires a password or has no pages')
            leading = []
            for number in range(min(3, len(pdf))):
                raw = pdf[number].get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES,
                                           clip=fitz.INFINITE_RECT())
                spans = [s for block in raw['blocks'] if block['type'] == 0
                         for line in block['lines'] for s in line['spans']]
                leading.append({'page': number + 1, 'spans': [{'id': i, 'text': s['text']} for i, s in enumerate(spans)]})
            manifest.update(page_count=len(pdf), identity=source_identity_review(filing, leading, patterns))
        if manifest['identity']['status'] == 'source_text_conflict':
            raise ValueError('Source cover conflicts with the registered filing')
        manifest['status'] = 'source_candidate'
    except Exception as error:
        manifest.update(status='needs_review', error=str(error))
        payload = _json(manifest)
        manifest_key = f'{PREFIX}acquisitions/{filing.bank_ticker}/{filing.period}/{filing.kind}/{hashlib.sha256(payload).hexdigest()}.json'
        store._immutable(manifest_key, payload, 'application/json')
        return {**manifest, 'manifest_key': manifest_key}
    # Persist the interpretation receipt before exposing its acquired PDF. A
    # concurrent writer may win, but its different bytes must never be replaced.
    payload = _json(manifest)
    manifest_key = f'{PREFIX}acquisitions/{filing.bank_ticker}/{filing.period}/{filing.kind}/{hashlib.sha256(payload).hexdigest()}.json'
    store._immutable(manifest_key, payload, 'application/json')
    created = True
    try:
        store.client.put_object(Bucket=store.bucket, Key=key, Body=body,
                                ContentType='application/pdf', IfNoneMatch='*')
    except Exception as error:
        if _error_code(error) not in ('412', 'PreconditionFailed'):
            raise
        created = False
    response = store.client.get_object(Bucket=store.bucket, Key=key)
    stream = response['Body']
    try:
        acquired = stream.read()
    finally:
        stream.close()
    if acquired != body or response['ContentLength'] != len(body):
        raise ValueError('Acquisition key has different bytes; existing source left unchanged')
    return {**manifest, 'manifest_key': manifest_key,
            'status': 'acquired' if created else 'acquired_by_concurrent_writer', 'byte_readback_verified': True}
