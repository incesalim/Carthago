"""Source-linked document structure, with explicit candidate and residual content.

Existing numerical table heuristics supply candidates, not verified truth. Every
source span remains accessible in physical PDF blocks/lines, including content
that no heuristic understands. Ruled tables add text-only cells. Alternative
overlapping tables are retained for review rather than silently choosing a winner.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import fitz

from .document_capture import capture_document, capture_page, _fold
from .document_corpus import Filing, source_identity
from .document_evidence import artifact_digest, compare_page_text, text_characters, verify_evidence_records
from .document_rule_tables import grid_paths, underline_candidates
from .document_narrative import narrative_candidates, verify_narrative
from .document_positioned_text import positioned_text, verify_positioned_text
from .document_table_context import table_context, verify_table_context
from .document_table_rows import table_source_rows, verify_table_source_rows
from .document_reading_layout import reading_layout, verify_reading_layout
from .document_segmented_tables import segmented_table_candidates, verify_segmented_tables
from .document_table_notes import table_note_links, verify_table_note_links
from .document_navigation import NAVIGATION_VERSION, document_navigation, verify_document_navigation
from .document_cell_fragments import link_cell_fragments, verify_cell_fragments, word_character_geometry

STRUCTURE_VERSION = "document-structure-1"


def structure_engine() -> dict:
    # Extraction dependencies participate; changing a storage/catalog adapter
    # must not force otherwise identical documents through extraction again.
    digest = hashlib.sha256()
    for name in ("document_structure.py", "document_capture.py", "document_sections.py",
                 "document_evidence.py", "document_corpus.py", "document_rule_tables.py", "document_narrative.py",
                 "document_tagged.py",
                 "document_positioned_text.py",
                 "document_table_context.py",
                 "document_table_rows.py",
                 "document_reading_layout.py",
                 "document_segmented_tables.py",
                 "document_table_notes.py",
                 "document_navigation.py",
                 "document_cell_fragments.py",
                 "prose.py", "extractor.py", "units.py"):
        path = Path(__file__).parent / name
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {"pymupdf": fitz.VersionBind, "implementation_sha256": digest.hexdigest()}


def _bounds(boxes):
    boxes = list(boxes)
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _inside(word, bbox):
    x0, y0, x1, y1 = word["bbox"]
    return bbox[0] <= (x0 + x1) / 2 <= bbox[2] and bbox[1] <= (y0 + y1) / 2 <= bbox[3]


def _compact(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def _image_rules(source):
    """Candidate horizontal rules made of repeated tiny raster dashes.

    QNB prints some mixed/text tables with thousands of 6×1-pixel dash images.
    They are neither a scanned page nor vector ruling. Preserve the images and
    infer a rule only from a closely spaced run of at least five aligned dashes.
    """
    bands = defaultdict(list)
    for image in source["images"]:
        x0, y0, x1, y1 = image["bbox"]
        if 0 < y1 - y0 < 2 and x1 - x0 >= 3 * (y1 - y0):
            bands[round((y0 + y1) / 2, 1)].append((x0, x1))
    rules = []
    for y, segments in sorted(bands.items()):
        run = []
        for start, end in sorted(segments):
            if run and start - run[-1][1] > max(4, 2 * (run[-1][1] - run[-1][0])):
                if len(run) >= 5 and run[-1][1] - run[0][0] >= 30:
                    rules.append(((run[0][0], y), (run[-1][1], y)))
                run = []
            run.append((start, end))
        if len(run) >= 5 and run[-1][1] - run[0][0] >= 30:
            rules.append(((run[0][0], y), (run[-1][1], y)))
    return rules


def _physical_blocks(source):
    blocks = defaultdict(lambda: defaultdict(list))
    for span in source["spans"]:
        blocks[span["block"]][span["line"]].append(span)
    result = []
    for block_id, lines in blocks.items():
        physical = [{"source_line": line_id, "span_ids": [s["id"] for s in spans],
                     "text": "".join(s["text"] for s in spans),
                     "bbox": _bounds(s["bbox"] for s in spans)}
                    for line_id, spans in lines.items()]
        result.append({"id": f"p{source['page']}:text{block_id}",
                       "kind": "text_block", "method": "pdf_text_blocks",
                       "source_block": block_id, "lines": physical,
                       "bbox": _bounds(line["bbox"] for line in physical),
                       "text": "\n".join(line["text"] for line in physical),
                       "semantic_role": None, "review_status": "unreviewed"})
    return result


def _numeric_candidates(source, capture):
    words = source["words"]
    lines, issues = [], []
    for line in capture.lines:
        # Source occurrence IDs, not just a bag of values. A sideways or glued
        # fragment that cannot be grounded remains explicitly unresolved.
        # The capture anchors a band at its earliest word, not its centre.
        # A symmetric window borrows words from the preceding band when two
        # baselines are about three points apart (superscripts/stacked headers).
        # Evidence coordinates are rounded to four decimals.
        refs = [w for w in words if -.0001 <= w["bbox"][1] - line.y <= 3.0001
                and line.x0 - .1 <= w["bbox"][0] <= line.x1 + .1]
        conserved = text_characters(line.text) == text_characters("".join(w["text"] for w in refs))
        lines.append({**asdict(line), "word_ids": [w["id"] for w in refs],
                      "source_text_matches": conserved,
                      "bbox": _bounds(w["bbox"] for w in refs)})
        if not conserved:
            issues.append({"kind": "line_source_mismatch", "line_order": line.line_order})
    line_map = {line["line_order"]: line for line in lines}
    word_map = {word["id"]: word for word in words}
    cells_at = defaultdict(list)
    for cell in capture.cells:
        line = line_map[cell.line_order]
        refs = [word_map[i] for i in line["word_ids"]
                if cell.x0 - .1 <= (word_map[i]["bbox"][0] + word_map[i]["bbox"][2]) / 2 <= cell.x1 + .1]
        conserved = text_characters(cell.text) == text_characters("".join(w["text"] for w in refs))
        label_words = set()
        label = _compact(line["label"])
        # A digit in "Tier 1" or "Article 4" is source text, not a value column.
        # Use the exact leading label and occurrence positions; never strip every
        # small integer (a genuinely disclosed 1 must survive as a value).
        if label and _compact(line["text"]).startswith(label):
            prefix = ""
            for word in sorted((word_map[i] for i in line["word_ids"]), key=lambda w: w["bbox"][0]):
                prefix += _compact(word["text"])
                if label.startswith(prefix):
                    label_words.add(word["id"])
                else:
                    break
        placement = ("label_text" if refs and all(w["id"] in label_words for w in refs)
                     else "data" if cell.col_index is not None else "unplaced")
        cells_at[cell.line_order].append({**asdict(cell), "word_ids": [w["id"] for w in refs],
                                         "placement": placement, "legacy_col_index": cell.col_index,
                                         "bbox": _bounds(w["bbox"] for w in refs),
                                         "source_text_matches": conserved})
        if not conserved:
            issues.append({"kind": "cell_source_mismatch", "line_order": cell.line_order,
                           "cell_index": cell.cell_index})
    tables = []
    for block in capture.blocks:
        members = [line for line in lines if line["block_id"] == block.block_id]
        groups = defaultdict(list)
        for line in members:
            groups[line["logical_row"] if line["logical_row"] is not None
                   else -line["line_order"]].append(line)
        rows = []
        for group in groups.values():
            cells = [cell for line in group for cell in cells_at[line["line_order"]]]
            rows.append({"index": len(rows), "label": " ".join(line["label"] for line in group),
                         "line_orders": [line["line_order"] for line in group],
                         # Preserve every physical cell, including collisions and
                         # unplaced columns. Consumers must not silently flatten.
                         "cells": cells, "review_status": "unreviewed"})
        inline = [line["line_order"] for line in lines
                  if block.first_line <= line["line_order"] <= block.last_line
                  and line["block_id"] != block.block_id]
        columns = sorted({cell["legacy_col_index"] for row in rows for cell in row["cells"]
                          if cell["placement"] == "data"})
        remap = {old: new for new, old in enumerate(columns)}
        for row in rows:
            for cell in row["cells"]:
                cell["col_index"] = remap[cell["legacy_col_index"]] if cell["placement"] == "data" else None
        tables.append({**asdict(block), "id": f"p{source['page']}:numeric{block.block_id}",
                       "kind": "table_candidate", "method": "legacy_numeric_geometry",
                       "bbox": _bounds(line["bbox"] for line in members if line["bbox"]),
                       "rows": rows, "inline_line_orders": inline,
                       "physical_row_count": block.row_count, "row_count": len(rows),
                       "legacy_n_cols": block.n_cols, "n_cols": len(columns),
                       "col_x": [block.col_x[c] for c in columns],
                       "col_labels": [block.col_labels[c] if c < len(block.col_labels) else "" for c in columns],
                       "review_status": "unreviewed", "header_association_verified": False})
    return tables, lines, issues


def _positioned_candidates(page, source, captured):
    """Keep source-declared image positions as a separate table alternative."""
    view = positioned_text(source)
    if not view['replacement_pair_count']:
        return view, [], view['issues']

    class PositionedPage:
        rotation = 0  # Pieces are already in displayed page coordinates.

        def __getattr__(self, name):
            return getattr(page, name)

        def get_text(self, *args, **kwargs):
            if args and args[0] == 'words':
                return [(*p['bbox'], p['text'], 0, i, 0) for i, p in enumerate(view['pieces'])]
            return page.get_text(*args, **kwargs)

    furniture = frozenset(_fold(line.text) for line in captured.lines if line.role == 'furniture')
    alternative = capture_page(PositionedPage(), source['page'], furniture)
    tables, _lines, issues = _numeric_candidates({**source, 'words': view['pieces']}, alternative)
    for table in tables:
        table.update(id=table['id'].replace(':numeric', ':positioned'),
                     method='native_image_replacement_geometry', word_view='positioned_text')
    # Table diagnostics belong beside the tables, without altering the source
    # positioning object that can be recomputed from retained evidence alone.
    for issue in issues:
        issue['view'] = 'positioned_text'
    return view, tables, [*view['issues'], *issues]


def _ruled_candidates(page, source):
    if page.rotation:
        # find_tables normalizes rotated pages internally, but supplied drawing
        # paths are still in the original coordinate system. Applying another
        # rotation to its output then misplaces cells a second time. Normalize
        # an isolated page copy first so paths, text and output all use the
        # source evidence's displayed coordinates. Never modify the source PDF.
        with fitz.open() as displayed:
            displayed.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
            displayed[0].remove_rotation()
            return _ruled_candidates(displayed[0], source)
    tables = []
    # Horizontal underlines alone cannot define a ruled grid. Avoid the costly
    # table search on ordinary narrative/BRSA pages that have no vertical rules.
    # These pages still go through numeric detection and complete source capture.
    paths = grid_paths(page.get_drawings())
    image_rules = _image_rules(source)
    vertical, horizontal = set(), set()
    for path in paths:
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1:3]
                if abs(a.x - b.x) < 1 and abs(a.y - b.y) > 8:
                    vertical.add(round(a.x))
                if abs(a.y - b.y) < 1 and abs(a.x - b.x) > 8:
                    horizontal.add(round(a.y))
            elif item[0] == "re":
                rect = fitz.Rect(item[1])
                if rect.height > 8:
                    vertical.update((round(rect.x0), round(rect.x1)))
                if rect.width > 8:
                    horizontal.update((round(rect.y0), round(rect.y1)))
    virtual_rules = [(fitz.Point(a) * page.derotation_matrix,
                      fitz.Point(b) * page.derotation_matrix) for a, b in image_rules]
    for a, b in virtual_rules:
        if abs(a.y - b.y) < 1:
            horizontal.add(round(a.y))
        if abs(a.x - b.x) < 1:
            vertical.add(round(a.x))
    if len(vertical) < 2 or len(horizontal) < 2:
        return tables
    # The line strategy also finds text-only tables; it does not require a
    # minimum count of figures. Grid detection remains an unverified hypothesis.
    for number, table in enumerate(page.find_tables(
            strategy="lines_strict", paths=paths, add_lines=virtual_rules or None).tables):
        extracted = table.extract()
        rows = []
        for r, row in enumerate(table.rows):
            cells = []
            for c, cell in enumerate(row.cells):
                bbox = list(fitz.Rect(cell) * page.rotation_matrix) if cell else None
                refs = [w for w in source["words"] if bbox and _inside(w, bbox)]
                text = extracted[r][c]
                cells.append({"row": r, "column": c, "bbox": bbox, "text": text,
                              "word_ids": [w["id"] for w in refs],
                              "source_text_matches": text_characters(text or "") ==
                              text_characters("".join(w["text"] for w in refs)),
                              # None is an absent/merged slot, never a zero.
                              "slot_status": "absent_or_merged" if cell is None else "present"})
            rows.append({"index": r, "cells": cells})
        tables.append({"id": f"p{source['page']}:ruled{number}", "kind": "table_candidate",
                       "method": "pymupdf_lines_strict", "rows": rows,
                       "image_rule_candidates": [[list(a), list(b)] for a, b in image_rules],
                       "bbox": list(fitz.Rect(table.bbox) * page.rotation_matrix),
                       "row_count": table.row_count, "n_cols": table.col_count,
                       "header_names": table.header.names,
                       "header_external": table.header.external,
                       "review_status": "unreviewed", "header_association_verified": False})
    return tables


def build_document_structure(pdf_path: Path, evidence: list[dict]) -> dict:
    check = verify_evidence_records(evidence)
    if not check["valid"]:
        raise ValueError("Cannot structure invalid source evidence")
    source = evidence[0]["source"]
    filing = Filing(source["bank_ticker"], source["period"], source["kind"])

    def assert_source():
        observed = source_identity(pdf_path, filing)
        if observed["pdf_sha256"] != source["pdf_sha256"]:
            raise ValueError("Structured document PDF differs from source evidence")

    assert_source()
    capture = capture_document(pdf_path)
    if capture.page_count != evidence[0]["page_count"]:
        raise ValueError("Capture page inventory differs from source evidence")
    navigation = document_navigation(evidence)
    sections, items = navigation['sections'], navigation['contents_entries']
    pages = []
    with fitz.open(pdf_path) as pdf:
        for observed, captured in zip(evidence[1:], capture.pages, strict=True):
            numeric, lines, issues = _numeric_candidates(observed, captured)
            ruled = _ruled_candidates(pdf[observed["page"] - 1], observed)
            if any(not c['source_text_matches'] for t in ruled for r in t['rows'] for c in r['cells']):
                geometry = word_character_geometry(pdf[observed['page'] - 1], observed,
                                                   {w['id'] for w in observed['words']})
                ruled = [link_cell_fragments(t, observed, geometry) if any(
                    not c['source_text_matches'] for r in t['rows'] for c in r['cells']) else t for t in ruled]
            extra = underline_candidates(observed, numeric + ruled)
            tables = numeric + ruled + extra
            tables.extend(segmented_table_candidates(observed, tables))
            positioned = None
            if observed.get('actualtext_changes_word_view'):
                positioned, alternatives, position_issues = _positioned_candidates(pdf[observed['page'] - 1], observed, captured)
                tables.extend(alternatives)
                issues.extend(position_issues)
            for table in tables:
                if table.get('word_boundary_observations'):
                    issues.append({'kind': 'word_crosses_table_cells', 'table_id': table['id'],
                                   'word_ids': [o['word_id'] for o in table['word_boundary_observations']]})
                for row in table["rows"]:
                    for cell in row["cells"]:
                        if not cell["source_text_matches"]:
                            issues.append({"kind": "table_cell_source_mismatch", "table_id": table["id"],
                                           "row": row["index"], "column": cell.get("column", cell.get("col_index"))})
            conservation = compare_page_text(observed, [line["text"] for line in lines])
            if not conservation["text_conserved"]:
                issues.append({"kind": "legacy_text_not_conserved"})
            if observed["images"]:
                issues.append({"kind": "image_content_unreviewed", "count": len(observed["images"])})
            if observed["drawings"]:
                issues.append({"kind": "drawing_content_unreviewed", "count": len(observed["drawings"])})
            if captured.text_layer != "text":
                issues.append({"kind": "unreadable_content", "text_layer": captured.text_layer})
            if observed["replacement_character_count"]:
                issues.append({"kind": "replacement_characters",
                               "count": observed["replacement_character_count"]})
            if observed.get("actualtext_changes_word_view"):
                issues.append({"kind": "actualtext_geometry_unverified"})
            if (observed.get("native_structure") or {}).get("unmapped_nonblank_spans"):
                issues.append({"kind": "native_text_span_unresolved",
                               "count": observed["native_structure"]["unmapped_nonblank_spans"]})
            span_blocks = _physical_blocks(observed)
            pages.append({"page": observed["page"], "text_blocks": span_blocks,
                          "segmented_tables_schema": "segmented-table-candidates-1",
                          "candidate_lines": lines, "tables": tables,
                          "notes": [{**asdict(note), "review_status": "unreviewed"}
                                    for note in captured.notes],
                          "source_image_ids": [x["id"] for x in observed["images"]],
                          "source_drawing_ids": [x["id"] for x in observed["drawings"]],
                          "text_conservation": conservation, "issues": issues,
                          **({'positioned_text': positioned} if positioned is not None else {}),
                          "reading_order_verified": False})
    narrative_candidates(pages, evidence, sections)
    for page, page_source in zip(pages, evidence[1:], strict=True):
        page['table_source_rows'] = table_source_rows(page, page_source)
        page['reading_layout'] = reading_layout(page, page_source)
    for page, context in zip(pages, table_context(pages), strict=True):
        page['table_context'] = context
    for page, page_source in zip(pages, evidence[1:], strict=True):
        page['table_notes'] = table_note_links(page, page_source)
    assert_source()
    result = {"schema_version": STRUCTURE_VERSION, "engine": structure_engine(),
              "source": source, "evidence_artifact_sha256": artifact_digest(evidence),
              "sections": sections, "contents_items": items, "pages": pages,
              "navigation_schema": NAVIGATION_VERSION, "navigation": navigation,
              "status": "structured_candidates", "semantic_verification": "not_performed"}
    # Dataclass tuples (markers, columns, note links) must have the same shape
    # before and after persistence. A cache hit returns exactly this JSON model.
    result = json.loads(json.dumps(result, ensure_ascii=False))
    validation = verify_document_structure(result, evidence)
    if not validation["valid"]:
        raise ValueError(f"Structure failed source accounting: {validation['errors']}")
    return result


def verify_document_structure(structure: dict, evidence: list[dict]) -> dict:
    """Test source accounting and geometry; this does not certify interpretation."""
    errors = []
    errors.extend(verify_document_navigation(structure, evidence))
    errors.extend(verify_table_context(structure['pages']))
    if structure.get("source") != evidence[0]["source"]:
        errors.append("source_identity_mismatch")
    if structure.get("evidence_artifact_sha256") != artifact_digest(evidence):
        errors.append("source_artifact_mismatch")
    if [p["page"] for p in structure["pages"]] != [p["page"] for p in evidence[1:]]:
        errors.append("page_inventory_mismatch")
    for page, source in zip(structure["pages"], evidence[1:]):
        prefix = f"page_{source['page']}:"
        if any('table_source_rows' in p for p in structure['pages']) and 'table_source_rows' not in page:
            errors.append(prefix + 'missing_table_source_rows')
        if any('reading_layout' in p for p in structure['pages']) and 'reading_layout' not in page:
            errors.append(prefix + 'missing_reading_layout')
        if any('table_notes' in p for p in structure['pages']) and 'table_notes' not in page:
            errors.append(prefix + 'missing_table_notes')
        errors.extend(prefix + error for error in verify_narrative(page, source))
        errors.extend(prefix + error for error in verify_reading_layout(page, source))
        errors.extend(prefix + error for error in verify_table_source_rows(page, source))
        errors.extend(prefix + error for error in verify_segmented_tables(page, source))
        errors.extend(prefix + error for error in verify_table_note_links(page, source))
        spans = {s["id"]: s for s in source["spans"]}
        used = Counter()
        for block in page["text_blocks"]:
            for line in block["lines"]:
                used.update(line["span_ids"])
                if any(i not in spans for i in line["span_ids"]):
                    errors.append(prefix + "unknown_span")
                    continue
                expected = [spans[i] for i in line["span_ids"]]
                if line["text"] != "".join(s["text"] for s in expected):
                    errors.append(prefix + "span_text_mismatch")
                if line["bbox"] != _bounds(s["bbox"] for s in expected):
                    errors.append(prefix + "span_geometry_mismatch")
            if block["text"] != "\n".join(line["text"] for line in block["lines"]):
                errors.append(prefix + "block_text_mismatch")
        if used != Counter(spans.keys()):
            errors.append(prefix + "span_inventory_mismatch")
        for key, source_key in (("source_image_ids", "images"), ("source_drawing_ids", "drawings")):
            if page[key] != [x["id"] for x in source[source_key]]:
                errors.append(prefix + source_key + "_inventory_mismatch")
        positioned = page.get('positioned_text')
        if positioned is not None:
            errors.extend(prefix + error for error in verify_positioned_text(positioned, source)['errors'])
        for table in page["tables"]:
            errors.extend(prefix + error for error in verify_cell_fragments(table, source))
            if table.get('word_boundary_observations'):
                expected_issue = {'kind': 'word_crosses_table_cells', 'table_id': table['id'],
                                  'word_ids': [o['word_id'] for o in table['word_boundary_observations']]}
                if expected_issue not in page['issues']:
                    errors.append(prefix + 'missing_word_boundary_issue')
            word_view = table.get('word_view', 'words')
            if word_view not in ('words', 'positioned_text') or word_view == 'positioned_text' and positioned is None:
                errors.append(prefix + 'unknown_table_word_view')
                continue
            items = positioned['pieces'] if word_view == 'positioned_text' else source['words']
            words = {w['id']: w for w in items}
            for row in table["rows"]:
                for cell in row["cells"]:
                    if 'source_fragments' in cell:
                        # The table-level check rederives every character range,
                        # cell assignment and boundary observation together.
                        continue
                    refs = cell["word_ids"]
                    if any(i not in words for i in refs):
                        errors.append(prefix + "unknown_cell_word")
                        continue
                    if cell["source_text_matches"] and text_characters(cell["text"] or "") != text_characters(
                            "".join(words[i]["text"] for i in refs)):
                        errors.append(prefix + "cell_text_mismatch")
                    if refs and (not cell["bbox"] or any(not _inside(words[i], cell["bbox"]) for i in refs)):
                        errors.append(prefix + "cell_geometry_mismatch")
    return {"valid": not errors, "errors": errors, "semantic_verification": "not_performed"}


def structure_digest(structure: dict) -> str:
    return hashlib.sha256(json.dumps(structure, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def structure_jsonl(structure: dict) -> bytes:
    """Streamable, individually verifiable pages without loading a whole filing."""
    def line(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    pages = [line({"type": "structured_page", **page}) for page in structure["pages"]]
    manifest = {"type": "structure_manifest", **{k: v for k, v in structure.items() if k != "pages"},
                "page_count": len(pages),
                "page_sha256": [hashlib.sha256(page.encode("utf-8")).hexdigest() for page in pages]}
    return ("\n".join([line(manifest), *pages]) + "\n").encode("utf-8")


def structure_from_jsonl(body: bytes) -> dict:
    lines = body.splitlines()
    if not lines:
        raise ValueError("Empty structure artifact")
    manifest = json.loads(lines[0])
    if manifest.get("type") != "structure_manifest" or manifest.get("page_count") != len(lines) - 1:
        raise ValueError("Structure page manifest mismatch")
    hashes = [hashlib.sha256(line).hexdigest() for line in lines[1:]]
    if manifest.get("page_sha256") != hashes:
        raise ValueError("Structure page digest mismatch")
    pages = []
    for number, line in enumerate(lines[1:], 1):
        page = json.loads(line)
        if page.pop("type", None) != "structured_page" or page.get("page") != number:
            raise ValueError("Structure page order mismatch")
        pages.append(page)
    return {**{k: v for k, v in manifest.items() if k not in ("type", "page_count", "page_sha256")},
            "pages": pages}
