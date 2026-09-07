"""Literal source discrepancies remain open; forged references cannot pass."""
import copy
import json
from pathlib import Path

import pytest

from src.audit_reports.document_benchmark import check_annotations, check_source_annotations
from src.audit_reports.document_content_review import validate_content_review

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def review():
    captured = json.loads((FIXTURES / "document_content_review_tomk.json").read_text(encoding="utf-8"))
    annotation = json.loads((FIXTURES / "document_annotations/tomk_2023q3_solo.json").read_text(encoding="utf-8"))
    cases = [c for c in annotation["cases"] if c.get("kind") == "source_review"]
    return captured, annotation, cases


def test_three_real_report_differences_keep_all_seven_source_passages(review):
    captured, _, cases = review
    pages = {p["page"]: p for p in captured["pages"]}
    assert len(cases) == 3 and sum(len(c["points"]) for c in cases) == 7
    assert all(validate_content_review(c, pages) for c in cases)
    assert ["93,93" in cases[0]["points"][0]["source_text"],
            "93,75" in cases[0]["points"][1]["source_text"],
            "93,90" in cases[0]["points"][2]["source_text"]] == [True] * 3


@pytest.mark.parametrize("mutation", ["figure", "page", "span", "duplicate_span", "order", "bbox", "page_hash", "page_bytes", "approval", "resolved"])
def test_corrupt_or_overclaimed_content_reviews_fail(review, mutation):
    captured, _, cases = review
    case = copy.deepcopy(cases[0])
    pages = {p["page"]: p for p in captured["pages"]}
    point = case["points"][0]
    if mutation == "figure":
        point["source_text"] = point["source_text"].replace("93,93", "93,75")
    elif mutation == "page":
        point["page"] = 28
    elif mutation == "span":
        point["source_span_ids"][0] = 29
    elif mutation == "duplicate_span":
        point["source_span_ids"].append(point["source_span_ids"][-1])
    elif mutation == "order":
        point["source_span_ids"].reverse()
    elif mutation == "bbox":
        point["bbox"][2] = 130
    elif mutation == "page_hash":
        point["source_page_artifact_sha256"] = "0" * 64
    elif mutation == "page_bytes":
        pages[26]["spans"][30]["text"] += "changed"
    elif mutation == "approval":
        case["semantic_verification"] = "verified"
    else:
        case["status"] = "resolved"
    assert not validate_content_review(case, pages)


def test_source_only_benchmark_preserves_notes_in_receipt_payload(review, tmp_path):
    captured, annotation, cases = review
    annotation["cases"] = cases
    (tmp_path / "review.json").write_text(json.dumps(annotation), encoding="utf-8")
    evidence = [{"source": captured["source"]}, *captured["pages"]]
    result = check_source_annotations(evidence, tmp_path)
    assert result["status"] == "passed"
    assert result["checks"][0]["content_reviews"] == cases
    evidence[0]["source"]["pdf_sha256"] = "0" * 64
    assert check_source_annotations(evidence, tmp_path)["status"] == "source_revision_unannotated"


def test_wrong_source_does_not_return_content_reviews(review):
    captured, annotation, cases = review
    annotation["cases"] = cases
    evidence = [{"source": captured["source"]}, *captured["pages"]]
    annotation["pdf_sha256"] = "0" * 64
    result = check_annotations({"source": captured["source"]}, evidence, annotation)
    assert not result["passed"] and "content_reviews" not in result
