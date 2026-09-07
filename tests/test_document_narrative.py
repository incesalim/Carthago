import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations, paragraph_digest
from src.audit_reports.document_narrative import narrative_candidates, verify_narrative


def source_page(number=1):
    # One PDF block deliberately contains headings, multiple paragraphs, blank
    # lines, and table text. Expected wording is authored independently here.
    lines = [("Qualified conclusion", 16), (" ", 0),
             ("Nothing indicates that 1,000 and 1,000", 0), ("are not consistent with the report.", 0),
             ("", 0), ("Other requirements", 2), ("Second passage.", 0),
             ("a) First condition", 0), ("b) Second condition", 0), ("Table content", 0)]
    return {"page": number, "height": 800, "spans": [
        {"id": f"p{number}:s{i}", "block": 0, "line": i, "text": text,
         "bbox": [40, 150 + i * 12, 230, 160 + i * 12], "size": 10, "flags": flags}
        for i, (text, flags) in enumerate(lines)]}


@pytest.fixture
def narrative():
    source = source_page()
    page = {"page": 1, "tables": [{"id": "table1", "bbox": [30, 256, 250, 272]}]}
    evidence = [{"source": {"pdf_sha256": "a" * 64}}, source]
    narrative_candidates([page], evidence, [])
    structure = {"source": evidence[0]["source"], "pages": [page]}
    annotation = {"pdf_sha256": "a" * 64, "cases": [{
        "kind": "narrative", "id": "opinion_negation", "page": 1,
        "text_sha256": paragraph_digest("Nothing indicates that 1,000 and 1,000 are not consistent with the report."),
        "heading_path": ["Qualified conclusion"], "bbox": [39, 173, 231, 197]}]}
    return structure, evidence, annotation


def test_paragraphs_headings_lists_and_table_text_preserve_source(narrative):
    structure, evidence, annotation = narrative
    page = structure["pages"][0]
    elements = page["narrative_elements"]
    assert [e["kind"] for e in elements] == [
        "heading_candidate", "paragraph_candidate", "heading_candidate", "paragraph_candidate",
        "list_item_candidate", "list_item_candidate", "table_text"]
    assert elements[1]["text"] == "Nothing indicates that 1,000 and 1,000\nare not consistent with the report."
    assert elements[3]["heading_path"][0]["text"] == "Other requirements"
    assert elements[-1]["table_ids"] == ["table1"]
    assert elements[-1]["heading_path"] == []
    assert all(not e["heading_context_verified"] for e in elements)
    assert verify_narrative(page, evidence[1]) == []
    assert check_annotations(structure, evidence, annotation)["passed"]


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "negation", "swap_lines", "swap_elements", "empty_lines", "duplicate_id"])
def test_source_accounting_detects_damaged_narrative(narrative, mutation):
    structure, evidence, _annotation = narrative
    page = copy.deepcopy(structure["pages"][0])
    elements = page["narrative_elements"]
    if mutation == "drop":
        elements.pop(1)
    elif mutation == "duplicate":
        elements.append(copy.deepcopy(elements[1]))
    elif mutation == "negation":
        elements[1]["text"] = elements[1]["text"].replace("not ", "")
    elif mutation == "swap_lines":
        # Keep all text/spans and make the altered element internally consistent.
        e = elements[1]
        e["source_lines"].reverse()
        e["span_ids"].reverse()
        e["text"] = "\n".join(reversed(e["text"].splitlines()))
    elif mutation == "swap_elements":
        elements[1], elements[3] = elements[3], elements[1]
    elif mutation == "empty_lines":
        elements[1]["source_lines"] = []
    else:
        elements[1]["id"] = elements[0]["id"]
    assert verify_narrative(page, evidence[1])


@pytest.mark.parametrize("mutation", ["negation", "heading", "false_heading_reference", "same_text_wrong_source", "duplicate_paragraph"])
def test_benchmark_requires_complete_paragraph_and_real_heading(narrative, mutation):
    structure, evidence, annotation = narrative
    changed = copy.deepcopy(structure)
    elements = changed["pages"][0]["narrative_elements"]
    if mutation == "negation":
        elements[1]["text"] = elements[1]["text"].replace("not ", "")
    elif mutation == "heading":
        elements[1]["heading_path"][0]["text"] = "Unqualified conclusion"
    elif mutation == "false_heading_reference":
        elements[1]["heading_path"][0]["id"] = elements[2]["id"]
    elif mutation == "same_text_wrong_source":
        elements[1]["span_ids"] = elements[3]["span_ids"]
    else:
        elements.append(copy.deepcopy(elements[1]))
    assert not check_annotations(changed, evidence, annotation)["passed"]


def test_repeated_margin_text_and_page_numbers_do_not_become_heading_context():
    sources, pages = [], []
    for number in (1, 2, 3):
        source = {"page": number, "height": 800, "spans": [
            {"id": f"p{number}:s{i}", "block": i, "line": 0, "text": text,
             "bbox": [40, y, 200, y + 10], "size": 10, "flags": flags}
            for i, (text, y, flags) in enumerate([("Bank audit report", 40, 16),
                                                  ("Body text.", 200, 0), (str(number), 750, 0)])]}
        sources.append(source)
        pages.append({"page": number, "tables": []})
    narrative_candidates(pages, [{}] + sources, [])
    for page, source in zip(pages, sources, strict=True):
        assert [e["kind"] for e in page["narrative_elements"]] == [
            "running_header_candidate", "paragraph_candidate", "page_number_candidate"]
        assert page["narrative_elements"][1]["heading_path"] == []
        assert not verify_narrative(page, source)


def test_cover_typography_does_not_leak_into_the_following_audit_opinion(narrative):
    _structure, evidence, annotation = narrative
    cover = {"page": 1, "height": 800, "spans": [
        {"id": "cover", "block": 0, "line": 0, "text": "Bank cover title",
         "bbox": [40, 200, 400, 250], "size": 36, "flags": 16}]}
    opinion = copy.deepcopy(evidence[1])
    opinion["page"] = 2
    pages = [{"page": 1, "tables": []}, {"page": 2, "tables": []}]
    combined = [evidence[0], cover, opinion]
    narrative_candidates(pages, combined, [])
    changed = copy.deepcopy(annotation)
    changed["cases"][0]["page"] = 2
    structure = {"source": evidence[0]["source"], "pages": pages}
    assert check_annotations(structure, combined, changed)["passed"]
    assert pages[1]["narrative_elements"][1]["heading_path"] == [
        {"id": "p2:narrative0", "text": "Qualified conclusion"}]
    assert pages[1]["narrative_elements"][1]["heading_context_scope"] == "page"


@pytest.mark.parametrize('alternative', [
    {'method': 'horizontal_rule_cells'},
    {'method': 'segmented_rules_and_source_lines'},
    {'method': 'legacy_numeric_geometry', 'word_view': 'positioned_text'},
])
def test_speculative_table_rectangles_cannot_split_source_paragraphs(narrative, alternative):
    structure, evidence, annotation = narrative
    before = copy.deepcopy(structure['pages'][0]['narrative_elements'])
    # Only the second line is overlapped: bbox classification used to split
    # the sentence and sever its heading context even though no prose changed.
    structure['pages'][0]['tables'].append({'id': 'alternative', 'bbox': [30, 184, 250, 198], **alternative})
    narrative_candidates(structure['pages'], evidence, [])
    after = copy.deepcopy(structure['pages'][0]['narrative_elements'])
    assert after[1]['candidate_table_ids'] == ['alternative']
    for element in after:
        element['candidate_table_ids'] = []
    assert after == before
    assert check_annotations(structure, evidence, annotation)['passed']


def test_albrk_source_paragraph_and_sibling_heading_survive_real_table_alternatives():
    fixtures = Path(__file__).parent / 'fixtures'
    fixture = json.loads((fixtures / 'document_narrative_albrk_table_overlap.json').read_text(encoding='utf-8'))
    evidence = [{'source': fixture['source']}, fixture['source_page']]
    page = {'page': 8, 'tables': fixture['tables']}
    tables = copy.deepcopy(page['tables'])
    narrative_candidates([page], evidence, fixture['sections'])
    annotation = json.loads((fixtures / 'document_annotations/albrk_2026q1_consolidated.json').read_text(encoding='utf-8'))
    annotation['cases'] = [c for c in annotation['cases'] if c['kind'] == 'narrative']
    assert len(annotation['cases']) == 1
    result = check_annotations({'source': fixture['source'], 'pages': [page]}, evidence, annotation)
    assert result['passed'], result
    assert page['tables'] == tables  # Alternatives remain available for table review.
    assert verify_narrative(page, fixture['source_page']) == []


@pytest.mark.parametrize('indent,expected', [(40, []), (70, ['III. Previous topic'])])
def test_roman_heading_siblings_use_alignment_while_nested_headings_keep_the_parent(indent, expected):
    source = {'page': 1, 'height': 800, 'spans': [
        {'id': 0, 'block': 0, 'line': 0, 'text': 'III. Previous topic',
         'bbox': [40, 100, 250, 112], 'size': 12, 'flags': 16},
        {'id': 1, 'block': 1, 'line': 0, 'text': 'IV. Current topic',
         'bbox': [indent, 140, 250, 150], 'size': 10, 'flags': 16},
        {'id': 2, 'block': 2, 'line': 0, 'text': 'Current passage.',
         'bbox': [indent, 160, 250, 170], 'size': 10, 'flags': 0},
    ]}
    page = {'page': 1, 'tables': []}
    narrative_candidates([page], [{}, source], [])
    assert [h['text'] for h in page['narrative_elements'][1]['heading_path']] == expected
    assert [h['text'] for h in page['narrative_elements'][2]['heading_path']] == [*expected, 'IV. Current topic']
