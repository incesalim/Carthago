"""Navigation candidates bound to native word occurrences, without folio offsets.

Contents claims and body locations are separate observations. A unique printed
footer can locate a declared folio; it cannot prove that the named content starts
there. Missing or repeated folios are never interpolated. Original text survives
in the source ledger regardless of whether these conservative cues recognize it.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .document_sections import ROMAN, SEC_EN, SEC_TR, fold, sec_no
from .prose import role_from_title

NAVIGATION_VERSION = "document-navigation-1"
_FOLIO = re.compile(r"\(?([0-9]{1,4})\)?")
_RANGE = re.compile(r"([0-9]{1,4})(?:[-–—]([0-9]{1,4}))?")
_ITEM = re.compile(r"(" + "|".join(sorted(ROMAN, key=len, reverse=True)) + r")\.?$")


def _bounds(words):
    return [min(w['bbox'][0] for w in words), min(w['bbox'][1] for w in words),
            max(w['bbox'][2] for w in words), max(w['bbox'][3] for w in words)]


def _witness(source, words):
    return {'page': source['page'], 'word_ids': [w['id'] for w in words],
            'text': ' '.join(w['text'] for w in words), 'bbox': _bounds(words)}


def _lines(source):
    """Whole-word baselines; overlapping or displaced words do not get guessed."""
    groups = []
    for word in sorted(source['words'], key=lambda w: (w['bbox'][1], w['bbox'][0], w['id'])):
        if not groups or word['bbox'][1] - groups[-1][0]['bbox'][1] > 1:
            groups.append([])
        groups[-1].append(word)
    result = []
    for words in groups:
        words.sort(key=lambda w: (w['bbox'][0], w['id']))
        if any(a['bbox'][2] > b['bbox'][0] + .75 for a, b in zip(words, words[1:])):
            # Keep the obstacle: a wrapped entry must not jump over an unread line.
            result.append({'words': words, 'valid': False, **_witness(source, words)})
            continue
        result.append({'words': words, 'valid': True, **_witness(source, words)})
    return result


def _banner(line):
    if not line['valid']:
        return None
    text = line['text']
    match = SEC_EN.match(fold(text)) or SEC_TR.match(fold(text))
    if match is None:
        return None
    suffix = text[match.end():]
    # A prose reference beginning "SECTION ONE contains ..." is not a banner.
    if suffix.strip() and not suffix.lstrip().startswith((':', '—', '–', '-')):
        return None
    return sec_no(match.group(1)), suffix.strip(' :—–-')


def _public(line):
    return {k: line[k] for k in ('page', 'word_ids', 'text', 'bbox')}


def _title(lines, index, inline):
    if inline:
        return inline, [_public(lines[index])]
    selected = []
    banner = lines[index]
    for line in lines[index + 1:]:
        previous = selected[-1] if selected else banner
        height = previous['bbox'][3] - previous['bbox'][1]
        if (not line['valid'] or _banner(line) or _ITEM.fullmatch(line['words'][0]['text'])
                or not any(c.isalpha() for c in line['text'])
                or line['bbox'][1] - previous['bbox'][3] > 3 * height):
            break
        # Titles may wrap, but a following paragraph must not be absorbed.
        if selected and (abs(sum(line['bbox'][::2]) - sum(previous['bbox'][::2])) > 24
                         or line['bbox'][1] - previous['bbox'][3] > height):
            break
        selected.append(line)
        if not line['text'].isupper():
            break
    return ' '.join(line['text'] for line in selected), [_public(line) for line in selected]


def _contents(source, lines, issues):
    entries, sections = [], []
    current, pending = None, []

    def finish():
        nonlocal pending
        if not pending:
            return
        words = [w for line in pending for w in line['words']]
        match = _RANGE.fullmatch(words[-1]['text'])
        # A folio has its own right-hand column, separated from the title.
        suffix = pending[-1]['words']
        separated = (len(suffix) == 1 or suffix[-1]['bbox'][0] - suffix[-2]['bbox'][2] >= 8)
        printed = match is not None and separated and words[-1]['bbox'][0] > .75 * source['width']
        marker = _ITEM.fullmatch(words[0]['text'])
        entry = {'id': f"p{source['page']}:contents{len(entries)}", 'section': current,
                 'number': ROMAN.index(marker.group(1)) + 1,
                 'title': ' '.join(w['text'] for w in words[1:-1]) if printed
                 else ' '.join(w['text'] for w in words[1:]),
                 'source_lines': [_public(line) for line in pending],
                 'declared_folio': words[-1]['text'] if printed else None,
                 'folio_start': int(match.group(1)) if printed else None,
                 'folio_end': int(match.group(2) or match.group(1)) if printed else None,
                 'review_status': 'unreviewed'}
        entries.append(entry)
        if not printed:
            issues.append({'kind': 'contents_folio_unresolved', 'entry_id': entry['id']})
        pending = []

    for index, line in enumerate(lines):
        banner = _banner(line)
        if banner:
            finish()
            current, inline = banner
            title, witnesses = _title(lines, index, inline)
            sections.append({'number': current, 'title': title,
                             'banner': _public(line), 'title_sources': witnesses})
            continue
        if not line['valid']:
            finish()
            issues.append({'kind': 'contents_line_unresolved', 'source': _public(line)})
            continue
        if current is None:
            continue
        marker = _ITEM.fullmatch(line['words'][0]['text'])
        if marker:
            finish()
            pending = [line]
        elif pending:
            previous = pending[-1]
            if (line['bbox'][1] - previous['bbox'][3] <= 2 * (previous['bbox'][3] - previous['bbox'][1])
                    and line['bbox'][0] >= pending[0]['bbox'][0]):
                pending.append(line)
            else:
                finish()
        if pending:
            last = pending[-1]['words']
            if (_RANGE.fullmatch(last[-1]['text']) and last[-1]['bbox'][0] > .75 * source['width']
                    and (len(last) == 1 or last[-1]['bbox'][0] - last[-2]['bbox'][2] >= 8)):
                finish()
    finish()
    return sections, entries


def _body_item_matches(entry, section, all_lines):
    if section is None:
        return []
    target = [fold(w).rstrip(':') for w in entry['title'].split()]
    matches = []
    for page in range(section['page_start'], section['page_end'] + 1):
        lines = all_lines.get(page, [])
        for index, line in enumerate(lines):
            marker = _ITEM.fullmatch(line['words'][0]['text'])
            if not line['valid'] or not marker or ROMAN.index(marker.group(1)) + 1 != entry['number']:
                continue
            selected, actual = [line], [fold(w['text']).rstrip(':') for w in line['words'][1:]]
            for following in lines[index + 1:]:
                if len(actual) >= len(target):
                    break
                previous = selected[-1]
                if (not following['valid'] or _banner(following)
                        or _ITEM.fullmatch(following['words'][0]['text'])
                        or following['bbox'][0] < line['bbox'][0]
                        or following['bbox'][1] - previous['bbox'][3] > 2 * (previous['bbox'][3] - previous['bbox'][1])):
                    break
                selected.append(following)
                actual.extend(fold(w['text']).rstrip(':') for w in following['words'])
            if actual == target:
                matches.append({'page': page, 'source_lines': [_public(s) for s in selected]})
    return matches


def document_navigation(evidence: list[dict]) -> dict:
    """Retain source claims even when the body or the folio map disagrees."""
    body, contents, entries, folios, issues = [], [], [], [], []
    all_lines = {}
    for source in evidence[1:]:
        lines = _lines(source)
        all_lines[source['page']] = lines
        banners = [(i, found) for i, line in enumerate(lines) if (found := _banner(line))]
        if len({found[0] for _, found in banners}) >= 2:
            heads, items = _contents(source, lines, issues)
            contents.append({'page': source['page'], 'sections': heads})
            entries.extend(items)
        elif len(banners) == 1:
            index, (number, inline) = banners[0]
            title, witnesses = _title(lines, index, inline)
            body.append({'number': number, 'page': source['page'], 'title': title,
                         'banner': _public(lines[index]), 'title_sources': witnesses})
        for line in lines:
            match = _FOLIO.fullmatch(line['text'])
            if (line['valid'] and match and line['bbox'][1] > .88 * source['height']
                    and .2 * source['width'] <= line['bbox'][0] <= .8 * source['width']):
                folios.append({'folio': int(match.group(1)), 'source': _public(line)})

    by_number, by_folio = defaultdict(list), defaultdict(list)
    for item in body:
        by_number[item['number']].append(item)
    for item in folios:
        by_folio[item['folio']].append(item['source'])
    expected = {s['number'] for page in contents for s in page['sections']} or set(by_number)
    supported = (len(expected) >= 3 and expected == set(range(1, max(expected) + 1))
                 and set(by_number) == expected and all(len(v) == 1 for v in by_number.values()))
    ordered = [by_number[n][0] for n in sorted(by_number)] if supported else []
    supported = bool(supported and all(a['page'] < b['page'] for a, b in zip(ordered, ordered[1:])))
    sections = []
    if supported:
        for index, item in enumerate(ordered):
            sections.append({'number': item['number'], 'title': item['title'], 'page_start': item['page'],
                             'page_end': ordered[index + 1]['page'] - 1 if index + 1 < len(ordered) else evidence[0]['page_count'],
                             'method': 'source_body_banner', 'role': role_from_title(item['title']),
                             'review_status': 'unreviewed'})
    elif body or contents:
        issues.append({'kind': 'body_section_sequence_unresolved'})
    for entry in entries:
        matches = by_folio.get(entry['folio_start'], [])
        entry['folio_sources'] = matches
        entry['page_start'] = matches[0]['page'] if len(matches) == 1 else None
        entry['mapping_status'] = 'unique_printed_folio' if len(matches) == 1 else 'ambiguous' if matches else 'unresolved'
        end_matches = by_folio.get(entry['folio_end'], [])
        entry['folio_end_sources'] = end_matches
        entry['page_end'] = end_matches[0]['page'] if len(end_matches) == 1 else None
        entry['end_mapping_status'] = 'unique_printed_folio' if len(end_matches) == 1 else 'ambiguous' if end_matches else 'unresolved'
        section = next((s for s in sections if s['number'] == entry['section']), None)
        entry['body_section_page'] = section['page_start'] if section else None
        entry['body_title_matches'] = _body_item_matches(entry, section, all_lines)
        if section and entry['page_start'] is not None and not section['page_start'] <= entry['page_start'] <= section['page_end']:
            issues.append({'kind': 'contents_target_outside_body_section', 'entry_id': entry['id'],
                           'section': entry['section'], 'declared_folio': entry['declared_folio'],
                           'mapped_pdf_page': entry['page_start'], 'body_section_page': section['page_start']})
    # A section divider can repeat every statement title. Preserve these
    # occurrences, but do not mistake the short list for six statement starts.
    occurrences = defaultdict(list)
    for entry in entries:
        for match in entry['body_title_matches']:
            occurrences[match['page']].append((entry, match))
    index_pages = set()
    for page, found in occurrences.items():
        covered = {w for _, match in found for line in match['source_lines'] for w in line['word_ids']}
        total = sum(len(line['words']) for line in all_lines[page])
        if len({entry['number'] for entry, _ in found}) >= 3 and total and len(covered) / total >= .6:
            index_pages.add(page)
    for entry in entries:
        for match in entry['body_title_matches']:
            match['kind'] = 'section_index_candidate' if match['page'] in index_pages else 'body_title_candidate'
        title_pages = {m['page'] for m in entry['body_title_matches'] if m['kind'] == 'body_title_candidate'}
        if len(title_pages) == 1 and entry['page_start'] is not None and entry['page_start'] not in title_pages:
            issues.append({'kind': 'contents_target_differs_from_body_title', 'entry_id': entry['id'],
                           'section': entry['section'], 'declared_folio': entry['declared_folio'],
                           'mapped_pdf_page': entry['page_start'], 'body_title_page': next(iter(title_pages))})
    return {'schema_version': NAVIGATION_VERSION, 'sections': sections, 'contents_entries': entries,
            'body_banners': body, 'contents_pages': contents, 'folio_observations': folios,
            'section_status': 'source_body_sequence' if supported else 'unresolved',
            'issues': issues, 'semantic_verification': 'not_performed'}


def verify_document_navigation(structure: dict, evidence: list[dict]) -> list[str]:
    if 'navigation_schema' not in structure and 'navigation' not in structure:
        return []  # Prior revisions remain readable.
    expected = document_navigation(evidence)
    errors = []
    if structure.get('navigation_schema') != NAVIGATION_VERSION or structure.get('navigation') != expected:
        errors.append('navigation_source_mismatch')
    if structure.get('sections') != expected['sections'] or structure.get('contents_items') != expected['contents_entries']:
        errors.append('navigation_projection_mismatch')
    for page in structure['pages']:
        section = next((s for s in expected['sections'] if s['page_start'] <= page['page'] <= s['page_end']), None)
        context = {k: section[k] for k in ('number', 'title', 'role')} if section else None
        if any(element.get('section_candidate') != context for element in page.get('narrative_elements', [])):
            errors.append(f"page_{page['page']}:narrative_section_mismatch")
    return errors
