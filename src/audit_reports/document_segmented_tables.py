"""Whole-table alternatives supported by repeated cell-width horizontal rules.

Keep the original candidates. This view requires a complete repeated column
partition, a separate period-header rule and non-overlapping native header
blocks. It preserves literal text, blank slots and all drawing/word witnesses.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from .document_rule_tables import _text
from .document_table_rows import _lines

METHOD = 'segmented_rules_and_source_lines'


def _rules(source):
    groups = defaultdict(list)
    for drawing in source['drawings']:
        x0, y0, x1, y1 = drawing['bbox']
        if x1 - x0 >= 8 and 0 <= y1 - y0 <= 2:
            groups[round((y0 + y1) / 2)].append(drawing)
    result = []
    for _y, drawings in sorted(groups.items()):
        drawings.sort(key=lambda d: d['bbox'][0])
        if len(drawings) < 3 or any(abs(a['bbox'][2] - b['bbox'][0]) > 2
                                   for a, b in zip(drawings, drawings[1:])):
            continue
        result.append({'y': median((d['bbox'][1] + d['bbox'][3]) / 2 for d in drawings),
                       'edges': [drawings[0]['bbox'][0],
                                 *((a['bbox'][2] + b['bbox'][0]) / 2 for a, b in zip(drawings, drawings[1:])),
                                 drawings[-1]['bbox'][2]],
                       'drawing_ids': [d['id'] for d in drawings]})
    return result


def _same_edges(left, right):
    return len(left) == len(right) and all(abs(a - b) <= 2 for a, b in zip(left, right, strict=True))


def _inside(word, box):
    x0, y0, x1, y1 = word['bbox']
    return box[0] <= (x0 + x1) / 2 < box[2] and box[1] <= (y0 + y1) / 2 < box[3]


def _cell(words, row, column, box):
    return {'row': row, 'column': column, 'bbox': box, 'text': _text(words),
            'word_ids': [w['id'] for w in words], 'source_text_matches': True, 'slot_status': 'present'}


def _make(source, chain, header_rule):
    edges = [median(rule['edges'][c] for rule in chain) for c in range(len(chain[0]['edges']))]
    top, bottom = chain[0]['y'], chain[-1]['y']
    header_y = header_rule['y']
    header_top = max(0, header_y - 2 * (top - header_y))
    preceding = [w for w in source['words'] if _inside(w, [edges[0], header_top, edges[-1], header_y])]
    if not preceding:
        return None
    # Stop at the first clear horizontal whitespace band above the header.
    # A nearby section title must not be clipped into a table header.
    gap = median(w['bbox'][3] - w['bbox'][1] for w in preceding)
    reached = header_y
    for word in sorted(preceding, key=lambda w: w['bbox'][3], reverse=True):
        if reached - word['bbox'][3] > gap:
            break
        reached = min(reached, word['bbox'][1])
    header_top = reached - .25
    bounds = [edges[0], header_top, edges[-1], bottom]
    selected = [w for w in source['words'] if _inside(w, bounds)]
    period = [w for w in selected if _inside(w, [edges[0], header_y, edges[-1], top])]
    groups = defaultdict(list)
    for word in selected:
        if _inside(word, [edges[0], header_top, edges[-1], header_y]):
            groups[word['block']].append(word)
    # The whole amount-column width must be covered once by at least two native
    # blocks. A paragraph or a single ambiguous title cannot supply these groups.
    if len(groups) < 2:
        return None
    header_ids = {w['id'] for words in groups.values() for w in words}
    if any(w['block'] in groups and w['id'] not in header_ids for w in source['words']):
        return None  # Do not truncate a larger native block into a header.
    header_cells = [_cell([], 0, c, None) for c in range(len(edges) - 1)]
    for cell in header_cells:
        cell.update(text=None, slot_status='absent_or_merged')
    header_cells[0] = _cell([], 0, 0, [edges[0], header_top, edges[1], header_y])
    occupied = []
    witnesses = []
    for block, words in sorted(groups.items(), key=lambda entry: min(w['bbox'][0] for w in entry[1])):
        left, right = min(w['bbox'][0] for w in words), max(w['bbox'][2] for w in words)
        columns = [c for c in range(1, len(edges) - 1) if edges[c] < right and left < edges[c + 1]]
        if (not columns or left < edges[columns[0]] - .75 or right > edges[columns[-1] + 1] + .75
                or set(columns).intersection(occupied)):
            return None
        occupied.extend(columns)
        first, stop = columns[0], columns[-1] + 1
        header_cells[first] = _cell(words, 0, first, [edges[first], header_top, edges[stop], header_y])
        witnesses.append({'source_block': block, 'columns': columns, 'word_ids': [w['id'] for w in words]})
    if sorted(occupied) != list(range(1, len(edges) - 1)):
        return None
    period_cells = []
    for c, (left, right) in enumerate(zip(edges, edges[1:])):
        words = [w for w in period if left <= (w['bbox'][0] + w['bbox'][2]) / 2 < right]
        if bool(words) != (c != 0) or any(w['bbox'][0] < left - .75 or w['bbox'][2] > right + .75 for w in words):
            return None
        period_cells.append(_cell(words, 1, c, [left, header_y, right, top]))
    body = [w for w in selected if _inside(w, [edges[0], top, edges[-1], bottom])]
    lines = _lines(body)
    if lines is None or len(lines) < 3:
        return None
    line_tops = [min(w['bbox'][1] for w in line) for line in lines]
    line_bottoms = [max(w['bbox'][3] for w in line) for line in lines]
    cuts = [top, *((a + b) / 2 for a, b in zip(line_bottoms, line_tops[1:])), bottom]
    rows = [{'index': 0, 'cells': header_cells}, {'index': 1, 'cells': period_cells}]
    for line_no, line in enumerate(lines):
        cells = []
        for c, (left, right) in enumerate(zip(edges, edges[1:])):
            words = [w for w in line if left <= (w['bbox'][0] + w['bbox'][2]) / 2 < right]
            if any(w['bbox'][0] < left - .75 or w['bbox'][2] > right + .75 for w in words):
                return None
            cells.append(_cell(words, line_no + 2, c, [left, cuts[line_no], right, cuts[line_no + 1]]))
        if not cells[0]['word_ids'] or sum(bool(c['word_ids']) for c in cells[1:]) < 2:
            return None
        rows.append({'index': line_no + 2, 'cells': cells})
    used = Counter(i for row in rows for cell in row['cells'] for i in cell['word_ids'])
    if used != Counter(w['id'] for w in selected) or any(n != 1 for n in used.values()):
        return None
    return {'id': '', 'kind': 'table_candidate', 'method': METHOD, 'bbox': bounds,
            'rows': rows, 'row_count': len(rows), 'n_cols': len(edges) - 1,
            'rule_witnesses': chain, 'period_header_rule': header_rule, 'header_block_witnesses': witnesses,
            'source_drawing_ids': [i for rule in [header_rule, *chain] for i in rule['drawing_ids']],
            'review_status': 'unreviewed', 'header_association_verified': False,
            'physical_source_unchanged': True, 'semantic_verification': 'not_performed'}


def segmented_table_candidates(source, existing):
    rules, result = _rules(source), []
    consumed = set()
    for start, rule in enumerate(rules):
        if start in consumed:
            continue
        chain = [rule]
        indexes = [start]
        for index in range(start + 1, len(rules)):
            current = rules[index]
            if not 3 <= current['y'] - chain[-1]['y'] <= 40 or not _same_edges(current['edges'], rule['edges']):
                break
            chain.append(current); indexes.append(index)
        if len(chain) < 3:
            continue
        consumed.update(indexes)
        headers = [r for r in rules[:start] if 6 <= rule['y'] - r['y'] <= 30
                   and _same_edges(r['edges'], rule['edges'][1:])]
        if len(headers) != 1:
            continue
        # A complete ruled table already records this source region.
        if any(t['method'] == 'pymupdf_lines_strict' and t['bbox'][0] <= rule['edges'][0] + 2
               and t['bbox'][2] >= rule['edges'][-1] - 2 and t['bbox'][1] <= headers[0]['y']
               and t['bbox'][3] >= chain[-1]['y'] - 2 for t in existing):
            continue
        table = _make(source, chain, headers[0])
        if table:
            table['id'] = f"p{source['page']}:segmented{len(result)}"
            result.append(table)
    return result


def verify_segmented_tables(page, source):
    observed = [t for t in page['tables'] if t['method'] == METHOD]
    if not observed and 'segmented_tables_schema' not in page:
        return []  # Earlier captures remain readable.
    if page.get('segmented_tables_schema') != 'segmented-table-candidates-1':
        return ['segmented_table_schema_mismatch']
    expected = segmented_table_candidates(source, [t for t in page['tables'] if t['method'] != METHOD])
    return [] if observed == expected else ['segmented_table_source_mismatch']
