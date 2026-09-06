"""Conservative table candidates from printed rules, preserving source words.

Complex logo paths must not participate in global grid snapping. Separately,
cell-width underline segments can reveal a one-row table with no vertical rules.
Both interpretations remain unreviewed and retain the actual rule references.
"""
from __future__ import annotations

from collections import defaultdict

import fitz


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
    return tables
