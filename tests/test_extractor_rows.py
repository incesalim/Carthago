"""Regression tests for _parse_rows over real-world phantom/garbage lines.

Skipped under CI's minimal deps (extractor imports pdfplumber at module
level); runs locally and in any env with full requirements.
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.extractor import _parse_rows  # noqa: E402

VALUES_6 = "123.456 789 124.245 100.000 500 100.500"


def test_qnbfb_squished_page_header_rejected():
    # The two dates fragment into 6 numeric tokens; before the BALANCE\s*SHEET
    # filter this line was admitted as a roman-I data row with garbage values.
    text = "I. BALANCESHEET-ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(text, 6) == []
    text2 = "I. CONSOLIDATEDBALANCESHEET–ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(text2, 6) == []


def test_skbnk_leading_dipnot_with_dashes_not_stored_as_value():
    # 5 dashes + the "(14)" dipnot = 6 tokens; (14) used to become tl=-14.
    text = "VII. INVESTMENT PROPERTY (Net) (14) - - - - -"
    assert _parse_rows(text, 6) == []  # below n_cols after dipnot drop → skip


def test_leading_dipnot_with_full_columns_kept():
    text = f"VII. INVESTMENT PROPERTY (Net) (14) {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    label, vals = rows[0]
    assert vals[0] == 123456.0 and -14 not in vals


def test_ecl_row_with_dipnot_still_parses():
    text = "2.4 Expected Credit Losses (-) (6) 3.901.206 2.639.305 6.540.511 3.514.226 2.543.524 6.057.750"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    _, vals = rows[0]
    assert vals[2] == 6540511.0 and vals[5] == 6057750.0


def test_plain_row_unaffected():
    text = f"1.1.2 Banks {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][2] == 124245.0


def test_squished_off_balance_rows_survive_header_filter():
    # ISCTR off-balance: real data rows that contain "BALANCESHEET" squished —
    # the header filter must not eat them (it did, briefly, between the QNBFB
    # fix and the Phase-3 batch-3 gate catching a 12-row loss).
    a = f"A. OFF-BALANCESHEETCONTINGENCIESandCOMMITMENTS(I+II+III) V-III {VALUES_6}"
    total = f"TOTALOFF-BALANCESHEETCOMMITMENTS(A+B) {VALUES_6}"
    tr = f"A. BİLANÇO DIŞI YÜKÜMLÜLÜKLER (I+II+III) {VALUES_6}"
    assert len(_parse_rows(a, 6)) == 1
    assert len(_parse_rows(total, 6)) == 1
    assert len(_parse_rows(tr, 6)) == 1
    # …while the page header stays rejected
    hdr = "I. BALANCESHEET-ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(hdr, 6) == []
