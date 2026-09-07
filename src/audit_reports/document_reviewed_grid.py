"""Validate an explicitly source-reviewed grid inside retained physical cells."""
from collections import Counter
import math
from statistics import median
import unicodedata

from .document_cell_fragments import cell_word_fragments
from .document_table_context import _grid


def reviewed_source_lines(words):
    """Order explicit source assignments by distinct baseline centres.

    Adjacent font boxes can overlap even when the printed lines are distinct.
    This applies only inside a grid whose entire wording is independently read.
    A word matching more than one baseline band still fails.
    """
    lines = []
    for word in sorted(words, key=lambda w: ((w['bbox'][1] + w['bbox'][3]) / 2, w['bbox'][0], w['id'])):
        center = (word['bbox'][1] + word['bbox'][3]) / 2
        height = word['bbox'][3] - word['bbox'][1]
        matches = [line for line in lines if abs(center - median((w['bbox'][1] + w['bbox'][3]) / 2 for w in line))
                   <= .3 * min(height, *(w['bbox'][3] - w['bbox'][1] for w in line))]
        if len(matches) > 1:
            raise ValueError('Reviewed grid source baseline is ambiguous')
        if matches:
            matches[0].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: (w['bbox'][0], w['bbox'][1], w['id']))
    return lines


def reviewed_grid_rows(table, source, review):
    """Partition source words without changing the original grid or any character.

    Review boundaries are transcription partitions, not newly asserted PDF rules.
    They must refine all existing physical boundaries. Covered slots stay null.
    """
    physical = _grid(table)
    if (physical is None or not isinstance(review, dict)
            or not isinstance(review.get('source_review'), str) or not review['source_review'].strip()):
        raise ValueError('Reviewed grid requires physical boundaries and a source review')
    axes = []
    for axis, key in enumerate(('x_edges', 'y_edges')):
        edges = review.get(key)
        if (not isinstance(edges, list) or len(edges) < 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in edges)
                or any(b <= a for a, b in zip(edges, edges[1:]))
                or abs(edges[0] - table['bbox'][axis]) > .1
                or abs(edges[-1] - table['bbox'][axis + 2]) > .1
                or any(not any(abs(v - old) <= .1 for v in edges) for old in physical[key])):
            raise ValueError('Reviewed grid moves or removes physical boundaries')
        axes.append(edges)
    x, y = axes
    rows, spans = review.get('rows'), review.get('spans')
    if (not isinstance(rows, list) or len(rows) != len(y) - 1 or not isinstance(spans, list)
            or any(not isinstance(row, list) or len(row) != len(x) - 1 for row in rows)):
        raise ValueError('Reviewed grid dimensions disagree')
    span_map = {}
    for span in spans:
        if (not isinstance(span, dict)
                or any(type(span.get(k)) is not int or span[k] < 0 for k in ('row', 'column', 'row_span', 'column_span'))
                or span['row_span'] < 1 or span['column_span'] < 1
                or span['row_span'] * span['column_span'] < 2
                or span['row'] + span['row_span'] >= len(y) or span['column'] + span['column_span'] >= len(x)
                or (span['row'], span['column']) in span_map):
            raise ValueError('Invalid reviewed grid span')
        span_map[span['row'], span['column']] = span
    words = {w['id']: w for w in source['words']}
    observed, covered, used_spans, result = Counter(), set(), set(), []
    norm = lambda value: ' '.join(unicodedata.normalize('NFKC', value).split())
    for r, row in enumerate(rows):
        cells = []
        for c, cell in enumerate(row):
            if (not isinstance(cell, dict) or 'text' not in cell or not isinstance(cell.get('source_word_ids'), list)
                    or any(type(i) is not int or i not in words for i in cell['source_word_ids'])
                    or len(cell['source_word_ids']) != len(set(cell['source_word_ids']))):
                raise ValueError('Invalid reviewed grid word references')
            ids, text = cell['source_word_ids'], cell.get('text')
            if (r, c) in covered:
                if text is not None or ids or (r, c) in span_map:
                    raise ValueError('Covered reviewed grid slot contains data')
                cells.append({'column': c, 'text': None, 'source_fragments': [], 'method': 'covered_reviewed_grid_slot'})
                continue
            if not isinstance(text, str):
                raise ValueError('Uncovered reviewed grid slot must retain literal text')
            span = span_map.get((r, c), {'row_span': 1, 'column_span': 1})
            if (r, c) in span_map:
                used_spans.add((r, c))
            rr, cc = r + span['row_span'], c + span['column_span']
            slots = {(a, b) for a in range(r, rr) for b in range(c, cc)}
            if slots & covered:
                raise ValueError('Reviewed grid spans overlap')
            covered.update(slots)
            selected = [words[i] for i in ids]
            if any(not (x[c] <= (w['bbox'][0] + w['bbox'][2]) / 2 <= x[cc]
                        and y[r] <= (w['bbox'][1] + w['bbox'][3]) / 2 <= y[rr]) for w in selected):
                raise ValueError('Reviewed grid word belongs to another cell')
            lines = reviewed_source_lines(selected)
            ordered = [w for line in lines for w in line]
            literal = '\n'.join(' '.join(w['text'] for w in line) for line in lines)
            if [w['id'] for w in ordered] != ids or norm(literal) != norm(text):
                raise ValueError('Reviewed grid literal wording or occurrence order differs')
            parts = [{'word_id': w['id'], 'start': 0, 'end': len(w['text']), 'text': w['text'], 'bbox': w['bbox']}
                     for w in ordered]
            observed.update((p['word_id'], i) for p in parts for i in range(p['start'], p['end']))
            cells.append({'column': c, 'text': literal, 'source_fragments': parts,
                          'method': 'explicit_source_grid', 'source_review': review['source_review']})
        if not any(c['source_fragments'] for c in cells):
            raise ValueError('Reviewed grid introduces an empty source row')
        result.append({'row': r, 'cells': cells})
    expected = Counter((p['word_id'], i) for row in table['rows'] for cell in row['cells']
                       for p in cell_word_fragments(cell, words) for i in range(p['start'], p['end']))
    if used_spans != set(span_map) or observed != expected or any(n != 1 for n in observed.values()):
        raise ValueError('Reviewed grid loses, duplicates or borrows source characters')
    return result
