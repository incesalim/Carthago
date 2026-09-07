"""Capture observed official PDF editions without changing the acquired filing.

An edition is bound to an immutable origin observation, not inferred to replace,
correct or translate another PDF. All source observations remain addressable.
"""
from __future__ import annotations

import hashlib
import json

from .document_acquisition import unwrap_pdf
from .document_corpus import Filing
from .document_corpus_store import CorpusStore, PREFIX


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _verified(store, ref, key):
    if (not isinstance(ref, dict) or not _hash(ref.get('sha256')) or ref.get('key') != key
            or type(ref.get('bytes')) is not int or ref['bytes'] < 1):
        raise ValueError('Invalid edition evidence reference')
    body, _ = store._read(key)
    if body is None or len(body) != ref['bytes'] or hashlib.sha256(body).hexdigest() != ref['sha256']:
        raise ValueError('Edition evidence differs from its immutable reference')
    return body


def edition_source(store: CorpusStore, filing: Filing, observation: str):
    """Read one retained difference, rechecking its receipt, transport and PDF."""
    if not _hash(observation):
        raise ValueError('An edition requires an exact retained observation digest')
    base = f'{PREFIX}origins/{filing.bank_ticker}/{filing.period}/{filing.kind}/'
    raw, _ = store._read(base + 'index.json')
    if raw is None:
        raise ValueError('No retained origin observations for this filing')
    index = json.loads(raw)
    if (index.get('schema_version') != 'document-origin-index-1' or index.get('filing') != filing.as_dict()
            or index.get('semantically_verified') is not False or not isinstance(index.get('revisions'), list)
            or index.get('current') not in index['revisions']):
        raise ValueError('Invalid edition origin index')
    refs = [r for r in index['revisions'] if r.get('sha256') == observation]
    if len(refs) != 1:
        raise ValueError('Edition observation is absent or ambiguous in retained history')
    ref = refs[0]
    receipt = json.loads(_verified(store, ref, base + observation + '.json'))
    if (receipt.get('schema_version') != 'document-origin-review-1' or receipt.get('filing') != filing.as_dict()
            or receipt.get('semantically_verified') is not False or receipt.get('status') != 'different_pdf_revision'
            or ref.get('status') != receipt['status'] or ref.get('checked_at') != receipt.get('checked_at')
            or not isinstance(receipt.get('source_url'), str) or not receipt['source_url'].startswith(('https://', 'http://'))
            or not isinstance(receipt.get('acquisition'), dict)
            or not _hash(receipt['acquisition'].get('sha256'))
            or receipt['acquisition']['sha256'] != ref.get('acquisition_sha256')
            or not isinstance(receipt.get('origin_pdf'), dict)
            or receipt['origin_pdf'].get('sha256') == receipt['acquisition']['sha256']):
        raise ValueError('Edition receipt does not establish an observed different PDF')
    pdf_ref, transport_ref = receipt['origin_pdf'], receipt.get('transport')
    if not isinstance(transport_ref, dict):
        raise ValueError('Edition has no retained download evidence')
    pdf = _verified(store, pdf_ref, f"{PREFIX}sources/{pdf_ref.get('sha256')}/original.pdf")
    transport = _verified(store, transport_ref, f"{PREFIX}transports/{transport_ref.get('sha256')}/original.bin")
    actual_pdf, selection = unwrap_pdf(transport, receipt.get('requested_archive_selection'))
    if actual_pdf != pdf or selection != receipt.get('selection'):
        raise ValueError('Edition PDF or archive selection differs from the retained response')
    if receipt.get('source_listing') is not None:
        from .document_origin_listing import listing_witness
        listing = receipt['source_listing']
        body = _verified(store, listing, f"{PREFIX}origin-listings/{listing.get('sha256')}.html")
        actual = listing_witness(body, listing['response'], filing)
        # Old observations retain their own parser fingerprint. Recheck the
        # literal row and source bytes with today's parser without relabelling it.
        if ({k: v for k, v in listing.items() if k not in ('key', 'engine')}
                != {k: v for k, v in actual.items() if k != 'engine'}
                or listing['download_url'] != receipt['source_url']):
            raise ValueError('Edition differs from its retained official listing row')
    return receipt, ref, pdf


class EditionCorpusStore(CorpusStore):
    """Index a PDF edition separately; share immutable content-addressed artifacts."""
    def __init__(self, store, filing, observation):
        super().__init__(store.client, store.bucket)
        self.filing, self.observation = filing, observation
        self.receipt, self.reference, self.pdf = edition_source(store, filing, observation)
        self.pdf_sha256 = self.receipt['origin_pdf']['sha256']

    def index_key(self, filing):
        if filing != self.filing:
            raise ValueError('Edition store cannot address another filing')
        return f'{PREFIX}editions/{filing.bank_ticker}/{filing.period}/{filing.kind}/{self.pdf_sha256}.json'

    def _update_index(self, filing, update):
        def bound(index):
            binding = {'schema_version': 'document-edition-binding-1', 'filing': filing.as_dict(),
                       'pdf_sha256': self.pdf_sha256, 'relationship': 'observed_different_official_pdf',
                       'semantic_verification': 'not_performed'}
            if index.get('edition', binding) != binding:
                raise ValueError('Edition index has a different source binding')
            index['edition'] = binding
            refs = index.setdefault('origin_observations', [])
            if self.reference not in refs:
                refs.append(self.reference)
            update(index)
            if index.get('current') and index['current']['source']['pdf_sha256'] != self.pdf_sha256:
                raise ValueError('Edition index points to another PDF')
        return super()._update_index(filing, bound)

    def publish(self, records, original, evidence):
        receipt, reference, pdf = edition_source(self, self.filing, self.observation)
        if (receipt != self.receipt or reference != self.reference or pdf != original.read_bytes()
                or records[0]['source'].get('source_url') != receipt['source_url']):
            raise ValueError('Edition capture differs from the retained origin observation')
        return super().publish(records, original, evidence)
