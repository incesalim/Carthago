"""Apply explicitly reviewed logical rows without rewriting physical PDF cells.

This is a transcription view for named source annotations, not an automatic
financial interpretation or a general permission to move characters.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import unicodedata

from .document_cell_fragments import cell_word_fragments, verify_cell_fragments
from .document_table_context import _grid
from .document_table_rows import _lines


def _text(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').split())


def reviewed_logical_rows(table: dict, source: dict, case: dict) -> list[dict]:
    """Require a complete, positioned source-word inventory for each reviewed row.

    A reviewer supplies the independently read wording and word occurrences.
    The whole word must lie in its reviewed row and its centre in its reviewed
    column. Its full character inventory must equal the physical row, including
    letters split between physical cells. Unreviewed rows retain their cells.
    """
    if verify_cell_fragments(table, source):
        raise ValueError('Physical table has invalid source references')
    words = {w['id']: w for w in source['words']}
    rows = [{'row': r['index'], 'cells': [
        {'column': c['column'], 'text': c['text'], 'source_fragments': cell_word_fragments(c, words),
         'method': 'retained_physical_cell'} for c in r['cells']]} for r in table['rows']]
    overrides = case.get('logical_rows', [])
    grid = _grid(table)
    if overrides and grid is None:
        raise ValueError('Reviewed logical columns require a consistent physical grid')
    seen = set()
    for review in overrides:
        r = review['row']
        if (type(r) is not int or r in seen or not 0 <= r < len(rows)
                or not isinstance(review.get('source_review'), str) or not review['source_review'].strip()
                or len(review['cells']) != table['n_cols']):
            raise ValueError('Invalid or duplicated reviewed row')
        seen.add(r)
        expected = Counter((p['word_id'], i) for c in rows[r]['cells'] for p in c['source_fragments']
                           for i in range(p['start'], p['end']))
        observed, cells = Counter(), []
        for column, cell in enumerate(review['cells']):
            ids = cell['source_word_ids']
            if (not isinstance(ids, list) or any(type(i) is not int or i not in words for i in ids)
                    or len(ids) != len(set(ids)) or not isinstance(cell['text'], str)):
                raise ValueError('Invalid reviewed word occurrences')
            selected = [words[i] for i in ids]
            x0, x1 = grid['x_edges'][column:column + 2]
            y0, y1 = grid['y_edges'][r:r + 2]
            if any(not (x0 <= (w['bbox'][0] + w['bbox'][2]) / 2 <= x1
                        and y0 <= w['bbox'][1] <= w['bbox'][3] <= y1) for w in selected):
                raise ValueError('Reviewed word belongs to a different row or column')
            lines = _lines(selected) if selected else []
            if lines is None:
                raise ValueError('Ambiguous source line order')
            ordered = [w for line in lines for w in line]
            literal = '\n'.join(' '.join(w['text'] for w in line) for line in lines)
            if [w['id'] for w in ordered] != ids or _text(literal) != _text(cell['text']):
                raise ValueError('Reviewed wording or occurrence order differs from source')
            parts = [{'word_id': w['id'], 'start': 0, 'end': len(w['text']),
                      'text': w['text'], 'bbox': w['bbox']} for w in ordered]
            observed.update((p['word_id'], i) for p in parts for i in range(p['start'], p['end']))
            cells.append({'column': column, 'text': literal, 'source_fragments': parts,
                          'method': 'explicit_source_review', 'source_review': review['source_review']})
        if observed != expected or any(count != 1 for count in observed.values()):
            raise ValueError('Reviewed row loses, duplicates or borrows source characters')
        rows[r] = {'row': r, 'cells': cells}
    return deepcopy(rows)
