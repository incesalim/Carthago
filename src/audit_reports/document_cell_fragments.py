"""Character occurrence links for words crossing a ruled table's cell borders.

The grid is still a candidate. Exact source links do not certify that splitting
a word at that grid border is semantically correct. Keep that observation beside
the cells, including cases where the PDF paints a letter over a table rule.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

import fitz

from .document_evidence import text_characters


def _box(bbox, matrix):
    return [round(v, 4) for v in fitz.Rect(bbox) * matrix]


def _inside(box, region):
    return (region[0] <= (box[0] + box[2]) / 2 <= region[2]
            and region[1] <= (box[1] + box[3]) / 2 <= region[3])


def _bounds(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _literal(text):
    return ''.join(c for c in text or '' if not c.isspace())


def word_character_geometry(page, source, word_ids):
    """Observe actual glyph boxes, requiring an exact retained word occurrence.

    ActualText replacement positions need their own existing view. They cannot
    be inferred from the literal glyph geometry used for ordinary text here.
    """
    if source.get('actualtext_changes_word_view'):
        return []
    raw = page.get_text('rawdict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES,
                        clip=fitz.INFINITE_RECT())
    lines = defaultdict(list)
    for b, block in enumerate(raw['blocks']):
        if block['type'] != 0:
            continue
        for line_number, line in enumerate(block['lines']):
            for span in line['spans']:
                for char in span['chars']:
                    if not char['c'].isspace():
                        lines[b, line_number].append({'text': char['c'],
                                                     'bbox': _box(char['bbox'], page.rotation_matrix)})
    result = []
    for word in source['words']:
        if word['id'] not in word_ids:
            continue
        selected = [c for c in lines[word['block'], word['line']] if _inside(c['bbox'], word['bbox'])]
        if ''.join(c['text'] for c in selected) != word['text']:
            continue
        offset, characters = 0, []
        for char in selected:
            characters.append({'start': offset, 'end': offset + len(char['text']), **char})
            offset += len(char['text'])
        result.append({'word_id': word['id'], 'characters': characters})
    return result


def link_cell_fragments(table, source, geometry):
    """Return an exact character-linked copy, or the unchanged candidate.

    Every affected cell must match its source characters in order. Missing,
    overlapping or competing occurrences abstain together, never partially move
    a word into one cell while leaving the old whole word in its neighbour.
    """
    cells = {(c['row'], c['column']): c for r in table['rows'] for c in r['cells'] if c['bbox']}
    words = {w['id']: w for w in source['words']}
    split, accepted_geometry = {}, []
    for observed in geometry:
        word = words.get(observed['word_id'])
        if word is None:
            continue
        box = word['bbox']
        possible = [c for c in cells.values() if min(box[2], c['bbox'][2]) > max(box[0], c['bbox'][0])
                    and min(box[3], c['bbox'][3]) > max(box[1], c['bbox'][1])]
        if len(possible) < 2:
            continue
        chars = observed['characters']
        if (not chars or ''.join(c['text'] for c in chars) != word['text']
                or [(c['start'], c['end']) for c in chars] !=
                [(sum(len(x['text']) for x in chars[:i]), sum(len(x['text']) for x in chars[:i+1]))
                 for i in range(len(chars))]
                or any(not _inside(c['bbox'], word['bbox']) for c in chars)):
            continue
        owners = [[position for position, cell in cells.items() if _inside(c['bbox'], cell['bbox'])]
                  for c in chars]
        if any(len(v) != 1 for v in owners) or len({v[0] for v in owners}) < 2:
            continue
        pieces = []
        for char, (owner,) in zip(chars, owners, strict=True):
            if pieces and pieces[-1]['cell'] == owner:
                pieces[-1]['end'] = char['end']
                pieces[-1]['text'] += char['text']
                pieces[-1]['boxes'].append(char['bbox'])
            else:
                pieces.append({'cell': owner, 'word_id': word['id'], 'start': char['start'],
                               'end': char['end'], 'text': char['text'], 'boxes': [char['bbox']]})
        if len(pieces) != len({p['cell'] for p in pieces}):
            continue
        split[word['id']] = [{**{k: v for k, v in p.items() if k != 'boxes'}, 'bbox': _bounds(p['boxes'])}
                             for p in pieces]
        accepted_geometry.append(observed)
    if not split:
        return table
    affected = {p['cell'] for pieces in split.values() for p in pieces}
    # Also include the old owner so its whole-word reference cannot survive.
    affected.update(position for position, cell in cells.items() if set(cell['word_ids']) & split.keys())
    fragments = defaultdict(list)
    for word in source['words']:
        if word['id'] in split:
            for piece in split[word['id']]:
                fragments[piece['cell']].append({k: v for k, v in piece.items() if k != 'cell'})
        else:
            owners = [position for position in affected if _inside(word['bbox'], cells[position]['bbox'])]
            if len(owners) > 1:
                return table
            for position in owners:
                fragments[position].append({'word_id': word['id'], 'start': 0, 'end': len(word['text']),
                                            'text': word['text'], 'bbox': word['bbox']})
    if any(_literal(''.join(p['text'] for p in fragments[position])) != _literal(cells[position]['text'])
           for position in affected):
        return table
    result = deepcopy(table)
    for row in result['rows']:
        for cell in row['cells']:
            position = cell['row'], cell['column']
            if position in affected:
                cell['source_fragments'] = fragments[position]
                cell['word_ids'] = list(dict.fromkeys(p['word_id'] for p in fragments[position]))
                cell['source_text_matches'] = True
    result['word_fragment_geometry'] = accepted_geometry
    result['word_boundary_observations'] = [
        {'word_id': word_id, 'text': words[word_id]['text'], 'review_status': 'unreviewed',
         'cells': [{'row': p['cell'][0], 'column': p['cell'][1], 'start': p['start'], 'end': p['end']}
                   for p in pieces]}
        for word_id, pieces in split.items()]
    return result


def cell_word_fragments(cell, words):
    """Uniform occurrence references; full words retain their existing geometry."""
    if 'source_fragments' in cell:
        return cell['source_fragments']
    return [{'word_id': i, 'start': 0, 'end': len(words[i]['text']),
             'text': words[i]['text'], 'bbox': words[i]['bbox']} for i in cell['word_ids']]


def verify_cell_fragments(table, source):
    """Recompute links from retained character observations and parent words.

    Original-PDF readback must separately verify the observed glyph boxes.
    This check does not turn stored geometry into independent source evidence.
    """
    if 'word_fragment_geometry' not in table:
        missing = ('word_boundary_observations' in table
                   or any('source_fragments' in c for r in table['rows'] for c in r['cells']))
        return ['missing_word_fragment_geometry'] if missing else []
    words = {w['id']: w for w in source['words']}
    original = deepcopy(table)
    original.pop('word_fragment_geometry', None)
    original.pop('word_boundary_observations', None)
    for row in original['rows']:
        for cell in row['cells']:
            cell.pop('source_fragments', None)
            refs = [w for w in words.values() if cell['bbox'] and _inside(w['bbox'], cell['bbox'])]
            cell['word_ids'] = [w['id'] for w in refs]
            cell['source_text_matches'] = text_characters(''.join(w['text'] for w in refs)) == text_characters(
                cell['text'] or '')
    expected = link_cell_fragments(original, source, table['word_fragment_geometry'])
    return [] if expected == table else ['cell_fragment_reconstruction_mismatch']
