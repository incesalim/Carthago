"""Isolate table grids so distant rows cannot drag their column boundaries.

PyMuPDF snaps line coordinates across its search region. Separate tables on a
page can therefore move each other's borders even when their rows never touch.
A bounded second observation may replace a grid only when exactly one table
retains the complete same native word region and all its source characters.
"""
from __future__ import annotations

from collections import Counter

import fitz

from .document_evidence import text_characters


def _inside(box, region):
    return (region[0] <= (box[0] + box[2]) / 2 <= region[2]
            and region[1] <= (box[1] + box[3]) / 2 <= region[3])


def refine_ruled_regions(page, source, tables, paths, virtual_rules, serialize):
    """Use the existing detector in one source region, without accepting loss.

Three points is the detector's normal snapping/intersection tolerance. Include
that margin to retain the original outer rules, but never intersect another
detected table. Competing grids, changed word regions and missing/repeated
characters retain the original candidate for review.
"""
    result = []
    for table in tables:
        bounds = fitz.Rect(table['bbox'])
        clip = (bounds + (-3, -3, 3, 3)) & page.rect
        if any(other['id'] != table['id'] and fitz.Rect(other['bbox']).intersects(clip)
               for other in tables):
            result.append(table)
            continue
        expected_words = [w for w in source['words'] if _inside(w['bbox'], bounds)]
        if not expected_words:
            result.append(table)
            continue
        found = page.find_tables(strategy='lines_strict', paths=paths,
                                 add_lines=virtual_rules or None, clip=clip).tables
        if len(found) != 1:
            result.append(table)
            continue
        observed = serialize(found[0], table['id'])
        actual_words = [w for w in source['words'] if _inside(w['bbox'], observed['bbox'])]
        expected = Counter(w['id'] for w in expected_words)
        characters = text_characters(''.join(w['text'] for w in expected_words))
        extracted = text_characters(''.join(c['text'] or '' for r in observed['rows'] for c in r['cells']))
        if Counter(w['id'] for w in actual_words) != expected or extracted != characters:
            result.append(table)
            continue
        if observed != table:
            observed['region_refinement'] = {
                'method': 'isolated_source_region-1', 'clip': list(clip),
                'initial_bbox': table['bbox'], 'initial_row_count': table['row_count'],
                'initial_column_count': table['n_cols'],
                'source_word_ids': [w['id'] for w in expected_words],
                'semantic_verification': 'not_performed',
            }
        result.append(observed)
    return result


def verify_region_refinement(table, source):
    """Check retained region/occurrence provenance; PDF readback checks the grid."""
    record = table.get('region_refinement')
    if record is None:
        return []
    try:
        bounds = fitz.Rect(record['initial_bbox'])
        clip = list((bounds + (-3, -3, 3, 3)) & fitz.Rect(0, 0, source['width'], source['height']))
        before = [w for w in source['words'] if _inside(w['bbox'], bounds)]
        after = [w for w in source['words'] if _inside(w['bbox'], table['bbox'])]
        characters = text_characters(''.join(w['text'] for w in before))
        extracted = text_characters(''.join(c['text'] or '' for r in table['rows'] for c in r['cells']))
        valid = (record['method'] == 'isolated_source_region-1'
                 and record['semantic_verification'] == 'not_performed'
                 and record['clip'] == clip and fitz.Rect(clip).contains(table['bbox'])
                 and record['source_word_ids'] == [w['id'] for w in before]
                 and [w['id'] for w in before] == [w['id'] for w in after]
                 and bool(before) and characters == extracted
                 and type(record['initial_row_count']) is int and record['initial_row_count'] > 0
                 and type(record['initial_column_count']) is int and record['initial_column_count'] > 0)
    except (KeyError, TypeError, ValueError):
        valid = False
    return [] if valid else ['table_region_source_mismatch']
