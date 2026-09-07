"""Check independently annotated source cases, including row/column association.

Annotations name a PDF byte revision and exact printed labels, cells and regions.
Passing selected cases is a regression result, never a whole-report quality score.
"""
from __future__ import annotations

import unicodedata
import json
import hashlib
from collections import Counter
from pathlib import Path

SOURCE_CASE_KINDS = frozenset({"source_span", "source_word", "source_review"})


def _text(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def paragraph_digest(text: str) -> str:
    """Hash normalized, independently transcribed prose; retain punctuation."""
    return hashlib.sha256(_text(text).encode("utf-8")).hexdigest()


def _continuation_matches(case, pages, sources):
    from .document_table_context import verify_table_context
    if verify_table_context(list(pages.values())):
        return []
    context = pages[case['page']].get('table_context', {})
    matches = []
    for link in context.get('continuations', []):
        if (link['status'] != 'unique_source_evidence' or link['from_page'] != case['from_page']
                or link['title'] != case['title'] or link['column_identifiers'] != case['column_identifiers']):
            continue
        good = True
        for number, table_id in [(link['from_page'], link['from_table_ids'][0]),
                                  (link['to_page'], link['to_table_id'])]:
            table_context = next(t for t in pages[number]['table_context']['tables'] if t['table_id'] == table_id)
            heading = table_context['heading']
            spans = {s['id']: s for s in sources[number]['spans']}
            ids = heading['source_span_ids']
            if (not ids or len(ids) != len(set(ids)) or any(i not in spans for i in ids)
                    or _text(' '.join(spans[i]['text'] for i in ids)) != _text(heading['text'])):
                good = False
            elif heading['bbox'] != [min(spans[i]['bbox'][0] for i in ids), min(spans[i]['bbox'][1] for i in ids),
                                     max(spans[i]['bbox'][2] for i in ids), max(spans[i]['bbox'][3] for i in ids)]:
                good = False
            words = {w['id']: w for w in sources[number]['words']}
            for cell in table_context['column_identifiers']['cells']:
                ids = cell['word_ids']
                if (not ids or len(ids) != len(set(ids)) or any(i not in words for i in ids)
                        or _text(' '.join(words[i]['text'] for i in ids)) != _text(cell['text'])):
                    good = False
                elif any(not (cell['bbox'][0] <= (words[i]['bbox'][0] + words[i]['bbox'][2]) / 2 <= cell['bbox'][2]
                              and cell['bbox'][1] <= (words[i]['bbox'][1] + words[i]['bbox'][3]) / 2 <= cell['bbox'][3]) for i in ids):
                    good = False
        if good:
            matches.append(link['to_table_id'])
    return matches


def _complete_table_matches(case, page, source):
    """Check every annotated slot and every source word in a reviewed region."""
    from .document_table_context import table_context
    contexts = {t['table_id']: t for t in table_context([page])[0]['tables']}
    bounds, expected = case['bbox'], case['rows']
    words = {w['id']: w for w in source['words']}

    def inside(box, region):
        return region[0] <= (box[0] + box[2]) / 2 <= region[2] and region[1] <= (box[1] + box[3]) / 2 <= region[3]

    expected_words = Counter(w['id'] for w in source['words'] if inside(w['bbox'], bounds))
    for region in case.get('source_text_regions', []):
        selected = [s for s in source['spans'] if inside(s['bbox'], region['bbox'])]
        if not selected or _text(' '.join(s['text'] for s in selected)) != _text(region['text']):
            return []
    matches = []
    for table in page['tables']:
        if (table['method'] != case['method'] or table['row_count'] != len(expected)
                or table['n_cols'] != len(expected[0]) or len(table['rows']) != len(expected)):
            continue
        grid = contexts[table['id']]['physical_grid']
        if grid is None or [a for a in grid['anchors'] if a['row_span'] > 1 or a['column_span'] > 1] != case['spans']:
            continue
        actual_words, good = Counter(), True
        for r, (row, texts) in enumerate(zip(table['rows'], expected, strict=True)):
            if row['index'] != r or len(row['cells']) != len(texts):
                good = False
                break
            for c, (cell, text) in enumerate(zip(row['cells'], texts, strict=True)):
                refs = cell['word_ids']
                if (cell['column'] != c or (cell['text'] is None) != (text is None)
                        or _text(cell['text']) != _text(text) or any(i not in words for i in refs)):
                    good = False
                    break
                if text is None:
                    if cell['bbox'] is not None or refs:
                        good = False
                    continue
                box = cell['bbox']
                if (box is None or not (bounds[0] <= box[0] <= box[2] <= bounds[2]
                                       and bounds[1] <= box[1] <= box[3] <= bounds[3])
                        or _text(' '.join(words[i]['text'] for i in refs)) != _text(text)
                        or any(not inside(words[i]['bbox'], box) for i in refs)):
                    good = False
                actual_words.update(refs)
        if good and actual_words == expected_words:
            matches.append(table['id'])
    return matches


def _source_line_matches(case, page, source):
    from .document_table_rows import table_source_rows
    if page.get('table_source_rows') != table_source_rows(page, source):
        return []
    region = case['bbox']
    matches = []
    for table in page['table_source_rows']['tables']:
        for split in table['split_rows']:
            for line in split['lines']:
                box = line['bbox']
                if (region[0] <= box[0] <= box[2] <= region[2]
                        and region[1] <= box[1] <= box[3] <= region[3]
                        and [_text(c['text']) for c in line['cells']] == [_text(t) for t in case['columns']]):
                    matches.append((table['table_id'], split['source_row'], line['index']))
    return matches


def _table_note_matches(case, page, source):
    from .document_table_notes import table_note_links
    from .document_narrative import verify_narrative
    view = page.get('table_notes')
    if view is None or view != table_note_links(page, source) or verify_narrative(page, source):
        return []
    words = {w['id']: w for w in source['words']}
    matches = []
    for table in view['tables']:
        if len(table['links']) != len(case['links']):
            continue
        good = True
        for link, expected in zip(table['links'], case['links'], strict=True):
            if (any(link[key] != expected[key] for key in ('label', 'column', 'header_row', 'header_word_ids'))
                    or _text(link['text']) != _text(expected['text'])
                    or any(i not in words for i in link['header_word_ids'])
                    or _text(' '.join(words[i]['text'] for i in link['header_word_ids'])) != link['label']):
                good = False
                break
            for field in ('marker_bbox', 'text_bbox'):
                box, bounds = link[field], expected[field]
                if not (bounds[0] <= box[0] <= box[2] <= bounds[2] and bounds[1] <= box[1] <= box[3] <= bounds[3]):
                    good = False
        if good:
            matches.append(table['table_id'])
    return matches


def _narrative_matches(case, page, sources, pages):
    elements = {e["id"]: (p["page"], e) for p in pages.values() for e in p.get("narrative_elements", [])}

    def source_matches(element, number, bounds=None):
        spans = {s["id"]: s for s in sources[number]["spans"]}
        ids = element.get("span_ids", [])
        if not ids or len(ids) != len(set(ids)) or any(i not in spans for i in ids):
            return False
        actual = [spans[i] for i in ids]
        text = ""
        previous = None
        for span in actual:
            key = span["block"], span["line"]
            text += ("\n" if previous is not None and key != previous else "") + span["text"]
            previous = key
        if _text(text) != _text(element["text"]):
            return False
        return bounds is None or all(bounds[0] <= s["bbox"][0] <= s["bbox"][2] <= bounds[2]
                                     and bounds[1] <= s["bbox"][1] <= s["bbox"][3] <= bounds[3] for s in actual)

    matching = []
    for element in page.get("narrative_elements", []):
        if element["kind"] != case.get("element_kind", "paragraph_candidate"):
            continue
        if paragraph_digest(element["text"]) != case["text_sha256"]:
            continue
        path = element.get("heading_path", [])
        if [_text(h["text"]) for h in path] != [_text(h) for h in case["heading_path"]]:
            continue
        if not source_matches(element, case["page"], case["bbox"]):
            continue
        good = True
        for heading in path:
            number, original = elements.get(heading["id"], (None, None))
            if (original is None or original["kind"] != "heading_candidate"
                    or _text(original["text"]) != _text(heading["text"])
                    or number > case["page"]
                    or (number == case["page"] and original["source_lines"][0] >= element["source_lines"][0])
                    or not source_matches(original, number)):
                good = False
                break
        if good:
            matching.append(element["id"])
    return matching


def _reading_layout_matches(case, page, source):
    from .document_narrative import verify_narrative
    from .document_reading_layout import reading_layout
    view = page.get('reading_layout')
    if (view is None or verify_narrative(page, source) or view != reading_layout(page, source)
            or view['element_order'] != case['element_order'] or view['list_pairs'] != case['list_pairs']):
        return False
    columns = []

    def visit(node):
        if 'element_ids' in node:
            return node['element_ids']
        children = [visit(child) for child in node['children']]
        if node.get('axis') == 'x':
            columns.append(children)
        return [i for child in children for i in child]

    if view['tree']:
        visit(view['tree'])
    return all(group in columns for group in case.get('column_groups', []))


def _navigation_selection_matches(case, structure, evidence):
    """Check reviewed navigation locations without claiming all contents were read."""
    from .document_navigation import verify_document_navigation
    if verify_document_navigation(structure, evidence):
        return False
    nav = structure.get('navigation', {})
    sections = [{k: s.get(k) for k in ('number', 'title', 'page_start', 'page_end')}
                for s in nav.get('sections', [])]
    entries = nav.get('contents_entries', [])
    counts = Counter(e['section'] for e in entries)
    if sections != case['sections'] or sorted(counts.items()) != [tuple(p) for p in case['contents_counts']]:
        return False
    for expected in case['contents']:
        selected = [e for e in entries if (e['section'], e['number']) == (expected['section'], expected['number'])]
        if len(selected) != 1 or any(selected[0].get(k) != v for k, v in expected.items()):
            return False
    for page, folio in case['folio_pairs']:
        selected = [f for f in nav.get('folio_observations', []) if f['source']['page'] == page]
        if len(selected) != 1 or selected[0]['folio'] != folio:
            return False
    for expected in case['body_markers']:
        selected = [b for b in nav.get('body_banners', []) if b['number'] == expected['number']]
        if len(selected) != 1 or selected[0]['banner']['text'] != expected['text']:
            return False
    for expected in case.get('contents_section_titles', []):
        selected = [s for p in nav.get('contents_pages', []) for s in p['sections'] if s['number'] == expected['number']]
        if len(selected) != 1 or selected[0]['title'] != expected['title']:
            return False
    return True


def check_annotations(structure: dict, evidence: list[dict], annotation: dict) -> dict:
    failures, content_reviews = [], []
    if (annotation["pdf_sha256"] != evidence[0]["source"]["pdf_sha256"]
            or structure["source"] != evidence[0]["source"]):
        return {"passed": False, "failures": [{"kind": "source_revision_mismatch"}],
                "scope": "annotated_cases_only"}
    if annotation.get("filing") and any(evidence[0]["source"].get(k) != v
                                         for k, v in annotation["filing"].items()):
        return {"passed": False, "failures": [{"kind": "filing_identity_mismatch"}],
                "scope": "annotated_cases_only"}
    sources = {p["page"]: p for p in evidence[1:]}
    pages = {p["page"]: p for p in structure["pages"]}
    for case in annotation["cases"]:
        if case.get("kind") == "source_review":
            from .document_content_review import validate_content_review
            if validate_content_review(case, sources):
                content_reviews.append(case)
            else:
                failures.append({"case": case["id"], "kind": "content_review_source_mismatch"})
            continue
        prefix = {"case": case["id"], "page": case["page"]}
        if case["page"] not in pages or case["page"] not in sources:
            failures.append({**prefix, "kind": "missing_page"})
            continue
        if case.get('kind') == 'table_continuation':
            matching = (_continuation_matches(case, pages, sources)
                        if case['from_page'] in pages and case['from_page'] in sources else [])
            if len(matching) != 1:
                failures.append({**prefix, 'kind': 'table_continuation_source_mismatch',
                                 'matching_candidates': len(matching)})
            continue
        if case.get('kind') == 'document_navigation':
            from .document_navigation import verify_document_navigation
            nav = structure.get('navigation', {})
            observed = {
                'sections': [{k: s.get(k) for k in ('number', 'title', 'page_start', 'page_end')}
                             for s in nav.get('sections', [])],
                'contents': [{k: e.get(k) for k in ('section', 'number', 'title', 'declared_folio', 'page_start', 'page_end')}
                             for e in nav.get('contents_entries', [])],
                'folio_pairs': [[f['source']['page'], f['folio']] for f in nav.get('folio_observations', [])],
                'conflicting_entry_ids': sorted({i['entry_id'] for i in nav.get('issues', [])
                                                if i['kind'].startswith('contents_target_')})}
            if (verify_document_navigation(structure, evidence)
                    or any(observed[k] != case[k] for k in observed)):
                failures.append({**prefix, 'kind': 'navigation_source_mismatch'})
            continue
        if case.get('kind') == 'navigation_source_selection':
            if not _navigation_selection_matches(case, structure, evidence):
                failures.append({**prefix, 'kind': 'navigation_selection_source_mismatch'})
            continue
        if case.get('kind') == 'complete_physical_table':
            matching = _complete_table_matches(case, pages[case['page']], sources[case['page']])
            if len(matching) != 1:
                failures.append({**prefix, 'kind': 'complete_table_source_mismatch',
                                 'matching_candidates': len(matching)})
            continue
        if case.get('kind') == 'source_table_line':
            matching = _source_line_matches(case, pages[case['page']], sources[case['page']])
            if len(matching) != 1:
                failures.append({**prefix, 'kind': 'table_source_line_mismatch',
                                 'matching_candidates': len(matching)})
            continue
        if case.get('kind') == 'reading_layout':
            if not _reading_layout_matches(case, pages[case['page']], sources[case['page']]):
                failures.append({**prefix, 'kind': 'reading_layout_source_mismatch'})
            continue
        if case.get('kind') == 'table_note_links':
            matching = _table_note_matches(case, pages[case['page']], sources[case['page']])
            if len(matching) != 1:
                failures.append({**prefix, 'kind': 'table_note_source_mismatch',
                                 'matching_candidates': len(matching)})
            continue
        if case.get("kind") in SOURCE_CASE_KINDS:
            source = sources[case["page"]]
            if case["kind"] == "source_span":
                matching = [s for s in source["spans"] if paragraph_digest(s["text"]) == case["text_sha256"]]
            else:
                words = source.get(case.get("view", "words")) or []
                bounds = case["bbox"]
                matching = [w for w in words if _text(w["text"]) == _text(case["text"])
                            and bounds[0] <= w["bbox"][0] <= w["bbox"][2] <= bounds[2]
                            and bounds[1] <= w["bbox"][1] <= w["bbox"][3] <= bounds[3]]
            if len(matching) != 1:
                failures.append({**prefix, "kind": "source_text_occurrence_mismatch",
                                 "matching_candidates": len(matching)})
            continue
        if case.get("kind") == "narrative":
            matching = _narrative_matches(case, pages[case["page"]], sources, pages)
            if len(matching) != 1:
                failures.append({**prefix, "kind": "paragraph_heading_source_mismatch",
                                 "matching_candidates": len(matching)})
            continue
        if case.get('kind') == 'positioned_text':
            from .document_positioned_text import verify_positioned_text
            view = pages[case['page']].get('positioned_text')
            bounds = case['bbox']
            matching = []
            if view is not None and verify_positioned_text(view, sources[case['page']])['valid']:
                matching = [p for p in view['pieces'] if p['method'] == case['method']
                            and paragraph_digest(p['text']) == case['text_sha256']
                            and bounds[0] <= p['bbox'][0] <= p['bbox'][2] <= bounds[2]
                            and bounds[1] <= p['bbox'][1] <= p['bbox'][3] <= bounds[3]]
            if len(matching) != 1:
                failures.append({**prefix, 'kind': 'positioned_source_region_mismatch',
                                 'matching_candidates': len(matching)})
            continue
        candidates = [table for table in pages[case["page"]]["tables"]
                      if table["method"] == case.get("method", "legacy_numeric_geometry")]
        matching = []
        for table in candidates:
            word_view = table.get('word_view', 'words')
            if word_view == 'positioned_text':
                from .document_positioned_text import verify_positioned_text
                view = pages[case['page']].get('positioned_text')
                if view is None or not verify_positioned_text(view, sources[case['page']])['valid']:
                    continue
                source_words = view['pieces']
            elif word_view == 'words':
                source_words = sources[case['page']]['words']
            else:
                continue
            rows = [r for r in table["rows"] if _text(r.get("label", r["cells"][0].get("text")
                                                       if r["cells"] else None)) == _text(case["row_label"])]
            for row in rows:
                if table["n_cols"] != case["column_count"]:
                    continue
                good = True
                for expected in case["cells"]:
                    cells = [c for c in row["cells"] if c.get("placement", "data") == "data"
                             and c.get("col_index", c.get("column")) == expected["column"]]
                    if len(cells) != 1 or _text(cells[0]["text"]) != _text(expected["text"]):
                        good = False
                        break
                    cell = cells[0]
                    if not cell["bbox"] or not cell["word_ids"]:
                        good = False
                        break
                    box, bounds = cell["bbox"], expected["bbox"]
                    words = {w['id']: w for w in source_words}
                    if any(i not in words for i in cell["word_ids"]):
                        good = False
                        break
                    actual_words = [words[i] for i in cell["word_ids"]]
                    if _text(" ".join(w["text"] for w in actual_words)) != _text(expected["text"]):
                        good = False
                        break
                    if any(not (bounds[0] <= w["bbox"][0] <= w["bbox"][2] <= bounds[2]
                                and bounds[1] <= w["bbox"][1] <= w["bbox"][3] <= bounds[3])
                           for w in actual_words):
                        good = False
                        break
                    if any(not (box[0] <= (w["bbox"][0] + w["bbox"][2]) / 2 <= box[2]
                                and box[1] <= (w["bbox"][1] + w["bbox"][3]) / 2 <= box[3])
                           for w in actual_words):
                        good = False
                        break
                if good:
                    matching.append(table["id"])
        if len(matching) != 1:
            failures.append({**prefix, "kind": "row_column_source_mismatch",
                             "matching_candidates": len(matching)})
    return {"passed": not failures, "failures": failures,
            **({"content_reviews": content_reviews} if content_reviews else {}),
            "cases_checked": len(annotation["cases"]), "scope": "annotated_cases_only"}


def check_registered_annotations(structure: dict, evidence: list[dict], directory: Path, *,
                                 source_only: bool = False) -> dict:
    source = evidence[0]["source"]
    matches, checks = [], []
    for path in sorted(directory.glob("*.json")):
        annotation = json.loads(path.read_text(encoding="utf-8"))
        if not all(source.get(k) == v for k, v in annotation["filing"].items()):
            continue
        if source_only:
            annotation["cases"] = [c for c in annotation["cases"] if c.get("kind") in SOURCE_CASE_KINDS]
            if not annotation["cases"]:
                continue
        matches.append(path.name)
        if annotation["pdf_sha256"] == source["pdf_sha256"]:
            checks.append({"annotation": path.name, **check_annotations(structure, evidence, annotation)})
    if not checks:
        return {"status": "source_revision_unannotated" if matches else "not_annotated",
                "checks": [], "scope": "annotated_cases_only"}
    return {"status": "passed" if all(c["passed"] for c in checks) else "failed",
            "checks": checks, "scope": "annotated_cases_only"}


def check_source_annotations(evidence: list[dict], directory: Path) -> dict:
    source_only = {"source": evidence[0]["source"], "pages": [{"page": p["page"]} for p in evidence[1:]]}
    return check_registered_annotations(source_only, evidence, directory, source_only=True)
