"""Assemble candidate numbered rows from retained, rule-supported source lines.

Identifiers stay literal: no renumbering, numeric conversion or note parsing.
Only an unfinished numbered row may absorb an aligned continuation. Ambiguous
lines remain explicit and prevent the result being accepted as a reviewed grid.
"""
from __future__ import annotations

from collections import Counter
import re

from .document_cell_fragments import cell_word_fragments
from .document_table_rows import table_source_rows

_IDENTIFIER = re.compile(r'^(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.?|[A-Z]\.)\s+')


def numbered_source_rows(page: dict, source: dict) -> dict:
    """Return source-linked grouping candidates without modifying either input."""
    projected = table_source_rows(page, source)
    words = {w['id']: w for w in source['words']}
    results = []
    for table in projected['tables']:
        for split in table['split_rows']:
            lines = split['lines']
            # The identifier and two regularly occupied columns are witnesses,
            # not a financial interpretation of any column's contents.
            coded = [line for line in lines if _IDENTIFIER.match(line['cells'][0]['text'])]
            if len(coded) < 4 or len(coded) < len(lines) / 2:
                continue
            counts = Counter(c['column'] for line in lines for c in line['cells'][1:] if c['text'].strip())
            if not counts:
                continue
            witnesses = sorted(c for c, count in counts.items() if count >= .9 * max(counts.values()))
            if len(witnesses) < 2:
                continue
            groups, unresolved = [], []
            for line in lines:
                text = line['cells'][0]['text']
                parts = cell_word_fragments(line['cells'][0], words)
                match = _IDENTIFIER.match(text)
                complete = all(line['cells'][c]['text'].strip() for c in witnesses)
                if match:
                    groups.append({'lines': [line], 'identifier': match[0].strip(),
                                   'complete': complete, 'label_x': parts[1]['bbox'][0] if len(parts) > 1 else None})
                    continue
                previous = groups[-1] if groups else None
                aligned = (previous is not None and previous['identifier'] is not None
                           and previous['label_x'] is not None and parts
                           and abs(parts[0]['bbox'][0] - previous['label_x']) <= 1)
                if previous and not previous['complete'] and aligned:
                    before = previous['lines'][-1]['bbox']
                    height = max(line['bbox'][3] - line['bbox'][1], before[3] - before[1])
                    if 0 <= line['bbox'][1] - before[3] <= 2 * height:
                        previous['lines'].append(line)
                        previous['complete'] = complete
                        continue
                if not complete or not text.strip():
                    unresolved.append(line['index'])
                groups.append({'lines': [line], 'identifier': None, 'complete': complete, 'label_x': None})
            rows = []
            for group in groups:
                selected = group['lines']
                cells = []
                for column in range(len(lines[0]['cells'])):
                    fragments = [p for line in selected for p in cell_word_fragments(line['cells'][column], words)]
                    cells.append({'column': column,
                                  'text': '\n'.join(line['cells'][column]['text'] for line in selected if line['cells'][column]['text']),
                                  'source_fragments': fragments})
                rows.append({'source_line_indices': [line['index'] for line in selected],
                             'identifier': group['identifier'], 'cells': cells})
            def inventory(cells):
                return Counter((p['word_id'], i) for c in cells for p in c['source_fragments']
                               for i in range(p['start'], p['end']))
            original = [{'source_fragments': cell_word_fragments(c, words)} for line in lines for c in line['cells']]
            observed = inventory([c for row in rows for c in row['cells']])
            if observed != inventory(original) or any(count != 1 for count in observed.values()):
                raise ValueError('Numbered row grouping changed the source character inventory')
            results.append({'table_id': table['table_id'], 'source_row': split['source_row'],
                            'physical_source_rows': split.get('row_group', {}).get('source_rows', [split['source_row']]),
                            'witness_columns': witnesses, 'unresolved_lines': unresolved, 'rows': rows})
    return {'schema_version': 'numbered-source-rows-1', 'tables': results,
            'method': 'literal_identifiers_and_aligned_source_lines',
            'logical_rows_verified': False, 'semantic_verification': 'not_performed'}
