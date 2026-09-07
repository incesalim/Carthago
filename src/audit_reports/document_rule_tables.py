"""Conservative table candidates from printed rules, preserving source words.

Complex logo paths must not participate in global grid snapping. Separately,
cell-width underline segments can reveal a one-row table with no vertical rules.
Both interpretations remain unreviewed and retain the actual rule references.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

import fitz

from .document_table_rows import _lines


def grid_paths(paths: list[dict]) -> list[dict]:
    result = []
    for path in paths:
        usable = True
        for item in path["items"]:
            if item[0] == "re":
                rect = fitz.Rect(item[1])
                # Filled shading and logo polygons are not cell boundaries.
                usable &= path["type"] != "f" or min(rect.width, rect.height) <= 2
            elif item[0] == "l":
                a, b = item[1:3]
                usable &= abs(a.x - b.x) < .1 or abs(a.y - b.y) < .1
            else:
                usable = False
        if usable:
            result.append(path)
    return result


def _text(words: list[dict]) -> str:
    lines = defaultdict(list)
    for word in words:
        lines[word["block"], word["line"]].append(word)
    return "\n".join(" ".join(w["text"] for w in sorted(line, key=lambda w: w["word"]))
                     for line in lines.values())


def underline_candidates(source: dict, existing: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for drawing in source["drawings"]:
        x0, y0, x1, y1 = drawing["bbox"]
        if x1 - x0 >= 8 and y1 - y0 <= 2:
            groups[round((y0 + y1) / 2)].append(drawing)
    tables = []
    for bottom, segments in sorted(groups.items()):
        segments = sorted(segments, key=lambda d: d["bbox"][0])
        if len(segments) < 3:
            continue
        # These are adjacent cell-width rules, not unrelated short underlines.
        if any(abs(left["bbox"][2] - right["bbox"][0]) > 2
               for left, right in zip(segments, segments[1:])):
            continue
        x0, x1 = segments[0]["bbox"][0], segments[-1]["bbox"][2]
        tops = []
        for y, drawings in groups.items():
            if not 6 <= bottom - y <= 40:
                continue
            full = [d for d in drawings if abs(d["bbox"][0] - x0) <= 2 and abs(d["bbox"][2] - x1) <= 2]
            if len(full) == 1:
                tops.append((y, full))
                continue
            # Word-generated PDFs may serialize both borders as one segment
            # per cell. Require the same ordered column extents on both rules.
            ordered = sorted(drawings, key=lambda d: d['bbox'][0])
            if len(ordered) == len(segments) and all(
                    abs(a['bbox'][0] - b['bbox'][0]) <= 2 and abs(a['bbox'][2] - b['bbox'][2]) <= 2
                    for a, b in zip(ordered, segments, strict=True)):
                tops.append((y, ordered))
        if not tops:
            continue
        top, top_rules = max(tops, key=lambda entry: entry[0])
        center_y = (top + bottom) / 2
        if any(t.get("bbox") and t["bbox"][1] <= center_y <= t["bbox"][3]
               and t["bbox"][0] <= x0 + 3 and t["bbox"][2] >= x1 - 3 for t in existing):
            continue
        boundaries = [x0, *((a["bbox"][2] + b["bbox"][0]) / 2
                           for a, b in zip(segments, segments[1:])), x1]
        header_top = max(0, top - 2 * (bottom - top))
        rows = []
        for row_number, (y0, y1) in enumerate(((header_top, top), (top, bottom))):
            cells = []
            for column, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
                words = [w for w in source["words"] if left <= (w["bbox"][0] + w["bbox"][2]) / 2 < right
                         and y0 <= (w["bbox"][1] + w["bbox"][3]) / 2 < y1]
                cells.append({"row": row_number, "column": column, "bbox": [left, y0, right, y1],
                              "text": _text(words), "word_ids": [w["id"] for w in words],
                              "source_text_matches": True, "slot_status": "present"})
            rows.append({"index": row_number, "cells": cells,
                         "role": "possible_header" if row_number == 0 else "body",
                         "review_status": "unreviewed"})
        # A full-width sentence above a rule is not enough to propose a table.
        if sum(bool(c["word_ids"]) for c in rows[1]["cells"]) < 3:
            continue
        tables.append({"id": f"p{source['page']}:underline{len(tables)}", "kind": "table_candidate",
                       "method": "horizontal_rule_cells", "rows": rows, "row_count": 2,
                       "n_cols": len(segments), "bbox": [x0, header_top, x1, bottom],
                       "source_drawing_ids": [d['id'] for d in [*top_rules, *segments]],
                       "review_status": "unreviewed", "header_association_verified": False})
    tables.extend(_multiline_underlines(source, groups, existing + tables, len(tables)))
    return tables


def _multiline_underlines(source, groups, existing, offset):
    """Keep a long printed body band when repeated column rules and lines agree.

    This does not manufacture physical row borders. Logical line partitions are
    exposed separately by table_source_rows and still require source review.
    """
    result = []
    for bottom, drawings in sorted(groups.items()):
        segments = sorted(drawings, key=lambda d: d['bbox'][0])
        if len(segments) < 3 or any(abs(a['bbox'][2] - b['bbox'][0]) > 2
                                    for a, b in zip(segments, segments[1:])):
            continue
        x0, x1 = segments[0]['bbox'][0], segments[-1]['bbox'][2]
        matches = []
        for y, rules in groups.items():
            if bottom - y <= 40:
                continue  # Preserve the existing short-band interpretation.
            ordered = sorted(rules, key=lambda d: d['bbox'][0])
            if len(ordered) == len(segments) and all(
                    abs(a['bbox'][0] - b['bbox'][0]) <= 2 and abs(a['bbox'][2] - b['bbox'][2]) <= 2
                    for a, b in zip(ordered, segments, strict=True)):
                matches.append((y, ordered))
        if not matches:
            continue
        top, top_rules = max(matches, key=lambda entry: entry[0])
        if any(top < y < bottom and any(d['bbox'][0] >= x0 - 2 and d['bbox'][2] <= x1 + 2 for d in rules)
               for y, rules in groups.items()):
            continue  # Another printed band must not disappear into this one.
        edges = [x0, *((a['bbox'][2] + b['bbox'][0]) / 2 for a, b in zip(segments, segments[1:])), x1]

        def in_band(w, low, high):
            box = w['bbox']
            return x0 <= (box[0] + box[2]) / 2 < x1 and low <= (box[1] + box[3]) / 2 < high

        body = [w for w in source['words'] if in_band(w, top, bottom)]
        lines = _lines(body)
        if not lines or len(lines) < 3:
            continue
        height = median(w['bbox'][3] - w['bbox'][1] for w in body)
        if any(min(w['bbox'][1] for w in b) - max(w['bbox'][3] for w in a) > 2.5 * height
               for a, b in zip(lines, lines[1:])):
            continue
        preceding = _lines([w for w in source['words'] if in_band(w, max(0, top - 3 * height), top)])
        if not preceding:
            continue
        header = preceding[-1]
        if top - max(w['bbox'][3] for w in header) > height:
            continue
        if (len(preceding) > 1 and min(w['bbox'][1] for w in header)
                - max(w['bbox'][3] for w in preceding[-2]) < .75 * height):
            continue  # Do not take the last line of a compound header alone.
        header_top = min(w['bbox'][1] for w in header) - .25
        if any(t.get('method') != 'legacy_numeric_geometry' and t.get('bbox')
               and t['bbox'][0] <= x0 + 3 and t['bbox'][2] >= x1 - 3
               and t['bbox'][1] <= header_top + .5 and t['bbox'][3] >= bottom - .5 for t in existing):
            continue

        def columns(words):
            cells = [[] for _ in segments]
            for word in words:
                matches = [c for c, (left, right) in enumerate(zip(edges, edges[1:]))
                           if left - .75 <= word['bbox'][0] and word['bbox'][2] <= right + .75]
                if len(matches) != 1:
                    return None
                cells[matches[0]].append(word)
            return cells

        header_cells = columns(header)
        body_cells = columns(body)
        line_cells = [columns(line) for line in lines]
        if (header_cells is None or body_cells is None or not all(header_cells[1:])
                or len({_text(c) for c in header_cells[1:]}) < 2
                or any(cells is None or not all(cells) for cells in line_cells)):
            continue
        rows = []
        for r, (cells, y0, y1) in enumerate(((header_cells, header_top, top), (body_cells, top, bottom))):
            rows.append({'index': r, 'cells': [
                {'row': r, 'column': c, 'bbox': [edges[c], y0, edges[c + 1], y1],
                 'text': _text(words), 'word_ids': [w['id'] for w in words],
                 'source_text_matches': True, 'slot_status': 'present'} for c, words in enumerate(cells)],
                'role': 'possible_header' if r == 0 else 'body', 'review_status': 'unreviewed'})
        result.append({'id': f"p{source['page']}:underline{offset + len(result)}", 'kind': 'table_candidate',
                       'method': 'horizontal_rule_cells', 'rows': rows, 'row_count': 2,
                       'n_cols': len(segments), 'bbox': [x0, header_top, x1, bottom],
                       'source_drawing_ids': [d['id'] for d in [*top_rules, *segments]],
                       'body_source_line_count': len(lines), 'review_status': 'unreviewed',
                       'header_association_verified': False})
    return result
