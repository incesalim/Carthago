"""Source-linked ruled-table spans and explicit continuation candidates.

Keep every physical fragment and cell. A repeated heading alone never merges
tables: continuation requires an explicit marker and identical ordered column
identifiers on adjacent pages. These are reviewable relationships, not approval.
"""
from __future__ import annotations

import re
from statistics import median
import unicodedata


def _text(value):
    return ' '.join(unicodedata.normalize('NFC', value or '').split())


def _title(value):
    text = _text(value)
    marker = re.search(r'\s*\((?:continued|devamı|devami)\)\s*[:.]?$', text, re.I)
    return (text[:marker.start()].rstrip(' :.') if marker else text.rstrip(' :.')), marker is not None


def _grid(table):
    """Infer spanning slots only when every cell agrees with one physical grid."""
    rows, columns = table['rows'], table['n_cols']
    if table['method'] not in ('pymupdf_lines_strict', 'horizontal_rule_cells', 'segmented_rules_and_source_lines') or not rows or columns < 1:
        return None
    if any(len(row['cells']) != columns for row in rows):
        return None
    boxes = [[cell.get('bbox') for cell in row['cells']] for row in rows]
    if any(not any(row) for row in boxes):
        return None
    xs = []
    for column in range(columns):
        starts = [row[column][0] for row in boxes if row[column]]
        if not starts:
            return None
        xs.append(median(starts))
    xs.append(table['bbox'][2])
    ys = [max(box[1] for box in row if box) for row in boxes] + [table['bbox'][3]]
    if any(a >= b for edges in (xs, ys) for a, b in zip(edges, edges[1:])):
        return None
    slots, anchors = {}, []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row['cells']):
            box = cell.get('bbox')
            if box is None:
                if cell.get('text') is not None or cell['word_ids']:
                    return None
                continue
            if abs(box[0] - xs[c]) > .1 or abs(box[1] - ys[r]) > .1:
                return None
            right = [i for i in range(c + 1, len(xs)) if abs(xs[i] - box[2]) <= .1]
            bottom = [i for i in range(r + 1, len(ys)) if abs(ys[i] - box[3]) <= .1]
            if len(right) != 1 or len(bottom) != 1:
                return None
            for rr in range(r, bottom[0]):
                for cc in range(c, right[0]):
                    if (rr, cc) in slots:
                        return None
                    slots[rr, cc] = [r, c]
            anchors.append({'row': r, 'column': c, 'row_span': bottom[0] - r,
                            'column_span': right[0] - c})
    if len(slots) != len(rows) * columns:
        return None
    return {'method': 'cell_rectangles_on_shared_grid', 'x_edges': xs, 'y_edges': ys,
            'anchors': anchors,
            'covered_slots': [{'row': r, 'column': c, 'anchor': anchor}
                              for (r, c), anchor in sorted(slots.items()) if anchor != [r, c]],
            'semantic_verification': 'not_performed'}


def _heading(page, table):
    box = table.get('bbox')
    if not box:
        return None
    preceding = [e for e in page.get('narrative_elements', []) if e['kind'] == 'heading_candidate'
                 and e['bbox'][3] <= box[1] and box[1] - e['bbox'][3] <= 50
                 and e['bbox'][0] < box[2] and box[0] < e['bbox'][2]]
    if not preceding:
        return None
    closest = max(e['bbox'][3] for e in preceding)
    candidates = [e for e in preceding if abs(e['bbox'][3] - closest) <= .1]
    if len(candidates) != 1:
        return None
    heading = candidates[0]
    if any(t['id'] != table['id'] and t.get('bbox') and heading['bbox'][3] <= t['bbox'][1]
           and t['bbox'][3] <= box[1] for t in page['tables']):
        return None
    return {'page': page['page'], 'element_id': heading['id'], 'text': heading['text'],
            'source_span_ids': heading['span_ids'], 'bbox': heading['bbox']}


def _headers(table):
    if table['method'] != 'pymupdf_lines_strict' or table['n_cols'] < 3:
        return None
    candidates = []
    # An optional merged title may precede the column identifiers. Requiring an
    # empty stub and at least two distinct identifiers avoids using a data row.
    for row in table['rows'][:3]:
        cells = row['cells']
        if len(cells) != table['n_cols'] or _text(cells[0]['text']):
            continue
        labels = [_text(c['text']) for c in cells[1:]]
        if not all(labels) or len(set(labels)) != len(labels):
            continue
        if any(not c['source_text_matches'] or not c['bbox'] or not c['word_ids'] for c in cells[1:]):
            continue
        candidates.append({'row': row['index'], 'labels': labels,
                           'cells': [{'column': c['column'], 'text': c['text'],
                                      'word_ids': c['word_ids'], 'bbox': c['bbox']} for c in cells[1:]]})
    return candidates[0] if len(candidates) == 1 else None


def table_context(pages: list[dict]) -> list[dict]:
    """Return one page context per input page, without changing source structure."""
    results, previous = [], None
    for page in pages:
        tables = []
        for table in page['tables']:
            heading = _heading(page, table)
            tables.append({'table_id': table['id'], 'heading': heading,
                           'physical_grid': _grid(table), 'column_identifiers': _headers(table)})
        context = {'schema_version': 'table-context-1', 'tables': tables, 'continuations': [],
                   'semantic_verification': 'not_performed'}
        if previous is not None and previous[0]['page'] + 1 == page['page']:
            for current in tables:
                heading, headers = current['heading'], current['column_identifiers']
                if not heading or not headers or not _title(heading['text'])[1]:
                    continue
                matches = [p for p in previous[1]['tables'] if p['heading'] and p['column_identifiers']
                           and _title(p['heading']['text'])[0] == _title(heading['text'])[0]
                           and p['column_identifiers']['labels'] == headers['labels']]
                if matches:
                    context['continuations'].append({
                        'kind': 'table_continuation_candidate',
                        'status': 'unique_source_evidence' if len(matches) == 1 else 'ambiguous_previous_fragment',
                        'from_page': previous[0]['page'], 'from_table_ids': [p['table_id'] for p in matches],
                        'to_page': page['page'], 'to_table_id': current['table_id'],
                        'title': _title(heading['text'])[0], 'column_identifiers': headers['labels'],
                        'method': 'explicit_continued_title_and_ordered_column_identifiers',
                        'fragments_merged': False, 'semantic_verification': 'not_performed'})
        results.append(context)
        previous = page, context
    return results


def verify_table_context(pages: list[dict]) -> list[str]:
    if not any('table_context' in page for page in pages):
        return []  # Older revisions remain readable.
    expected = table_context(pages)
    return [f"page_{page['page']}:table_context_mismatch" for page, context in zip(pages, expected, strict=True)
            if page.get('table_context') != context]
