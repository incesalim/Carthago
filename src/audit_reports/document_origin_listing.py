"""Literal BDDK listing witnesses for additional official-source comparisons."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from .document_corpus import Filing

LISTING_URL = 'https://www.bddk.org.tr/BdrUyg/'
FORM = {'KurulusTuru': '1', 'EFTKodu': '0', 'RaporTipi': 'TÜMÜ', 'DonemYil': '0', 'DonemAy': '0'}
RESULT_URL = LISTING_URL + 'Home/SorguSonuc?' + urlencode(FORM)
NAMES_PATH = Path(__file__).resolve().parents[2] / 'data/banks/bddk_audit_registry_names.json'


def fetch_listing() -> tuple[bytes, dict]:
    import requests
    from src.scrapers._http import bddk_verify
    response = requests.post(LISTING_URL, data=FORM, timeout=120, verify=bddk_verify())
    response.raise_for_status()
    if response.url != RESULT_URL or len(response.content) > 20_000_000:
        raise ValueError('Unexpected official listing response')
    return response.content, {'source_url': LISTING_URL, 'resolved_url': response.url,
                              'method': 'POST', 'form': FORM, 'content_type': response.headers.get('Content-Type'),
                              'tls_verification': 'certifi_with_globalsign_intermediate'}


def _literal(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFC', value).split())


class _ReportRows(HTMLParser):
    """Read only explicit table cells in the regulator's report-results panel."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.found = False
        self.ordinal = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'div':
            if self.depth:
                self.depth += 1
            elif attributes.get('id') == 'divTab_raporlar':
                if self.found:
                    raise ValueError('Duplicate official results panel')
                self.depth, self.found = 1, True
        if not self.depth:
            return
        if tag == 'tr':
            if self.row is not None:
                raise ValueError('Nested or unclosed official listing row')
            self.row = []
        elif tag == 'td' and self.row is not None:
            if self.cell is not None:
                raise ValueError('Unclosed official listing cell')
            self.cell, self.links = [], []
        elif tag == 'a' and self.cell is not None and attributes.get('href') is not None:
            self.links.append(attributes['href'])

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == 'td' and self.cell is not None:
            self.row.append((_literal(' '.join(t.strip() for t in self.cell if t.strip())), tuple(self.links)))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.cell is not None:
                raise ValueError('Unclosed official listing cell')
            if self.row:
                self.rows.append((self.ordinal, tuple(c[0] for c in self.row), self.row[-1][1]))
            self.row = None
            self.ordinal += 1
        elif tag == 'div':
            self.depth -= 1


@lru_cache(maxsize=1)
def _listed_rows(body: bytes) -> tuple:
    if len(body) > 20_000_000:
        raise ValueError('Oversized official listing')
    parser = _ReportRows()
    parser.feed(body.decode('utf-8-sig'))
    parser.close()
    if not parser.found or parser.depth or parser.row is not None or parser.cell is not None:
        raise ValueError('Official report listing is absent')
    return tuple(parser.rows)


def listing_rows(body: bytes, names: dict[str, str], filings: set[Filing] | None = None) -> list[dict]:
    by_name = {_literal(name): ticker for ticker, name in names.items()}
    if len(by_name) != len(names):
        raise ValueError('Ambiguous regulator bank names')
    rows = []
    for ordinal, texts, links in _listed_rows(body):
        if texts[0] not in by_name:
            continue
        if len(texts) != 5 or not re.fullmatch(r'\d{4}', texts[1]) or texts[2] not in ('3', '6', '9', '12'):
            raise ValueError('Malformed registered-bank listing row')
        basis = {'SOLO': 'unconsolidated', 'KONSOLIDE': 'consolidated'}.get(texts[3])
        if basis is None or len(links) != 1:
            raise ValueError('Ambiguous report basis or download link')
        filing = Filing(by_name[texts[0]], f'{texts[1]}Q{int(texts[2]) // 3}', basis)
        if filings is not None and filing not in filings:
            continue
        url = urljoin(LISTING_URL, links[0])
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if (parts.scheme != 'https' or parts.netloc != 'www.bddk.org.tr'
                or parts.path != '/BdrUyg/Home/DosyaIndir' or parts.fragment
                or set(query) != {'raporUrl'} or len(query['raporUrl']) != 1):
            raise ValueError('Listing download is not a unique official report URL')
        target = re.fullmatch(r'~/Dosya/BDREki-(\d+)-(SOLO|KONSOLIDE)-(\d{4})-(\d{2})\.zip', query['raporUrl'][0])
        if not target or target.groups()[1:] != (texts[3], texts[1], f'{int(texts[2]):02d}'):
            raise ValueError(f'Listing date or basis differs from its download target: {filing.filename}')
        rows.append({'filing': filing.as_dict(), 'registry_name': texts[0], 'row_number': ordinal,
                     'row_cells': list(texts), 'download_url': url})
    if not rows:
        raise ValueError('No registered banks found in the official listing')
    return rows


def listing_witness(body: bytes, response: dict, filing: Filing) -> dict:
    if (response.get('source_url') != LISTING_URL or response.get('resolved_url') != RESULT_URL
            or response.get('method') != 'POST' or response.get('form') != FORM):
        raise ValueError('Official listing request cannot be matched')
    mapping = NAMES_PATH.read_bytes()
    names = json.loads(mapping)['banks']
    candidates = listing_rows(body, names, {filing})
    if len(candidates) != 1:
        raise ValueError(f'Official listing needs review: {len(candidates)} exact filing rows')
    return {'schema_version': 'document-origin-listing-1', 'sha256': hashlib.sha256(body).hexdigest(),
            'bytes': len(body), 'response': response, **candidates[0],
            'engine': {'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'bank_names_sha256': hashlib.sha256(mapping).hexdigest()},
            'semantically_verified': False}
