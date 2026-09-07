"""Source-linked paragraph and heading candidates; no prose is discarded.

PDF blocks often contain an entire audit opinion. Blank lines, spacing, style
changes and table regions provide explicit segmentation evidence. These cues
do not certify reading order or meaning. Original physical blocks remain intact.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import median

# These overlapping alternatives are retained for table review. Their inferred
# header rectangles must not split or reclassify the underlying source prose.
_ALTERNATIVE_TABLE_METHODS = {'horizontal_rule_cells', 'segmented_rules_and_source_lines'}
_ROMAN_HEADING = re.compile(r'^\s*[IVXLCDM]+\.\s+')


def _bounds(spans):
    return [min(s["bbox"][0] for s in spans), min(s["bbox"][1] for s in spans),
            max(s["bbox"][2] for s in spans), max(s["bbox"][3] for s in spans)]


def _lines(source):
    lines = defaultdict(list)
    for span in source["spans"]:
        lines[span["block"], span["line"]].append(span)
    return lines


def _table_envelopes(tables):
    """Numerical envelopes around separate ruled tables cannot own their gaps."""
    ruled = [t for t in tables if t.get('method') == 'pymupdf_lines_strict' and t.get('bbox')]
    envelopes = set()
    for table in tables:
        if table.get('method') != 'legacy_numeric_geometry' or not table.get('bbox'):
            continue
        b = table['bbox']
        enclosed = [t['bbox'] for t in ruled if t['id'] != table['id']
                    and b[0] - 1 <= t['bbox'][0] < t['bbox'][2] <= b[2] + 1
                    and b[1] - 1 <= t['bbox'][1] < t['bbox'][3] <= b[3] + 1]
        if any(a[2] <= c[0] or c[2] <= a[0] or a[3] <= c[1] or c[3] <= a[1]
               for i, a in enumerate(enclosed) for c in enclosed[i + 1:]):
            envelopes.add(table['id'])
    return envelopes


def _line_kind(spans, tables, envelopes):
    text = "".join(s["text"] for s in spans)
    visible = [s for s in spans if s["text"].strip()]
    memberships = []
    for span in visible:
        x, y = (span["bbox"][0] + span["bbox"][2]) / 2, (span["bbox"][1] + span["bbox"][3]) / 2
        memberships.append({t["id"] for t in tables if t.get("bbox")
                            and t.get('method') not in _ALTERNATIVE_TABLE_METHODS
                            and t['id'] not in envelopes
                            and t.get('word_view', 'words') == 'words'
                            and t["bbox"][0] <= x <= t["bbox"][2] and t["bbox"][1] <= y <= t["bbox"][3]})
    table_ids = sorted(set().union(*memberships)) if memberships else []
    if table_ids:
        return ("table_text" if all(memberships) else "mixed_text"), table_ids
    styled = sum(len(s["text"].strip()) for s in visible if s["flags"] & (2 | 16))
    total = sum(len(s["text"].strip()) for s in visible)
    roman_prefix = re.fullmatch(r'\s*[IVXLCDM]+\.\s*', text) is not None
    if total and styled / total >= .8 and len(text.strip()) <= 180 and (sum(c.isalpha() for c in text) >= 3 or roman_prefix):
        return "heading_candidate", []
    if re.match(r"^\s*(?:[•▪‣]|\(?[a-zA-Z0-9]{1,3}[.)])\s+", text):
        return "list_item_candidate", []
    return "paragraph_candidate", []


def _candidate_table_ids(spans, tables):
    """Keep uncertain table overlaps visible without using them as prose labels."""
    return sorted({t['id'] for t in tables if t.get('method') in _ALTERNATIVE_TABLE_METHODS | {'legacy_numeric_geometry'}
                   and t.get('bbox')
                   for s in spans if s['text'].strip()
                   and t['bbox'][0] <= (s['bbox'][0] + s['bbox'][2]) / 2 <= t['bbox'][2]
                   and t['bbox'][1] <= (s['bbox'][1] + s['bbox'][3]) / 2 <= t['bbox'][3]})


def narrative_candidates(pages: list[dict], evidence: list[dict], sections: list[dict]) -> None:
    """Add candidates to structured pages, preserving every nonblank source line."""
    all_elements = []
    for page, source in zip(pages, evidence[1:], strict=True):
        elements, pending = [], []
        envelopes = _table_envelopes(page['tables'])
        previous_key = None
        pending_kind, pending_tables = None, []

        def flush():
            if not pending:
                return
            spans = [s for _key, line in pending for s in line]
            elements.append({"id": f"p{source['page']}:narrative{len(elements)}", "kind": pending_kind,
                             "text": "\n".join("".join(s["text"] for s in line) for _key, line in pending),
                             "span_ids": [s["id"] for s in spans],
                             "source_lines": [list(key) for key, _line in pending],
                             "bbox": _bounds(spans), "font_size": median(s["size"] for s in spans),
                             "table_ids": pending_tables,
                             "candidate_table_ids": _candidate_table_ids(spans, page['tables']),
                             "method": "source_line_spacing_style_and_candidate_links", "review_status": "unreviewed",
                             "heading_context_verified": False, "heading_context_scope": "page"})
            pending.clear()

        for key, spans in _lines(source).items():
            if not "".join(s["text"] for s in spans).strip():
                flush()
                previous_key = None
                continue
            kind, table_ids = _line_kind(spans, page["tables"], envelopes)
            box = _bounds(spans)
            prior_box = _bounds(pending[-1][1]) if pending else None
            gap = prior_box is not None and box[1] - prior_box[3] > .7 * (prior_box[3] - prior_box[1])
            if pending and (key[0] != previous_key[0] or kind != pending_kind
                            or kind == "list_item_candidate"
                            or table_ids != pending_tables or gap):
                flush()
            pending_kind, pending_tables = kind, table_ids
            pending.append((key, spans))
            previous_key = key
        flush()
        page["narrative_elements"] = elements
        all_elements.extend((source, element) for element in elements)

    # Repeated margin text is still retained, but must not become a heading for
    # every following paragraph. Detect across this source revision only.
    repeated = defaultdict(set)
    for source, element in all_elements:
        box = element["bbox"]
        if box[1] < .14 * source["height"] or box[3] > .90 * source["height"]:
            repeated[" ".join(element["text"].split())].add(source["page"])
    headings = []
    current_section = None
    current_page = None
    for source, element in all_elements:
        text = " ".join(element["text"].split())
        box = element["bbox"]
        if box[1] > .88 * source["height"] and re.fullmatch(r"\(?\d{1,4}\)?", text):
            element["kind"] = "page_number_candidate"
        elif len(repeated[text]) >= 3 and (box[1] < .14 * source["height"] or box[3] > .90 * source["height"]):
            element["kind"] = "running_header_candidate" if box[1] < .14 * source["height"] else "running_footer_candidate"
        section = next((s for s in sections if s["page_start"] <= source["page"] <= s["page_end"]), None)
        section_number = section["number"] if section else None
        # Font sizes are comparable within a page, not across a report's cover,
        # auditor letter and statements. Keep section context separately; a
        # cross-page heading relationship requires continuation evidence.
        if section_number != current_section or source["page"] != current_page:
            headings.clear()
            current_section = section_number
            current_page = source["page"]
        element["section_candidate"] = ({k: section[k] for k in ("number", "title", "role")}
                                        if section else None)
        if element["kind"] == "heading_candidate":
            # Aligned Roman headings are siblings even if the PDF fonts differ
            # slightly. A new IV must not inherit the preceding III as a parent.
            if _ROMAN_HEADING.match(text):
                for index in range(len(headings) - 1, -1, -1):
                    previous = headings[index]
                    if (_ROMAN_HEADING.match(previous['text'])
                            and abs(previous['bbox'][0] - box[0]) <= element['font_size']):
                        del headings[index:]
                        break
            while headings and headings[-1]["font_size"] <= element["font_size"] + .1:
                headings.pop()
            element["heading_path"] = [{"id": h["id"], "text": " ".join(h["text"].split())} for h in headings]
            headings.append(element)
        elif element["kind"] in ("paragraph_candidate", "list_item_candidate", "mixed_text"):
            element["heading_path"] = [{"id": h["id"], "text": " ".join(h["text"].split())} for h in headings]
        else:
            element["heading_path"] = []


def verify_narrative(page: dict, source: dict) -> list[str]:
    if "narrative_elements" not in page:
        return []  # old revisions remain readable
    lines = _lines(source)
    expected = Counter(s["id"] for spans in lines.values() if "".join(s["text"] for s in spans).strip() for s in spans)
    actual, errors, ordered = Counter(), [], []
    identifiers = set()
    for element in page["narrative_elements"]:
        if element["id"] in identifiers:
            errors.append("duplicate_narrative_id")
        identifiers.add(element["id"])
        keys = [tuple(key) for key in element["source_lines"]]
        if not keys or any(key not in lines for key in keys):
            errors.append("unknown_narrative_source_line")
            continue
        spans = [s for key in keys for s in lines[key]]
        if (element.get('method') == 'source_line_spacing_style_and_candidate_links'
                and element.get('candidate_table_ids') != _candidate_table_ids(spans, page['tables'])):
            errors.append('narrative_candidate_table_membership_mismatch')
        actual.update(element["span_ids"])
        ordered.extend(element["span_ids"])
        if element["span_ids"] != [s["id"] for s in spans]:
            errors.append("narrative_span_mismatch")
        text = "\n".join("".join(s["text"] for s in lines[key]) for key in keys)
        if element["text"] != text or element["bbox"] != _bounds(spans):
            errors.append("narrative_text_or_geometry_mismatch")
    if actual != expected:
        errors.append("narrative_span_inventory_mismatch")
    expected_order = [s["id"] for spans in lines.values()
                      if "".join(s["text"] for s in spans).strip() for s in spans]
    if ordered != expected_order:
        errors.append("narrative_source_order_mismatch")
    return errors
