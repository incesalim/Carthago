"""Whitespace partitions over retained narrative elements, without rewriting them.

This is a physical reading candidate, not a semantic paragraph or role assignment.
Horizontal whitespace separates bands; within a band vertical whitespace groups
columns. Overlapping elements remain explicitly unresolved in their source order.
"""
from __future__ import annotations

from collections import Counter


def _bounds(items):
    return [min(e['bbox'][0] for e in items), min(e['bbox'][1] for e in items),
            max(e['bbox'][2] for e in items), max(e['bbox'][3] for e in items)]


def _partition(items, axis):
    ordered = sorted(items, key=lambda e: (e['bbox'][axis], e['ordinal']))
    groups, pending, end = [], [], None
    for item in ordered:
        start, stop = item['bbox'][axis], item['bbox'][axis + 2]
        # The PDF stores sub-point gaps between adjacent typeset lines.
        if pending and start - end >= .1:
            groups.append(pending)
            pending = []
        pending.append(item)
        end = max(end, stop) if end is not None else stop
    if pending:
        groups.append(pending)
    return groups


def _tree(items):
    if len(items) == 1:
        return items[0]['node']
    ordered = sorted(items, key=lambda e: (e['bbox'][1], e['ordinal']))
    if all(e['node']['kind'] == 'list_item_candidate' for e in items) and all(
            abs(a['bbox'][0] - b['bbox'][0]) <= .5
            and a['bbox'][1] < b['bbox'][1]
            and a['bbox'][3] - b['bbox'][1] <= .2 * min(
                a['bbox'][3] - a['bbox'][1], b['bbox'][3] - b['bbox'][1])
            for a, b in zip(ordered, ordered[1:])):
        return {'kind': 'sequence', 'axis': 'y', 'method': 'aligned_list_items',
                'bbox': _bounds(items), 'children': [e['node'] for e in ordered]}
    for axis in (1, 0):
        groups = _partition(items, axis)
        if len(groups) > 1:
            return {'kind': 'sequence', 'axis': 'y' if axis == 1 else 'x',
                    'bbox': _bounds(items), 'children': [_tree(g) for g in groups]}
    return {'kind': 'unresolved_overlap', 'bbox': _bounds(items),
            'children': [e['node'] for e in sorted(items, key=lambda e: e['ordinal'])]}


def reading_layout(page: dict, source: dict) -> dict:
    elements = page.get('narrative_elements', [])
    ids = [e['id'] for e in elements]
    if len(ids) != len(set(ids)):
        raise ValueError('Repeated narrative identifier')
    spans = {s['id']: s for s in source['spans']}
    pairs = []
    for marker in elements:
        if marker['text'].strip() not in ('•', '▪', '‣') or marker.get('table_ids'):
            continue
        box = marker['bbox']
        candidates = []
        for text in elements:
            if text['id'] == marker['id'] or text.get('table_ids') or text['text'].strip() in ('•', '▪', '‣'):
                continue
            first = text.get('source_lines', [None])[0]
            line = [spans[i] for i in text['span_ids']
                    if [spans[i]['block'], spans[i]['line']] == first]
            if not line:
                continue
            first_box = _bounds(line)
            height = min(box[3] - box[1], first_box[3] - first_box[1])
            if (0 <= first_box[0] - box[2] <= 4 * height
                    and abs(first_box[3] - box[3]) <= .2 * height):
                candidates.append(text['id'])
        if len(candidates) == 1:
            pairs.append((marker['id'], candidates[0]))
    uses = Counter(t for _, t in pairs)
    pairs = [(m, t) for m, t in pairs if uses[t] == 1]
    paired = {i for pair in pairs for i in pair}
    by_id = {e['id']: e for e in elements}
    items = []
    for ordinal, element in enumerate(elements):
        if element['id'] in paired:
            pair = next((p for p in pairs if p[0] == element['id']), None)
            if pair is None:
                continue
            box = _bounds([by_id[i] for i in pair])
            node = {'kind': 'list_item_candidate', 'bbox': box, 'element_ids': list(pair)}
        else:
            box = element['bbox']
            node = {'kind': 'element', 'bbox': box, 'element_ids': [element['id']]}
        items.append({'bbox': box, 'ordinal': ordinal, 'node': node})
    tree = _tree(items) if items else None
    order, issues = [], []

    def visit(node):
        if 'element_ids' in node:
            order.extend(node['element_ids'])
        else:
            if node['kind'] == 'unresolved_overlap':
                issues.append({'kind': 'unresolved_overlap', 'bbox': node['bbox']})
            for child in node['children']:
                visit(child)

    if tree:
        visit(tree)
    if Counter(order) != Counter(ids):
        raise ValueError('Reading layout does not retain every narrative element once')
    return {'method': 'source_whitespace_partitions-1', 'tree': tree,
            'element_order': order, 'list_pairs': [list(p) for p in pairs],
            'issues': issues, 'reading_order_verified': False,
            'paragraph_boundaries_verified': False, 'semantic_verification': 'not_performed'}


def verify_reading_layout(page: dict, source: dict) -> list[str]:
    if 'reading_layout' not in page:
        return []
    return [] if page['reading_layout'] == reading_layout(page, source) else ['reading_layout_source_mismatch']
