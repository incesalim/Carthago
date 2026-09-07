"""Read printed period headings by source position without changing cells.

A PDF can omit the vertical rules through its header. Keep the resulting
physical merged cell, and separately associate its words with witnessed body
columns. Missing headings never acquire dates from another page here.
"""
from __future__ import annotations

from collections import Counter
import re

from .document_cell_fragments import cell_word_fragments, verify_cell_fragments
from .document_table_context import _grid
from .document_table_rows import _lines

VERSION = 'source-period-headers-1'
_PERIOD = re.compile(r'\b(?:cari\s+dönem|önceki\s+dönem|current\s+period|prior\s+period|previous\s+period)\b', re.I)


def _bounds(items):
    return [min(w['bbox'][0] for w in items), min(w['bbox'][1] for w in items),
            max(w['bbox'][2] for w in items), max(w['bbox'][3] for w in items)]


def _row_projection(table, row, grid, words):
    parts = [part for cell in row['cells'] for part in cell_word_fragments(cell, words)]
    occurrences = Counter((p['word_id'], i) for p in parts for i in range(p['start'], p['end']))
    band_box = [grid['x_edges'][0], grid['y_edges'][row['index']],
                grid['x_edges'][-1], grid['y_edges'][row['index'] + 1]]
    expected = Counter((w['id'], i) for w in words.values()
                       if band_box[0] <= (w['bbox'][0] + w['bbox'][2]) / 2 <= band_box[2]
                       and band_box[1] <= (w['bbox'][1] + w['bbox'][3]) / 2 <= band_box[3]
                       for i in range(len(w['text'])))
    if not parts or occurrences != expected:
        return None
    columns = [[] for _ in range(table['n_cols'])]
    for part in parts:
        box = part['bbox']
        matched = [c for c in range(table['n_cols'])
                   if grid['x_edges'][c] - .75 <= box[0] and box[2] <= grid['x_edges'][c + 1] + .75]
        if len(matched) != 1:
            return None
        columns[matched[0]].append({**part, 'id': (part['word_id'], part['start'], part['end'])})
    result = []
    for c, items in enumerate(columns):
        lines = _lines(items) if items else []
        if lines is None:
            return None
        ordered = [w for line in lines for w in line]
        result.append({'column': c, 'text': '\n'.join(' '.join(w['text'] for w in line) for line in lines),
                       'bbox': _bounds(items) if items else None,
                       'source_fragments': [{k: v for k, v in w.items() if k != 'id'} for w in ordered]})
    # A title or a first data row must not become a period header. Every amount
    # column needs its own explicit printed period phrase, with distinct text.
    labels = [' '.join(c['text'].split()) for c in result[1:]]
    if not all(_PERIOD.search(label) for label in labels) or len(set(labels)) != len(labels):
        return None
    return {'source_row': row['index'], 'columns': result,
            'x_edges': grid['x_edges'], 'bbox': band_box,
            'physical_cells_unchanged': True, 'semantic_verification': 'not_performed'}


def table_period_headers(page, source):
    """Return only source-backed bands, retaining competing bands explicitly."""
    words = {w['id']: w for w in source['words']}
    tables = []
    for table in page['tables']:
        if table['method'] != 'pymupdf_lines_strict' or table['n_cols'] < 3:
            continue
        grid = _grid(table)
        if grid is None or verify_cell_fragments(table, source):
            continue
        bands = []
        for row in table['rows'][:3]:
            if any(not cell['source_text_matches'] or any(i not in words for i in cell['word_ids'])
                   for cell in row['cells']):
                continue
            anchors = [a for a in grid['anchors'] if a['row'] == row['index']]
            if any(a['row_span'] != 1 for a in anchors):
                continue
            projected = _row_projection(table, row, grid, words)
            if projected:
                bands.append(projected)
        if bands:
            tables.append({'table_id': table['id'], 'status': 'unique_printed_band' if len(bands) == 1 else 'competing_printed_bands',
                           'bands': bands, 'method': 'source_words_on_witnessed_body_columns',
                           'semantic_verification': 'not_performed'})
    return {'schema_version': VERSION, 'tables': tables, 'semantic_verification': 'not_performed'}


def add_period_headers(structure, evidence):
    structure['table_period_headers_schema'] = VERSION
    for page, source in zip(structure['pages'], evidence[1:], strict=True):
        page['table_period_headers'] = table_period_headers(page, source)


def verify_period_headers(structure, evidence):
    from .document_header_upgrade import TARGET_ENGINE
    present = any('table_period_headers' in page for page in structure['pages'])
    if not present and 'table_period_headers_schema' not in structure:
        return ['missing_period_header_view'] if structure.get('engine') == TARGET_ENGINE else []
    errors = []
    if structure.get('table_period_headers_schema') != VERSION:
        errors.append('table_period_headers_schema_mismatch')
    for page, source in zip(structure['pages'], evidence[1:]):
        if page.get('table_period_headers') != table_period_headers(page, source):
            errors.append(f"page_{page['page']}:table_period_headers_mismatch")
    return errors
