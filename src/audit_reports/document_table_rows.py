"""Expose source lines inside tall ruled cells without parsing their figures.

Some PDFs draw only the table's column borders: one physical row then contains
an entire statement. Keep that original grid and provide a separate line view.
Wrapped labels remain separate source lines; this does not certify logical rows.
"""
from __future__ import annotations

from collections import Counter
from statistics import median

from .document_table_context import _grid


def _inside(box, region):
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return region[0] <= x <= region[2] and region[1] <= y <= region[3]


def _lines(words):
    """Cluster baseline bands, keeping close or overlapping lines ambiguous."""
    result = []
    for word in sorted(words, key=lambda w: ((w['bbox'][1] + w['bbox'][3]) / 2, w['bbox'][0], w['id'])):
        center = (word['bbox'][1] + word['bbox'][3]) / 2
        height = word['bbox'][3] - word['bbox'][1]
        matches = [line for line in result if abs(center - median(
            (w['bbox'][1] + w['bbox'][3]) / 2 for w in line)) <= .3 * min(
                [height, *(w['bbox'][3] - w['bbox'][1] for w in line)])]
        if len(matches) > 1:
            return None
        if matches:
            matches[0].append(word)
        else:
            result.append([word])
    for line in result:
        line.sort(key=lambda w: (w['bbox'][0], w['bbox'][1], w['id']))
    # Overlapping baseline bands cannot safely supply a row boundary.
    if any(max(w['bbox'][3] for w in a) > min(w['bbox'][1] for w in b)
           for a, b in zip(result, result[1:])):
        return None
    return result


def _project_columns(row, table, grid, source, by_id):
    """Separate merged body columns only with header and printed-rule witnesses.

    This is a separate geometric projection; the physical cell grid remains
    unchanged. A rule must cover 95% of the body, with gaps no taller than 2.5
    median glyph heights. Every word must fit exactly one projected column.
    """
    anchors = [a for a in grid['anchors'] if a['row'] == row['index']]
    if any(a['row_span'] != 1 for a in anchors):
        return None
    boundaries = sorted(c for a in anchors for c in range(a['column'] + 1, a['column'] + a['column_span']))
    if not boundaries:
        return None
    headers = []
    for header in table['rows'][:row['index']]:
        slots = [a for a in grid['anchors'] if a['row'] == header['index']]
        if (len(slots) == table['n_cols'] and all(a['row_span'] == a['column_span'] == 1 for a in slots)
                and all(header['cells'][c - 1]['word_ids'] and header['cells'][c]['word_ids'] for c in boundaries)):
            headers.append(header)
    if not headers:
        return None
    header = headers[-1]
    top, bottom = grid['y_edges'][row['index']:row['index'] + 2]
    if bottom - top < 4 * (grid['y_edges'][header['index'] + 1] - grid['y_edges'][header['index']]):
        return None
    refs = [i for c in row['cells'] for i in c['word_ids']]
    if not refs:
        return None
    max_gap = 2.5 * median(by_id[i]['bbox'][3] - by_id[i]['bbox'][1] for i in refs)
    witnesses = []
    for c in boundaries:
        x = grid['x_edges'][c]
        rules = [d for d in source['drawings'] if d['path_items'] == 1 and d['type'] in ('f', 's', 'fs')
                 and d['bbox'][2] - d['bbox'][0] <= .8
                 and abs((d['bbox'][0] + d['bbox'][2]) / 2 - x) <= .5
                 and min(bottom, d['bbox'][3]) > max(top, d['bbox'][1])]
        intervals = sorted((max(top, d['bbox'][1]), min(bottom, d['bbox'][3])) for d in rules)
        end, coverage, gaps = top, 0, []
        for start, stop in intervals:
            if start > end:
                gaps.append(start - end)
            coverage += max(0, stop - max(start, end))
            end = max(end, stop)
        gaps.append(bottom - end)
        if coverage < .95 * (bottom - top) or max(gaps) > max_gap:
            return None
        witnesses.append({'column_boundary': c, 'x': x, 'source_drawing_ids': sorted(d['id'] for d in rules),
                          'covered_height': round(coverage, 4), 'maximum_gap': round(max(gaps), 4)})
    columns = {}
    for i in refs:
        box = by_id[i]['bbox']
        matches = [c for c in range(table['n_cols'])
                   if box[0] >= grid['x_edges'][c] - .75 and box[2] <= grid['x_edges'][c + 1] + .75]
        if len(matches) != 1:
            return None
        columns[i] = matches[0]
    return columns, {'method': 'header_grid_and_retained_vertical_rules', 'header_row': header['index'],
                     'rule_witnesses': witnesses, 'physical_cells_unchanged': True,
                     'semantic_verification': 'not_performed'}


def _row_bands(table, grid):
    """Keep rows touched by a vertical cell span together in the line view."""
    ends = list(range(1, len(table['rows']) + 1))
    for anchor in grid['anchors']:
        ends[anchor['row']] = max(ends[anchor['row']], anchor['row'] + anchor['row_span'])
    start = 0
    while start < len(ends):
        stop = ends[start]
        for index in range(start + 1, len(ends)):
            if index >= stop:
                break
            stop = max(stop, ends[index])
        yield table['rows'][start:stop]
        start = stop


def table_source_rows(page: dict, source: dict) -> dict:
    results = []
    for table in page['tables']:
        grid = _grid(table)
        if grid is None:
            continue
        words = [w for w in source['words'] if _inside(w['bbox'], table['bbox'])]
        by_id = {w['id']: w for w in words}
        cells = [c for r in table['rows'] for c in r['cells']]
        if (len(by_id) != len(words)
                or Counter(i for c in cells for i in c['word_ids']) != Counter(by_id.keys())
                or any(not c['source_text_matches'] or any(not _inside(by_id[i]['bbox'], c['bbox'])
                       for i in c['word_ids']) for c in cells)):
            continue
        split = []
        for band in _row_bands(table, grid):
            row = band[0]
            row_ids = [r['index'] for r in band]
            anchors = [a for a in grid['anchors'] if a['row'] in row_ids]
            band_cells = [c for r in band for c in r['cells']]
            refs = [i for c in band_cells for i in c['word_ids']]
            lines = _lines([by_id[i] for i in refs])
            if lines is None or len(lines) < 8:
                continue
            projection = None
            row_group = None
            if len(band) > 1:
                if any(a['column_span'] != 1 for a in anchors):
                    continue
                columns = {i: c['column'] for c in band_cells for i in c['word_ids']}
                # A spanning cell supplies its actual column, not a guessed
                # assignment across a border. Reject words crossing that column.
                if any(by_id[i]['bbox'][0] < grid['x_edges'][c] - .75
                       or by_id[i]['bbox'][2] > grid['x_edges'][c + 1] + .75 for i, c in columns.items()):
                    continue
                row_group = {'method': 'source_words_in_vertical_cell_spans', 'source_rows': row_ids,
                             'spanning_cells': [a for a in anchors if a['row_span'] > 1],
                             'physical_cells_unchanged': True, 'semantic_verification': 'not_performed'}
            elif (len(anchors) == table['n_cols']
                    and all(a['row_span'] == a['column_span'] == 1 for a in anchors)):
                columns = {i: c['column'] for c in row['cells'] for i in c['word_ids']}
            else:
                projected = _project_columns(row, table, grid, source, by_id)
                if projected is None:
                    continue
                columns, projection = projected
            if sum(len({columns[w['id']] for w in line} - {0}) >= 2 for line in lines) < 4:
                continue
            rendered = []
            for index, line in enumerate(lines):
                top, bottom = min(w['bbox'][1] for w in line), max(w['bbox'][3] for w in line)
                rendered.append({'index': index, 'bbox': [table['bbox'][0], top, table['bbox'][2], bottom],
                    'cells': [{'column': c, 'text': ' '.join(w['text'] for w in line if columns[w['id']] == c),
                               'word_ids': [w['id'] for w in line if columns[w['id']] == c],
                               'bbox': [grid['x_edges'][c], top, grid['x_edges'][c + 1], bottom]}
                              for c in range(table['n_cols'])]})
            split.append({'source_row': row['index'], 'lines': rendered,
                          **({'row_group': row_group} if row_group is not None else {}),
                          **({'column_projection': projection} if projection is not None else {})})
        if split:
            results.append({'table_id': table['id'], 'split_rows': split})
    projected = any('column_projection' in row for result in results for row in result['split_rows'])
    return {'schema_version': 'ruled-source-lines-1', 'tables': results,
            'method': 'source_words_in_rule_supported_columns' if projected else 'source_words_within_original_ruled_columns',
            'logical_rows_verified': False, 'semantic_verification': 'not_performed'}


def verify_table_source_rows(page: dict, source: dict) -> list[str]:
    if 'table_source_rows' not in page:
        return []
    return [] if page['table_source_rows'] == table_source_rows(page, source) else ['table_source_rows_mismatch']
