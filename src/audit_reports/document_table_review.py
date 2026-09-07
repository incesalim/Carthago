"""Apply explicitly reviewed logical rows without rewriting physical PDF cells.

This is a transcription view for named source annotations, not an automatic
financial interpretation or a general permission to move characters.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
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
    row_splits = case.get('row_splits', [])
    grid = _grid(table)
    if (overrides or row_splits) and grid is None:
        raise ValueError('Reviewed logical columns require a consistent physical grid')
    seen = set()
    for review in overrides:
        r = review['row']
        if (type(r) is not int or r in seen or not 0 <= r < len(rows)
                or not isinstance(review.get('source_review'), str) or not review['source_review'].strip()
                or len(review['cells']) != table['n_cols']):
            raise ValueError('Invalid or duplicated reviewed row')
        seen.add(r)
        if any(a['row'] <= r < a['row'] + a['row_span'] and a['row_span'] != 1
               for a in grid['anchors']):
            raise ValueError('Logical row review cannot cut a vertical merged cell')
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
    expanded = {}
    for review in row_splits:
        r = review['row']
        if (type(r) is not int or r in seen or not 0 <= r < len(rows)
                or not isinstance(review.get('source_review'), str) or not review['source_review'].strip()
                or not isinstance(review.get('rows'), list) or len(review['rows']) < 2
                or any(a['row'] <= r < a['row'] + a['row_span'] and a['row_span'] != 1
                       for a in grid['anchors'])):
            raise ValueError('Invalid or overlapping reviewed row split')
        seen.add(r)
        expected = Counter((p['word_id'], i) for c in rows[r]['cells'] for p in c['source_fragments']
                           for i in range(p['start'], p['end']))
        observed, split, previous_bottom = Counter(), [], grid['y_edges'][r]
        for subrow in review['rows']:
            if not isinstance(subrow.get('cells'), list) or len(subrow['cells']) != table['n_cols']:
                raise ValueError('Invalid reviewed split row columns')
            cells, row_words = [], []
            for column, cell in enumerate(subrow['cells']):
                ids = cell['source_word_ids']
                if (not isinstance(ids, list) or any(type(i) is not int or i not in words for i in ids)
                        or len(ids) != len(set(ids)) or not isinstance(cell['text'], str)):
                    raise ValueError('Invalid reviewed split word occurrences')
                selected = [words[i] for i in ids]
                x0, x1 = grid['x_edges'][column:column + 2]
                y0, y1 = grid['y_edges'][r:r + 2]
                if any(not (x0 <= (w['bbox'][0] + w['bbox'][2]) / 2 <= x1
                            and y0 <= w['bbox'][1] <= w['bbox'][3] <= y1) for w in selected):
                    raise ValueError('Reviewed split word belongs to a different physical cell band')
                lines = _lines(selected) if selected else []
                if lines is None:
                    raise ValueError('Ambiguous reviewed split source order')
                ordered = [w for line in lines for w in line]
                literal = '\n'.join(' '.join(w['text'] for w in line) for line in lines)
                if [w['id'] for w in ordered] != ids or _text(literal) != _text(cell['text']):
                    raise ValueError('Reviewed split wording or source order differs')
                parts = [{'word_id': w['id'], 'start': 0, 'end': len(w['text']),
                          'text': w['text'], 'bbox': w['bbox']} for w in ordered]
                observed.update((p['word_id'], i) for p in parts for i in range(p['start'], p['end']))
                row_words.extend(ordered)
                cells.append({'column': column, 'text': literal, 'source_fragments': parts,
                              'method': 'explicit_source_row_split', 'source_review': review['source_review']})
            if not row_words or min(w['bbox'][1] for w in row_words) < previous_bottom:
                raise ValueError('Reviewed split rows overlap, reverse order or contain no source text')
            previous_bottom = max(w['bbox'][3] for w in row_words)
            split.append({'cells': cells})
        if observed != expected or any(count != 1 for count in observed.values()):
            raise ValueError('Reviewed row split loses, duplicates or borrows source characters')
        expanded[r] = split
    if expanded:
        result = []
        for r, row in enumerate(rows):
            for replacement in expanded.get(r, [row]):
                result.append({**replacement, 'row': len(result), 'source_row': r})
        rows = result
    return deepcopy(rows)


def reviewed_table_record(table: dict, page: dict, source: dict, case: dict, review_method: str) -> dict:
    """Bind a passed complete-table annotation to both exact stored page views.

    Receipts carry the annotation, not another copy of the extracted table.
    Readers recheck it against the individually verified native/structured pages.
    Call only after the complete physical-table benchmark has passed.
    """
    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                         separators=(',', ':')).encode('utf-8')).hexdigest()
    reviewed_logical_rows(table, source, case)
    return {'schema_version': 'annotated-table-view-1', 'review_id': case['id'],
            'page': page['page'], 'table_id': table['id'],
            'native_page_sha256': digest(source),
            'structure_page_sha256': digest({'type': 'structured_page', **page}),
            'physical_rows': deepcopy(case['rows']), 'merged_spans': deepcopy(case['spans']),
            'absent_slots': deepcopy(case.get('absent_slots', [])),
            'logical_rows': deepcopy(case.get('logical_rows', [])),
            **({'row_splits': deepcopy(case['row_splits'])} if 'row_splits' in case else {}),
            **({'numbered_rows': deepcopy(case['numbered_rows'])} if 'numbered_rows' in case else {}),
            'source_context': deepcopy(case.get('source_text_regions', [])),
            'source_review': case.get('source_review') or review_method,
            'scope': 'named_table_transcription', 'financial_series_interpretation': 'not_performed'}
