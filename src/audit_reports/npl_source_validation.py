"""Source-cell constraints for both periods of complete NPL movement tables."""
import json
import re

from .extractor import parse_amount
from .npl_disclosure import disclosure_lines
from .npl_movement import _OUTFLOW_KEYS, _match_row_label


def _require(condition):
    if not condition:
        raise ValueError('Invalid NPL source reference')


def check_source_cells(rows, source_lines, scale):
    from .validator import ValidationResult

    res = ValidationResult()
    pages = {}
    for line in source_lines:
        pages.setdefault(line['source_page'], []).append(line['line_text'])
    selected = disclosure_lines(pages)
    if selected is None:
        res.add_skip()
        return res
    if not any(line.get('cell_sources_json') for line in source_lines):
        res.add_fail('npl_source_cells_missing', 'native cell evidence missing for bounded disclosure', 1, 0)
        return res
    if scale is None:
        res.add_fail('npl_source_unit', 'unknown source denomination', 1, 0)
        return res
    originals = {(line['source_page'], line['line_order']): line['line_text'].split()
                 for line in source_lines}
    original_text = {(line['source_page'], line['line_order']): line['line_text'] for line in source_lines}
    stored = {(row['period_type'], row['group_code']): row for row in rows}
    printed, categories = {}, {}
    period_type = None
    for line in source_lines:
        page, order = line['source_page'], line['line_order']
        if (page, order) not in selected:
            continue
        text = line['line_text']
        if not line.get('is_data_row'):
            caption = re.match(r'^(current|prior|cari|önceki)\s+(?:period|dönem)\b', text, re.I)
            if caption:
                period_type = 'prior' if caption[1].lower() in {'prior', 'önceki'} else 'current'
            continue
        node = f'{period_type} p.{page} line {order}'
        try:
            data = json.loads(line.get('cell_sources_json') or 'null')
            cells = data['cells']
            _require(data['period_type'] == period_type and period_type in {'current', 'prior'})
            _require([c['group_code'] for c in cells] == ['III', 'IV', 'V'])
            key, parent = data['row_key'], data['parent_key']
            _require(key == _match_row_label(text) or key is None and parent)
            _require(key is not None or parent is not None)
            used = set()
            for cell in cells:
                refs = cell['fragments']
                _require(refs and cell['text'] == ''.join(r['text'] for r in refs))
                for ref in refs:
                    address = (ref['line_order'], ref['token_order'])
                    _require(address not in used)
                    used.add(address)
                    _require(originals[page, ref['line_order']][ref['token_order']] == ref['text'])
                    _require(abs(ref['line_order'] - order) <= 2)
                _require(parse_amount(cell['text']) is not None)
            # Every trailing printed amount must have a reference; a wider
            # unsupported table cannot silently lose a column and certify three.
            tokens = originals[page, order]
            for token_order in range(len(tokens) - 1, -1, -1):
                if parse_amount(tokens[token_order]) is None:
                    break
                _require((order, token_order) in used)
            for link in data.get('note_links', []):
                for target in link['targets']:
                    refs = target['source_lines']
                    _require(refs and target['text'] == '\n'.join(r['text'] for r in refs))
                    _require(all(original_text[r['source_page'], r['line_order']] == r['text'] for r in refs))
        except (KeyError, TypeError, IndexError, ValueError):
            res.add_fail('npl_source_cell_reference', node, 1, 0)
            continue
        for cell in cells:
            group = cell['group_code']
            amount = parse_amount(cell['text'])
            if key is None:
                categories.setdefault((period_type, group, parent), []).append(amount)
                continue
            canonical = abs(amount) if key in _OUTFLOW_KEYS or key == 'provision' else amount
            facts = printed.setdefault((period_type, group), {})
            if key in facts:
                res.add_fail('npl_source_duplicate', f'{node}/{group}/{key}', 1, 2)
                continue
            facts[key] = canonical
            row = stored.get((period_type, group))
            actual = row.get(key) if row else None
            if actual is None:
                res.add_fail('npl_source_cell_missing', f'{node}/{group}/{key}', 1, 0)
            elif abs(actual - canonical * scale) > 0.000001:
                res.add_fail('npl_source_cell', f'{node}/{group}/{key}', canonical * scale, actual)
            else:
                res.add_pass()
    for (period, group, parent), amounts in categories.items():
        expected = printed.get((period, group), {}).get(parent)
        actual = sum(amounts)
        if expected is None or abs(abs(expected) - actual) > 1.5:
            res.add_fail('npl_source_categories', f'{period}/{group}/{parent}', expected or 0, actual)
        else:
            res.add_pass()
    flows = ('additions', 'transfers_in', 'transfers_out', 'collections', 'write_offs',
             'sold', 'fx_diff', 'accrual_movement', 'other_movement')
    for (period, group), facts in printed.items():
        if 'opening_balance' not in facts or 'closing_balance' not in facts:
            res.add_fail('npl_source_balances', f'{period}/{group}', 2,
                         sum(k in facts for k in ('opening_balance', 'closing_balance')))
            continue
        implied = facts['opening_balance'] + sum(
            -abs(facts.get(k, 0)) if k in _OUTFLOW_KEYS else facts.get(k, 0) for k in flows)
        if abs(implied - facts['closing_balance']) > 5:
            res.add_fail('npl_source_movement', f'{period}/{group}', facts['closing_balance'], implied)
        else:
            res.add_pass()
    return res
