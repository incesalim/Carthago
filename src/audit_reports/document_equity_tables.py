"""Retain wide, framed equity statements with native grouped column headings.

Explicit period bands and repeated amount positions support a candidate grid.
No fixed bank coordinates, amounts, column count or accounting identities are
used. Ambiguous headers, missing period bands and overlapping cells abstain.
The output remains unreviewed: baseline bands are not certified logical rows.
"""
from collections import Counter, defaultdict
import re
from statistics import median
import unicodedata

from .document_framed_tables import _AMOUNT, _NOTE, _cell, _cx, _cy, _frame_bands, _inside
from .document_reviewed_grid import reviewed_source_lines

METHOD = 'framed_equity_headers_and_source_words'
SCHEMA = 'framed-equity-tables-1'
_DATES = re.compile(r'\(?\d{2}[/.]\d{2}[/.](?:19|20)\d{2}[-–]\d{2}[/.]\d{2}[/.](?:19|20)\d{2}\)?\Z')


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).replace('ı', 'i')


def _native_lines(words):
    lines = defaultdict(list)
    for word in words:
        lines[word['block'], word['line']].append(word)
    return [sorted(line, key=lambda w: w['bbox'][0]) for line in lines.values()]


def _headers(header, note, groups, box, top):
    words = [w for w in header if w['bbox'][0] > note['bbox'][2]]
    bands = reviewed_source_lines(words)
    if len(bands) < 3:
        return None
    leaves = _native_lines(bands[-1])
    leaves.sort(key=lambda line: min(w['bbox'][0] for w in line))
    if len(leaves) != len(groups):
        return None
    # One separated upper group band is supported. A second tier, interleaved
    # header or tightly packed hierarchy requires another capture path.
    height = median(w['bbox'][3] - w['bbox'][1] for w in words)
    gaps = [i for i in range(2, len(bands))
            if min(w['bbox'][1] for w in bands[i]) - max(w['bbox'][3] for w in bands[i - 1]) > 2 * height]
    if len(gaps) != 1:
        return None
    split = gaps[0]
    unit, parent_words, leaf_words = bands[0], [w for band in bands[1:split] for w in band], [w for band in bands[split:] for w in band]
    unit_text = _fold(' '.join(w['text'] for w in unit))
    if not (('thousand' in unit_text or 'bin ' in unit_text or 'million' in unit_text or 'milyon' in unit_text)
            and ('tl' in unit_text or 'lira' in unit_text)):
        return None
    leaf_centers = [(min(w['bbox'][0] for w in line) + max(w['bbox'][2] for w in line)) / 2 for line in leaves]
    spans = defaultdict(list)
    for line in _native_lines(leaf_words):
        lo, hi = min(w['bbox'][0] for w in line), max(w['bbox'][2] for w in line)
        hits = [c for c, center in enumerate(leaf_centers) if lo <= center <= hi]
        if len(hits) != 1:
            return None
        spans[hits[0], hits[0] + 1].extend(line)
    if any((c, c + 1) not in spans for c in range(len(groups))):
        return None
    groups = [[*body, *spans[c, c + 1]] for c, body in enumerate(groups)]
    edges = [(note['bbox'][2] + min(w['bbox'][0] for w in groups[0])) / 2,
             *((max(w['bbox'][2] for w in a) + min(w['bbox'][0] for w in b)) / 2
               for a, b in zip(groups, groups[1:])), box[2]]
    if any(b <= a for a, b in zip(edges, edges[1:])) or any(
            w['bbox'][0] < edges[c] or w['bbox'][2] > edges[c + 1]
            for c, group in enumerate(groups) for w in group):
        return None
    parent_lines = []
    for line in _native_lines(parent_words):
        lo, hi = min(w['bbox'][0] for w in line), max(w['bbox'][2] for w in line)
        hits = [c for c, center in enumerate(leaf_centers) if lo <= center <= hi]
        if not hits:
            return None
        parent_lines.append((hits[0], hits[-1] + 1, line))
    outer = {(a, b) for a, b, _ in parent_lines
             if b - a > 1 and not any(c <= a and b <= d and (a, b) != (c, d) for c, d, _ in parent_lines)}
    for a, b, line in parent_lines:
        matches = [(c, d) for c, d in outer if c <= a and b <= d
                   and all(edges[c] <= w['bbox'][0] < w['bbox'][2] <= edges[d] for w in line)]
        if len(matches) != 1:
            return None
        spans[matches[0]].extend(line)
    n = len(groups)
    if any((c, c + 1) not in spans for c in range(n)):
        return None
    parents = [(a, b) for a, b in spans if b - a > 1]
    if not parents or any(set(range(a, b)) & set(range(c, d))
                          for i, (a, b) in enumerate(parents) for c, d in parents[i + 1:]):
        return None  # This path supports one unambiguous grouping level.
    parent_words = [w for span in parents for w in spans[span]]
    leaf_words = [w for (a, b), ws in spans.items() if b == a + 1 for w in ws]
    if (max(w['bbox'][3] for w in unit) >= min(w['bbox'][1] for w in parent_words)
            or max(w['bbox'][3] for w in parent_words) >= min(w['bbox'][1] for w in leaf_words)):
        return None
    ys = [box[1], (max(w['bbox'][3] for w in unit) + min(w['bbox'][1] for w in parent_words)) / 2,
          (max(w['bbox'][3] for w in parent_words) + min(w['bbox'][1] for w in leaf_words)) / 2, top]
    cells = [(0, 0, n, 1, unit)]
    for (a, b), ws in spans.items():
        row = 2 if b == a + 1 and any(x <= a < y for x, y in parents) else 1
        cells.append((row, a, b, 3 if b == a + 1 else 2, ws))
    return edges, ys, cells


def _make(source, box, separators, rules):
    if not 2 <= len(separators) <= 4 or any(abs(d['bbox'][2] - box[2]) > 1 for d in rules[2:]):
        return None
    selected = [w for w in source['words'] if _inside(w, box)]
    header = [w for w in selected if _cy(w) < separators[0]]
    notes = [w for w in header if _fold(w['text']) in ('footnotes', 'dipnot', 'dipnotlar')]
    if len(notes) != 1:
        return None
    note = notes[0]
    title = _fold(' '.join(w['text'] for w in header if w['bbox'][2] < note['bbox'][0]))
    if not (('equity' in title and 'changes' in title) or ('ozkaynak' in title and 'degisim' in title)):
        return None
    body = [w for w in selected if _cy(w) >= separators[0]]
    lines = reviewed_source_lines(body)
    amount_lines = [[w for w in line if _cx(w) > note['bbox'][2]] for line in lines]
    if any(not _AMOUNT.fullmatch(w['text']) for line in amount_lines for w in line):
        return None
    counts = Counter(len(line) for line in amount_lines if line)
    if not counts:
        return None
    n, frequency = counts.most_common(1)[0]
    if not 6 <= n <= 32 or frequency < 4 or any(k > n for k in counts):
        return None
    complete = [line for line in amount_lines if len(line) == n]
    groups = [[line[c] for line in complete] for c in range(n)]
    result = _headers(header, note, groups, box, separators[0])
    if result is None:
        return None
    amount_edges, ys, headers = result
    label_words = [w for w in selected if _cx(w) < note['bbox'][0]]
    if not label_words:
        return None
    edges = [box[0], (max(w['bbox'][2] for w in label_words) + note['bbox'][0]) / 2, *amount_edges]
    # A partial row cannot shift its later values left when one slot is blank.
    # Every amount must fit the columns established independently by full rows.
    for line in lines:
        memberships = []
        for w in line:
            hits = [c for c in range(n + 2) if edges[c] <= w['bbox'][0] < w['bbox'][2] <= edges[c + 1]]
            if len(hits) != 1 or (hits[0] == 1 and not _NOTE.fullmatch(w['text'])):
                return None
            memberships.append(hits[0])
        if 0 not in memberships or any(memberships.count(c) > 1 for c in range(1, n + 2)):
            return None
    # Each ruled body band starts with an explicit period and literal date
    # range. Preserve both native lines instead of propagating a guessed year.
    periods = []
    for start, end in zip(separators, [*separators[1:], box[3]], strict=True):
        band = [line for line in lines if start <= median(_cy(w) for w in line) < end]
        if len(band) < 6:
            return None
        text = _fold(' '.join(w['text'] for w in band[0]))
        if (text not in ('prior period', 'current period', 'restated prior period', 'onceki donem', 'cari donem', 'duzeltilmis onceki donem')
                or len(band[1]) != 1 or not _DATES.fullmatch(band[1][0]['text'])):
            return None
        if any(_cx(w) >= edges[1] for line in band[:2] for w in line):
            return None
        periods.append({'word_ids': [w['id'] for line in band[:2] for w in line],
                        'text': '\n'.join(' '.join(w['text'] for w in line) for line in band[:2]),
                        'y_start': start, 'y_end': end})
        centers = [median(_cy(w) for w in line) for line in band]
        ys.extend([*((a + b) / 2 for a, b in zip(centers, centers[1:])), end])
    specs = [(0, 0, 1, 3, [w for w in header if w['bbox'][2] < note['bbox'][0]]),
             (0, 1, 2, 3, [note]), *[(r, a + 2, b + 2, stop, ws) for r, a, b, stop, ws in headers]]
    anchors, covered = {}, set()
    for r, a, b, stop, ws in specs:
        cell_box = [edges[a], ys[r], edges[b], ys[stop]]
        if any(not _inside(w, cell_box) or w['bbox'][0] < edges[a] or w['bbox'][2] > edges[b] for w in ws):
            return None
        slots = {(rr, cc) for rr in range(r, stop) for cc in range(a, b)}
        if slots & covered:
            return None
        covered |= slots
        anchors[r, a] = _cell(ws, r, a, cell_box)
    rows = []
    for r in range(len(ys) - 1):
        cells = []
        for c in range(n + 2):
            if (r, c) in anchors:
                cell = anchors[r, c]
            elif (r, c) in covered:
                cell = {'row': r, 'column': c, 'bbox': None, 'text': None, 'word_ids': [],
                        'source_text_matches': True, 'slot_status': 'absent_or_merged'}
            elif r < 3:
                return None
            else:
                cell_box = [edges[c], ys[r], edges[c + 1], ys[r + 1]]
                cell = _cell([w for w in body if _inside(w, cell_box)], r, c, cell_box)
            cells.append(cell)
        rows.append({'index': r, 'cells': cells})
    if Counter(w['id'] for w in selected) != Counter(i for row in rows for cell in row['cells'] for i in cell['word_ids']):
        return None
    return {'id': f"p{source['page']}:equityframe{rules[0]['id']}", 'kind': 'table_candidate', 'method': METHOD,
            'rows': rows, 'row_count': len(rows), 'n_cols': n + 2, 'bbox': box,
            'source_drawing_ids': [d['id'] for d in rules], 'note_header_word_id': note['id'],
            'period_bands': periods, 'row_assignment': 'native_baseline_bands',
            'column_assignment': 'native_grouped_headers_and_amount_bands',
            'review_status': 'unreviewed', 'header_association_verified': False}


def equity_table_candidates(source):
    if source.get('actualtext_changes_word_view'):
        return []
    result = []
    for box, separators, rules in _frame_bands(source):
        try:
            table = _make(source, box, separators, rules)
        except ValueError:
            continue
        if table is not None:
            result.append(table)
    return result


def verify_equity_tables(page, source):
    actual = [t for t in page['tables'] if t.get('method') == METHOD]
    if page.get('equity_tables_schema') != SCHEMA:
        return ['unknown_equity_tables_schema'] if actual or 'equity_tables_schema' in page else []
    return [] if actual == equity_table_candidates(source) else ['equity_tables_source_mismatch']
