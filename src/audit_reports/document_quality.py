"""Source-text identity and legibility signals, never whole-document approval.

Checks keep the observed claims and source span references. A missing alias,
image cover or competing date is unresolved; filenames never supply a missing
claim. A clean signal is not evidence that every printed character was decoded.
"""
from __future__ import annotations

import calendar
from collections import Counter, defaultdict
import re
import unicodedata

from .document_corpus import Filing


def structure_diagnostics(structure: dict) -> dict:
    """Count named structural defects independently of blanket review labels.

    Counts describe candidates, which can overlap. They never imply that a
    detector found every table, that OCR is accurate, or that semantics passed.
    Page lists let a corpus run produce a repair queue without another PDF run.
    """
    issues, methods, kinds = defaultdict(list), Counter(), Counter()
    bad_cells, unplaced = [], []
    for page in structure['pages']:
        number = page['page']
        for kind in sorted({i['kind'] for i in page['issues']}):
            issues[kind].append(number)
        kinds.update(e['kind'] for e in page.get('narrative_elements', []))
        for table in page['tables']:
            methods[table['method']] += 1
            cells = [c for row in table['rows'] for c in row['cells']]
            mismatches = sum(c.get('source_text_matches') is False for c in cells)
            pending = sum(c.get('placement') == 'unplaced' for c in cells)
            ref = {'page': number, 'table_id': table['id']}
            if mismatches:
                bad_cells.append({**ref, 'cells': mismatches})
            if pending:
                unplaced.append({**ref, 'cells': pending})
    return {'schema_version': 'document-structure-diagnostics-1',
            'pages': len(structure['pages']), 'issue_pages': dict(sorted(issues.items())),
            'table_candidates_by_method': dict(sorted(methods.items())),
            'tables_with_cell_source_mismatches': bad_cells,
            'tables_with_unplaced_numeric_cells': unplaced,
            'narrative_elements_by_kind': dict(sorted(kinds.items())),
            'semantic_verification': 'not_performed'}

_MONTHS = {'mart': 3, 'march': 3, 'haziran': 6, 'june': 6,
           'eylul': 9, 'september': 9, 'aralik': 12, 'december': 12}
_MONTH = '|'.join(_MONTHS)
_DATES = [
    re.compile(r'(?<!\d)(?P<day>\d{1,2})\s*(?P<month>' + _MONTH + r')\s*,?\s*(?P<year>20\d{2})(?!\d)'),
    re.compile(r'\b(?P<month>' + _MONTH + r')\s*(?P<day>\d{1,2})\s*,?\s*(?P<year>20\d{2})(?!\d)'),
    re.compile(r'(?<!\d)(?P<day>\d{1,2})[./-](?P<month>0?[369]|12)[./-](?P<year>20\d{2})(?!\d)'),
    re.compile(r'(?<!\d)(?P<year>20\d{2})[./-](?P<month>0?[369]|12)[./-](?P<day>\d{1,2})(?!\d)'),
]
_SOLO = re.compile(r'\b(?:unconsolidated|non[\s-]*consolidated|konsolide\s+olmayan)\b')
_CONS = re.compile(r'\b(?:consolidated|konsolide)\b')
_VALUE = re.compile(r'^[%\s(\[+\-−–—]*\d[\d.,/\s%()\]+\-−–—]*$|^[\s\-−–—(*\d)]+$')


def fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.casefold().replace('ı', 'i'))
    return ''.join(c for c in text if not unicodedata.combining(c))


def bank_patterns(banks: dict) -> dict[str, list[re.Pattern]]:
    """Only registered names and explicit parenthetical aliases; no fuzzy bank guess."""
    result = {}
    for ticker, info in banks.items():
        name = fold(info['name'])
        aliases = [re.sub(r'\([^)]*\)', '', name).strip()]
        aliases.extend(re.sub(r'^formerly\s+', '', a).strip() for a in re.findall(r'\(([^()]*)\)', name))
        aliases.extend(fold(alias) for alias in info.get('source_names', []))
        patterns = []
        for alias in aliases:
            alias = re.sub(r'\s+(?:anonim\s+sirketi?|[at]\s*\.\s*[as]\s*\.\s*[os]?\s*\.?|a\s*\.\s*s\s*\.?)\s*$', '', alias)
            tokens = re.findall(r'[a-z0-9]+', alias)
            if tokens:
                patterns.append(re.compile(r'(?<![a-z0-9])' + r'[^a-z0-9]*'.join(map(re.escape, tokens)) + r'(?![a-z0-9])'))
        result[ticker] = patterns
    return result


def _page_text(page):
    text, offsets = '', []
    previous_line = None
    for span in page['spans']:
        part = fold(span['text'])
        line = (span['block'], span['line']) if 'block' in span and 'line' in span else None
        # Font changes can split a single printed word into several spans.
        # Add a separator between physical lines, never inside that source word.
        if text and (line is None or line != previous_line):
            text += ' '
        start = len(text)
        text += part
        offsets.append((start, len(text), span['id']))
        previous_line = line
    return text, offsets


def _reference(match, text, offsets):
    start, end = match.span()
    return {'observed_text': text[start:end],
            'source_span_ids': [sid for a, b, sid in offsets if a < end and b > start],
            'normalized_text_range': [start, end]}


def page_identity_claims(page: dict, patterns: dict) -> dict:
    text, offsets = _page_text(page)
    banks, dates, bases = [], [], []
    for ticker, aliases in patterns.items():
        seen = set()
        for alias in aliases:
            for match in alias.finditer(text):
                if match.span() not in seen:
                    banks.append({'bank_ticker': ticker, **_reference(match, text, offsets)})
                    seen.add(match.span())
    seen_dates = set()
    for pattern in _DATES:
        for match in pattern.finditer(text):
            if match.span() in seen_dates:
                continue
            seen_dates.add(match.span())
            year, day = int(match['year']), int(match['day'])
            month = _MONTHS.get(match['month']) or int(match['month'])
            # Only an actual quarter-end date supports a reporting-period claim.
            if day == calendar.monthrange(year, month)[1]:
                dates.append({'period': f'{year}Q{month // 3}', **_reference(match, text, offsets)})
    solo = list(_SOLO.finditer(text))
    for match in solo:
        bases.append({'kind': 'unconsolidated', **_reference(match, text, offsets)})
    for match in _CONS.finditer(text):
        if not any(a.start() <= match.start() and match.end() <= a.end() for a in solo):
            bases.append({'kind': 'consolidated', **_reference(match, text, offsets)})
    return {'page': page['page'], 'banks': banks, 'quarter_end_dates': dates, 'bases': bases}


def source_identity_review(filing: Filing, leading_pages: list[dict], patterns: dict) -> dict:
    observations = [page_identity_claims(page, patterns) for page in leading_pages]
    # A cover or opening opinion must supply all three claims on the same page.
    # Never assemble a match from unrelated fragments on different pages.
    complete = [p for p in observations if p['banks'] and p['quarter_end_dates'] and p['bases']]
    chosen = complete[0] if complete else None
    issues = []
    if chosen is None:
        status = 'unresolved'
        issues.append('no_complete_identity_claim_on_one_leading_page')
    else:
        banks = {b['bank_ticker'] for b in chosen['banks']}
        periods = {d['period'] for d in chosen['quarter_end_dates']}
        kinds = {b['kind'] for b in chosen['bases']}
        for label, expected, observed in [('bank', filing.bank_ticker, banks), ('period', filing.period, periods),
                                          ('basis', filing.kind, kinds)]:
            if expected not in observed:
                issues.append(f'{label}_conflicts_with_source_text')
            elif len(observed) != 1:
                issues.append(f'{label}_has_competing_source_claims')
        status = ('source_text_conflict' if any('conflicts' in i for i in issues) else
                  'ambiguous' if issues else 'supported_by_source_text')
    return {'filing': filing.as_dict(), 'status': status, 'claim_page': chosen['page'] if chosen else None,
            'observations': observations, 'issues': issues, 'scope': 'leading_source_text_only',
            'semantic_verification': 'not_performed'}


def text_legibility_signals(page: dict) -> dict:
    suspect, nonnumeric = [], []
    for word in page['words']:
        text = word['text'].strip()
        if not text or _VALUE.fullmatch(text):
            continue
        nonnumeric.append(word)
        alpha = sum(c.isalpha() for c in text)
        unusual = sum(not c.isalnum() and c not in " '-.,()/:%" for c in text)
        if len(text) >= 4 and alpha / len(text) < .4 and unusual >= 2:
            suspect.append(word['id'])
    broken_map = len(suspect) >= 8 and len(suspect) / max(len(nonnumeric), 1) >= .25
    replacement = page.get('replacement_character_count', 0)
    controls = [{'source_span_id': span['id'], 'character_offsets': [
        i for i, c in enumerate(span['text']) if unicodedata.category(c) == 'Cc' and c not in '\t\n\r']}
        for span in page.get('spans', [])]
    controls = [item for item in controls if item['character_offsets']]
    return {'page': page['page'], 'native_words': len(page['words']),
            'nonnumeric_words': len(nonnumeric), 'suspect_word_ids': suspect,
            'replacement_characters': replacement, 'control_character_spans': controls,
            'needs_text_review': bool(broken_map or replacement or controls),
            'signals': (['possible_font_character_mapping_problem'] if broken_map else [])
                       + (['replacement_characters'] if replacement else [])
                       + (['nontext_control_characters'] if controls else []),
            'readability_verified': False}
