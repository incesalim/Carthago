"""A disclosed inconsistent row must survive extraction for validation to inspect."""
from dataclasses import asdict, fields
import json
from pathlib import Path

import pytest

from src.audit_reports import equity_change as EC
from src.audit_reports.validator import check_equity_change

FIXTURES = Path(__file__).parent / "fixtures"


def _extract(monkeypatch, index):
    source = json.loads((FIXTURES / "equity_source_completeness_tomk.json").read_text(encoding="utf-8"))[index]
    monkeypatch.setattr(EC, "_fitz_page_lines", lambda *_: source["block_lines"])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: source["text"])
    monkeypatch.setattr(EC, "_fitz_dense_page_lines", lambda *_: source["dense_lines"])
    monkeypatch.setattr(EC, "_fitz_wrapped_digit_page_lines", lambda *_: [])
    monkeypatch.setattr(EC, "_fitz_sparse_page_grid", lambda *_: None)
    monkeypatch.setattr(EC, "_block1_period_for_split", lambda *_: "prior")
    return EC._parse_equity_page("source-fixture.pdf", source["source_page"], "current", source["n_cols"])


def test_reviewed_complete_statement_matches_every_financial_cell_and_label(monkeypatch):
    rows = _extract(monkeypatch, 0)
    annotation = json.loads((FIXTURES / "document_annotations/tomk_2023q3_solo.json").read_text(encoding="utf-8"))
    case = next(c for c in annotation["cases"] if c["id"] == "complete_equity_change_with_six_numbered_columns")
    gold = case["reviewed_grid"]["rows"][3:]
    assert len(rows) == len(gold) == 17
    columns = [f.name for f in fields(EC.EquityChangeRow)][5:]
    for actual, expected in zip(rows, gold):
        assert [getattr(actual, c) for c in columns] == [EC.parse_num(c["text"]) for c in expected[1:]]
        # Separating the hierarchy does not discard any source label text.
        label = f"{actual.hierarchy} {actual.name}".strip()
        assert label.rstrip('.') == expected[0]["text"].rstrip('.')


def test_source_discrepancy_is_retained_and_fails_validation(monkeypatch):
    # PDF p14: current OCI closing visibly prints +1,288, while opening -1,099
    # and movement -189 imply -1,288. The source itself must remain reviewable.
    rows = _extract(monkeypatch, 1)
    assert len(rows) == 34
    assert [r.period_type for r in rows] == ["prior"] * 17 + ["current"] * 17
    closing = rows[-1]
    assert closing.hierarchy == "" and closing.name.endswith("+X+XI)")
    assert closing.oci_not_reclassified_2 == 1288
    assert closing.total_equity == 1571104
    values = [{**asdict(r), "item_name": r.name, "item_order": r.order} for r in rows]
    result = check_equity_change(values)
    assert any(f["check"] == "eq_row_sum" for f in result.failures)
    assert not any(f["check"] == "eq_closing_missing" for f in result.failures)


@pytest.mark.parametrize("line", [
    "II. TMS 8 Uyarınca Yapılan Düzeltmeler " + "- " * 14,
    "III. Yeni Bakiye (I+II) " + "- " * 14,
    "Dönem Sonu Bakiyesi (III+IV+X+XI) " + "- " * 14,
])
def test_complete_labels_keep_standards_and_formula_punctuation(line):
    _, label = EC._eq_split(line)
    assert "TMS 8" in label or label.endswith(")")


def test_incomplete_vectors_still_need_the_existing_arithmetic_gate():
    assert EC._try_fit([1000] + [0] * 10 + [500], 14) is None
