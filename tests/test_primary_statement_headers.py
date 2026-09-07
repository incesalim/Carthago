"""Reporting dates are source headings, never financial rows or values."""
import json
from pathlib import Path

import pytest

from src.audit_reports.extractor import _fitz_merge_rows, _parse_rows


@pytest.mark.parametrize("page,financial_label,first_value", [
    ("13", "KAR PAYI GELİRLERİ", 112338),
    ("16", "Bankacılık Faaliyet Konusu", 62874),
])
def test_retained_source_page_does_not_turn_2023_into_amounts_202_and_3(page, financial_label, first_value):
    source = json.loads((Path(__file__).parent / "fixtures/primary_statement_headers_tomk.json").read_text(encoding="utf-8"))
    # These real page headers previously became ('30 EYLÜL', [202, 3]).
    rows = _parse_rows(_fitz_merge_rows(source["pages"][page], 2), 2)
    assert not any(label.startswith("30 EYLÜL") for label, _ in rows)
    assert any(financial_label in label and values[0] == first_value for label, values in rows)


@pytest.mark.parametrize("header", [
    "30 EYLÜL 2023 TARİHİNDE SONA EREN HESAP DÖNEMİNE AİT",
    "31 ARALIK 2022 TARİHİ İTİBARIYLA",
    "31 December 2022", "30 SEPTEMBER 2023", "(31 December 2022)",
])
def test_calendar_header_is_excluded_before_numeric_tokenization(header):
    assert _parse_rows(header, 2) == []


def test_financial_rows_with_dates_or_month_names_are_kept():
    rows = _parse_rows("I. December interest income 100 90\n1.1 September fees 30 20\n"
                       "II. Balance at 31 December 2022 100 90", 2)
    assert len(rows) == 3
    assert [values for _, values in rows] == [[100, 90], [30, 20], [100, 90]]
