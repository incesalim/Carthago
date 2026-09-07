"""Candidate links from numbered column identifiers to adjacent source notes.

Only complete, uniquely aligned sequences are linked. The original header
cells, markers and paragraphs remain intact; no financial meaning is assigned.
"""
from __future__ import annotations

from collections import Counter
import re
from statistics import median

from .document_table_context import table_context


def _bounds(elements):
    return [min(e['bbox'][0] for e in elements), min(e['bbox'][1] for e in elements),
            max(e['bbox'][2] for e in elements), max(e['bbox'][3] for e in elements)]


def _numbered_pairs(page, source):
    elements = page.get('narrative_elements', [])
    spans = {s['id']: s for s in source['spans']}
    pairs = []
    for marker in elements:
        number = re.fullmatch(r'([1-9][0-9]?)\.', marker['text'].strip())
        if not number or marker['kind'] != 'list_item_candidate' or marker['table_ids']:
            continue
        matches = []
        for text in elements:
            if text['kind'] != 'paragraph_candidate' or text['table_ids'] or not text.get('source_lines'):
                continue
            first = [spans[i] for i in text['span_ids'] if [spans[i]['block'], spans[i]['line']] == text['source_lines'][0]]
            if not first:
                continue
            box = _bounds(first); mark = marker['bbox']; height = min(mark[3] - mark[1], box[3] - box[1])
            if 0 <= box[0] - mark[2] <= 4 * height and abs(box[3] - mark[3]) <= .2 * height:
                matches.append(text)
        if len(matches) == 1:
            pairs.append((number[1], marker, matches[0]))
    uses = Counter(text['id'] for _, _, text in pairs)
    return [(number, marker, text) for number, marker, text in pairs if uses[text['id']] == 1]


def table_note_links(page, source):
    contexts = {c['table_id']: c for c in table_context([page])[0]['tables']}
    pairs = _numbered_pairs(page, source)
    results = []
    for table in page['tables']:
        headers = contexts[table['id']]['column_identifiers']
        if not headers:
            continue
        cells = [c for c in headers['cells'] if re.fullmatch(r'[1-9][0-9]?', c['text'].strip())]
        labels = [c['text'].strip() for c in cells]
        if len(labels) < 2 or labels != [str(i) for i in range(1, len(labels) + 1)]:
            continue
        choices = [[(marker, text) for number, marker, text in pairs if number == label
                    and marker['bbox'][1] > table['bbox'][3]] for label in labels]
        if any(len(options) != 1 for options in choices):
            continue
        notes = [options[0] for options in choices]
        height = median(marker['bbox'][3] - marker['bbox'][1] for marker, _ in notes)
        if (notes[0][0]['bbox'][1] - table['bbox'][3] > 3 * height
                or any(abs(marker['bbox'][0] - notes[0][0]['bbox'][0]) > .5 for marker, _ in notes)
                or any(a[1]['bbox'][3] > b[0]['bbox'][1] + .2 * height
                       or b[0]['bbox'][1] - a[1]['bbox'][3] > 2 * height for a, b in zip(notes, notes[1:]))):
            continue
        bounds = _bounds([e for note in notes for e in note])
        if bounds[0] < table['bbox'][0] - 2 or bounds[2] > table['bbox'][2] + 2:
            continue
        expected_ids = {e['id'] for pair in notes for e in pair}
        inside_ids = {e['id'] for e in page['narrative_elements'] if bounds[0] <= e['bbox'][0]
                      and e['bbox'][2] <= bounds[2] and bounds[1] <= e['bbox'][1] and e['bbox'][3] <= bounds[3]}
        if inside_ids != expected_ids:
            continue
        links = []
        for cell, (marker, text) in zip(cells, notes, strict=True):
            links.append({'label': cell['text'].strip(), 'header_row': headers['row'], 'column': cell['column'],
                          'header_word_ids': cell['word_ids'], 'header_bbox': cell['bbox'],
                          **({'header_source_fragments': cell['source_fragments']} if 'source_fragments' in cell else {}),
                          'marker_element_id': marker['id'], 'marker_span_ids': marker['span_ids'], 'marker_bbox': marker['bbox'],
                          'text_element_id': text['id'], 'text_span_ids': text['span_ids'], 'text_bbox': text['bbox'],
                          'text': text['text']})
        results.append({'table_id': table['id'], 'links': links, 'source_region': bounds,
                        'method': 'ordered_column_numbers_and_adjacent_source_note_sequence',
                        'semantic_verification': 'not_performed'})
    # A duplicated table/header interpretation cannot claim the same note set.
    uses = Counter(link['marker_element_id'] for result in results for link in result['links'])
    results = [result for result in results if all(uses[link['marker_element_id']] == 1 for link in result['links'])]
    return {'schema_version': 'table-note-links-1', 'tables': results, 'semantic_verification': 'not_performed'}


def verify_table_note_links(page, source):
    if 'table_notes' not in page:
        return []
    return [] if page['table_notes'] == table_note_links(page, source) else ['table_note_source_mismatch']
