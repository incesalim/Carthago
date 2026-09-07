"""Preserve other PDFs in a registered report's archive as separate documents."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from .document_acquisition import unwrap_pdf, is_zip_transport
from .document_corpus import Filing
from .document_corpus_store import CorpusStore, PREFIX, _json
from .document_evidence import artifact_digest, verify_evidence_records


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def related_identity_review(records, patterns):
    """The archive's filing is context, not proof of its attachment's period."""
    from . import document_quality
    if not verify_evidence_records(records)['valid']:
        raise ValueError('Related identity requires valid native source evidence')
    source = records[0]['source']
    filing = Filing(**{k: source[k] for k in ('bank_ticker', 'period', 'kind')})
    rules = {bank: [{'pattern': p.pattern, 'flags': p.flags} for p in values]
             for bank, values in sorted(patterns.items())}
    return {'schema_version': 'related-identity-review-1', 'source': source,
            'evidence_artifact_sha256': artifact_digest(records),
            'container_filing': filing.as_dict(), 'source_filing_role': 'archive_container',
            'identity_review': document_quality.source_identity_review(filing, records[1:4], patterns),
            'engine': {'implementation_sha256': _sha(Path(document_quality.__file__).read_bytes()),
                       'bank_patterns': rules}, 'semantic_verification': 'not_performed'}


def _verified(store, entry, expected_key):
    if entry['key'] != expected_key:
        raise ValueError('Related source reference is outside its expected namespace')
    body, _ = store._read(expected_key)
    if body is None or len(body) != entry['bytes'] or _sha(body) != entry['sha256']:
        raise ValueError('Related source evidence bytes differ from their receipt')
    return body


def related_sources(store: CorpusStore, filing: Filing) -> tuple[dict, list[tuple[dict, bytes]]]:
    """Verify a retained origin/ZIP and enumerate every non-primary PDF member."""
    base = f'{PREFIX}origins/{filing.bank_ticker}/{filing.period}/{filing.kind}/'
    body, _ = store._read(base + 'index.json')
    if body is None:
        raise ValueError('No retained official-origin comparison for this filing')
    index = json.loads(body)
    if (index.get('schema_version') != 'document-origin-index-1' or index.get('filing') != filing.as_dict()
            or index.get('semantically_verified') is not False or index.get('current') not in index.get('revisions', [])):
        raise ValueError('Related source origin index has an invalid filing binding')
    current = index['current']
    receipt = json.loads(_verified(store, current, base + current['sha256'] + '.json'))
    if (receipt.get('schema_version') != 'document-origin-review-1' or receipt.get('filing') != filing.as_dict()
            or receipt.get('semantically_verified') is not False
            or receipt.get('status') != current['status'] or receipt.get('checked_at') != current['checked_at']):
        raise ValueError('Related source origin receipt differs from its index')
    if not receipt.get('transport'):
        raise ValueError('The official source response is unavailable')
    entry = receipt['transport']
    transport = _verified(store, entry, f"{PREFIX}transports/{entry['sha256']}/original.bin")
    if not is_zip_transport(transport):
        if receipt.get('selection', {}).get('unselected_pdf_members'):
            raise ValueError('Related PDF members claimed without an archive')
        return receipt, []
    selection = receipt.get('selection', {})
    if selection.get('method') == 'single_nested_zip':
        # The accepted nested shape has exactly one inner PDF and no hidden
        # attachments. Recheck that shape and every member before claiming none.
        pdf, actual = unwrap_pdf(transport, receipt.get('requested_archive_selection'))
        if (actual != selection or _sha(pdf) != receipt['origin_pdf']['sha256']
                or len(pdf) != receipt['origin_pdf']['bytes']):
            raise ValueError('Nested archive differs from its retained source selection')
        return receipt, []
    primary_name = selection.get('archive_member')
    with zipfile.ZipFile(io.BytesIO(transport)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len({m.filename for m in members}) != len(members):
            raise ValueError('Duplicate archive member names require source review')
        actual = [{'name': m.filename, 'bytes': m.file_size, 'sha256': _sha(archive.read(m))} for m in members]
        if actual != selection.get('archive_members'):
            raise ValueError('Retained archive member inventory differs from source bytes')
        if primary_name not in {m.filename for m in members} or not receipt.get('origin_pdf'):
            raise ValueError('Archive has no verified primary report selection')
        primary, _ = unwrap_pdf(archive.read(primary_name))
        if _sha(primary) != receipt['origin_pdf']['sha256'] or len(primary) != receipt['origin_pdf']['bytes']:
            raise ValueError('Archive primary member differs from its retained report')
        others = [m for m in actual if m['name'].lower().endswith('.pdf') and m['name'] != primary_name]
        if others != selection.get('unselected_pdf_members', []):
            raise ValueError('A related PDF member was omitted or invented')
        sources = []
        for member in others:
            relation = {'schema_version': 'related-source-binding-1', 'filing': filing.as_dict(),
                        'relationship': 'other_pdf_in_same_registered_source_archive',
                        'transport_sha256': entry['sha256'], 'transport_key': entry['key'],
                        'primary_pdf_sha256': receipt['origin_pdf']['sha256'], 'primary_member_name': primary_name,
                        'member': member,
                        'semantically_verified': False}
            sources.append((relation, archive.read(member['name'])))
    return receipt, sources


class RelatedCorpusStore(CorpusStore):
    """Reuse native preservation with a separate archive-member index namespace."""
    def __init__(self, store: CorpusStore, relation: dict):
        super().__init__(store.client, store.bucket)
        self.relation = relation
        self.filing = Filing(**relation['filing'])
        if (relation.get('schema_version') != 'related-source-binding-1' or relation.get('semantically_verified') is not False
                or relation.get('relationship') != 'other_pdf_in_same_registered_source_archive'
                or relation['member']['name'] == relation['primary_member_name']):
            raise ValueError('Invalid related document binding')
        for value in (relation['transport_sha256'], relation['primary_pdf_sha256'], relation['member']['sha256']):
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Invalid related source digest')

    def index_key(self, filing: Filing) -> str:
        if filing != self.filing:
            raise ValueError('Related document store cannot address another filing')
        return (f'{PREFIX}related/{filing.bank_ticker}/{filing.period}/{filing.kind}/'
                f"{self.relation['transport_sha256']}/{self.relation['member']['sha256']}.json")

    def _update_index(self, filing, update):
        def bound(index):
            if 'relationship' in index and index['relationship'] != self.relation:
                raise ValueError('Related document index has a different archive binding')
            index['relationship'] = self.relation
            update(index)
        return super()._update_index(filing, bound)

    def publish_identity_review(self, records, patterns):
        packet = related_identity_review(records, patterns)
        if packet['container_filing'] != self.filing.as_dict():
            raise ValueError('Related identity review has a different container filing')
        body = _json(packet)
        digest = _sha(body)
        key = f"{PREFIX}sources/{packet['source']['pdf_sha256']}/related-identity/{digest}.json"

        def bound(index):
            current = index.get('current')
            if (not current or current['source'] != packet['source']
                    or current['artifact_sha256'] != packet['evidence_artifact_sha256']):
                raise ValueError('Related identity review differs from retained native capture')
            return current

        index = json.loads(self._read(self.index_key(self.filing))[0])
        bound(index)
        self._immutable(key, body, 'application/json')
        reference = {'key': key, 'sha256': digest, 'bytes': len(body)}

        def update(index):
            current = bound(index)
            revision = next(r for r in index['revisions'] if r['artifact_sha256'] == current['artifact_sha256'])
            history = revision.setdefault('related_identity_reviews', [])
            if reference not in history:
                history.append(reference)
            revision['related_identity_review'] = reference
            index['current'] = revision

        self._update_index(self.filing, update)
        return packet

    def publish(self, records, original, evidence):
        # A caller-supplied relationship is not sufficient proof: locate the
        # exact member again in the retained transport before any publication.
        entry = {'key': self.relation['transport_key'], 'sha256': self.relation['transport_sha256']}
        body, _ = self._read(entry['key'])
        if entry['key'] != f"{PREFIX}transports/{entry['sha256']}/original.bin" or body is None or _sha(body) != entry['sha256']:
            raise ValueError('Related document transport binding changed')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            primary = [m for m in archive.infolist() if m.filename == self.relation['primary_member_name']]
            if len(primary) != 1 or _sha(unwrap_pdf(archive.read(primary[0]))[0]) != self.relation['primary_pdf_sha256']:
                raise ValueError('Related document primary report binding changed')
            matching = [m for m in archive.infolist() if m.filename == self.relation['member']['name']]
            if len(matching) != 1:
                raise ValueError('Related document member binding is ambiguous')
            raw = archive.read(matching[0])
            if _sha(raw) != self.relation['member']['sha256'] or len(raw) != self.relation['member']['bytes']:
                raise ValueError('Related document member bytes changed')
            canonical, _ = unwrap_pdf(raw)
            if canonical != original.read_bytes():
                raise ValueError('Related document original differs from its archive member')
        return super().publish(records, original, evidence)
