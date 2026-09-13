"""Source-word grids where a printed frame has no extractable inner rulings.

The currency header supplies the column inventory. Repeated aligned amounts
support the body partition; no amount is parsed, fitted to a sum or discarded.
These are candidates, not reviewed financial interpretations. Unsupported or
ambiguous headers/positions abstain and leave the other capture views intact.
"""
from __future__ import annotations

from collections import Counter
import re
from statistics import median

from .document_reviewed_grid import reviewed_source_lines

METHOD = "framed_currency_headers_and_source_words"
SCHEMA = "framed-currency-tables-1"
_AMOUNT = re.compile(r"(?:[-–—]+|[+-]?\(?\d[\d.,]*\)?%?)\Z")
_NOTE = re.compile(r"(?:\(?\d+(?:[.\-]\d+)+\)?|\([IVXLC]+[.\-]\d+\))\Z")


def _cx(w):
    return (w['bbox'][0] + w['bbox'][2]) / 2


def _cy(w):
    return (w['bbox'][1] + w['bbox'][3]) / 2


def _inside(w, box):
    return box[0] < _cx(w) < box[2] and box[1] < _cy(w) < box[3]


def _frame_bands(source):
    rules = [d for d in source['drawings'] if d['path_items'] == 1]
    vertical = [d for d in rules if 0 <= d['bbox'][2] - d['bbox'][0] <= 1
                and d['bbox'][3] - d['bbox'][1] > 40]
    horizontal = [d for d in rules if 0 <= d['bbox'][3] - d['bbox'][1] <= 1
                  and d['bbox'][2] - d['bbox'][0] > 80]
    for left in vertical:
        for right in vertical:
            x0, x1 = _cx(left), _cx(right)
            if x1 - x0 < 150 or any(abs(left['bbox'][i] - right['bbox'][i]) > 1 for i in (1, 3)):
                continue
            matches = sorted((d for d in horizontal if abs(d['bbox'][0] - x0) < 1
                              and d['bbox'][2] <= x1 + 1
                              and left['bbox'][1] - 1 <= _cy(d) <= left['bbox'][3] + 1), key=_cy)
            if (len(matches) >= 3 and all(abs(d['bbox'][2] - x1) < 1 for d in (matches[0], matches[-1]))
                    and abs(_cy(matches[0]) - left['bbox'][1]) < 1
                    and abs(_cy(matches[-1]) - left['bbox'][3]) < 1):
                yield [x0, _cy(matches[0]), x1, _cy(matches[-1])], [_cy(d) for d in matches[1:-1]], [left, right, *matches]


def _frames(source):
    for box, separators, rules in _frame_bands(source):
        if len(separators) == 1:
            yield box, separators[0], rules


def _cell(words, row, column, box):
    lines = reviewed_source_lines(words)
    ordered = [w for line in lines for w in line]
    return {'row': row, 'column': column, 'bbox': box,
            'text': '\n'.join(' '.join(w['text'] for w in line) for line in lines),
            'word_ids': [w['id'] for w in ordered], 'source_text_matches': True,
            'slot_status': 'present'}


def _make(source, box, body_top, rules):
    selected = [w for w in source['words'] if _inside(w, box)]
    header = [w for w in selected if _cy(w) < body_top]
    body = [w for w in selected if _cy(w) >= body_top]
    notes = [w for w in header if w['text'].casefold() in ('footnotes', 'dipnot', 'dipnotlar')]
    if len(notes) != 1 or not body:
        return None
    note = notes[0]
    header_lines = reviewed_source_lines([w for w in header if w['bbox'][0] > note['bbox'][2]])
    # The supported header is unit, period, date and currency. Do not guess
    # which dates a more complicated, restated or wrapped header qualifies.
    if len(header_lines) != 4:
        return None
    leaves = header_lines[-1]
    labels = [w['text'].casefold() for w in leaves]
    triplets = [labels[i:i + 3] for i in range(0, len(labels), 3)]
    if (not 2 <= len(triplets) <= 4 or any(t not in (['tl', 'fc', 'total'], ['tp', 'yp', 'toplam']) for t in triplets)
            or len(leaves) != 3 * len(triplets)):
        return None
    n = len(leaves)
    centers = [_cx(w) for w in leaves]
    initial = [(note['bbox'][2] + leaves[0]['bbox'][0]) / 2,
               *((a + b) / 2 for a, b in zip(centers, centers[1:])), box[2]]
    if any(b <= a for a, b in zip(initial, initial[1:])):
        return None
    lines = reviewed_source_lines(body)
    if len(lines) < 6:
        return None
    data, note_words, label_words = [[] for _ in leaves], [], []
    for w in body:
        if _cx(w) >= initial[0]:
            matches = [i for i in range(n) if initial[i] <= _cx(w) < initial[i + 1]]
            if len(matches) != 1 or not _AMOUNT.fullmatch(w['text']):
                return None
            data[matches[0]].append(w)
        elif _cx(w) > (note['bbox'][0] + note['bbox'][2]) / 2 - (note['bbox'][2] - note['bbox'][0]):
            if not _NOTE.fullmatch(w['text']):
                return None
            note_words.append(w)
        else:
            label_words.append(w)
    if not label_words or any(len(ws) < 4 for ws in data):
        return None
    # Right alignment may vary slightly between regular and bold fonts. A
    # second amount band in a proposed column is an ambiguity, not a merge.
    # A closing parenthesis may hang past the right-aligned digits. Bound the
    # allowance by half a native glyph height, still requiring disjoint columns.
    if any(max(w['bbox'][2] for w in ws) - min(w['bbox'][2] for w in ws)
           > .5 * median(w['bbox'][3] - w['bbox'][1] for w in ws) for ws in data):
        return None
    groups = [label_words, [*note_words, note], *data]
    edges = [box[0], *((max(w['bbox'][2] for w in a) + min(w['bbox'][0] for w in b)) / 2
                       for a, b in zip(groups, groups[1:])), box[2]]
    if any(b <= a for a, b in zip(edges, edges[1:])):
        return None
    memberships = {}
    for c, ws in enumerate(groups):
        for w in ws:
            if w['bbox'][0] < edges[c] or w['bbox'][2] > edges[c + 1]:
                return None
            memberships[w['id']] = c
    if any(sum(memberships[w['id']] == c for w in line) > 1 for line in lines for c in range(1, n + 2)):
        return None  # Two words/amounts at one cell cannot silently collapse.
    if any(not any(memberships[w['id']] == 0 for w in line) for line in lines):
        return None  # Floating values require a different row-assignment path.
    # Header/body row boundaries partition the whole printed frame. Header
    # titles and the note heading span all four header rows, preserving blanks.
    hys = [median(_cy(w) for w in line) for line in header_lines]
    bys = [median(_cy(w) for w in line) for line in lines]
    ys = [box[1], *((a + b) / 2 for a, b in zip(hys, hys[1:])), body_top,
          *((a + b) / 2 for a, b in zip(bys, bys[1:])), box[3]]
    rows = []
    for r in range(len(ys) - 1):
        cells = []
        for c in range(n + 2):
            row_stop, col_stop = r + 1, c + 1
            covered = r in (1, 2, 3) and c < 2
            if r == 0 and c < 2:
                row_stop = 4
            elif r == 0 and c >= 2:
                covered = c != 2
                col_stop = n + 2
            elif r in (1, 2) and c >= 2:
                covered = (c - 2) % 3 != 0
                col_stop = c + 3
            if covered:
                cells.append({'row': r, 'column': c, 'bbox': None, 'text': None,
                              'word_ids': [], 'source_text_matches': True, 'slot_status': 'absent_or_merged'})
                continue
            cell_box = [edges[c], ys[r], edges[col_stop], ys[row_stop]]
            words = [w for w in selected if _inside(w, cell_box)]
            # Every literal word must fit its column and its baseline must fit
            # its row. Font boxes may overlap adjacent baseline bands vertically.
            if any(w['bbox'][0] < cell_box[0] or w['bbox'][2] > cell_box[2] for w in words):
                return None
            cells.append(_cell(words, r, c, cell_box))
        rows.append({'index': r, 'cells': cells})
    if Counter(i for r in rows for c in r['cells'] for i in c['word_ids']) != Counter(w['id'] for w in selected):
        return None
    # A period's date must remain inside that period's group and all currency
    # leaves must occupy distinct cells in their original order.
    if ([c['text'] for c in rows[3]['cells'][2:]] != [w['text'] for w in leaves]
            or any(not re.search(r'\b(?:19|20)\d{2}\b', rows[2]['cells'][c]['text'] or '')
                   for c in range(2, n + 2, 3))):
        return None
    return {'id': f"p{source['page']}:framed{rules[0]['id']}", 'kind': 'table_candidate', 'method': METHOD,
            'rows': rows, 'row_count': len(rows), 'n_cols': n + 2, 'bbox': box,
            'source_drawing_ids': [d['id'] for d in rules],
            'column_header_word_ids': [w['id'] for w in leaves], 'note_header_word_id': note['id'],
            'row_assignment': 'native_baseline_bands', 'column_assignment': 'printed_currency_headers_and_alignment',
            'review_status': 'unreviewed', 'header_association_verified': False}


def framed_table_candidates(source):
    if source.get('actualtext_changes_word_view') or not any(
            w['text'].casefold() in ('footnotes', 'dipnot', 'dipnotlar') for w in source['words']):
        return []
    result = []
    for box, body_top, rules in _frames(source):
        try:
            table = _make(source, box, body_top, rules)
        except ValueError:  # Ambiguous native baseline grouping.
            continue
        if table is not None:
            result.append(table)
    return result


def verify_framed_tables(page, source):
    actual = [t for t in page['tables'] if t.get('method') == METHOD]
    if page.get('framed_tables_schema') != SCHEMA:
        return ['unknown_framed_tables_schema'] if actual or 'framed_tables_schema' in page else []
    return [] if actual == framed_table_candidates(source) else ['framed_tables_source_mismatch']
