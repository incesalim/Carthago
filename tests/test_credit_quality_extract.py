"""Credit-quality extractor unit tests — the two page-level readers that decide
whether a (bank, period) lands in the coverage matrix at all.

Both cases here were real coverage defects found on 2026-07-16 (see
docs/knowledge/audit-credit-quality-coverage-fix-2026-07-16.md):
  * the ₺1bn Stage-1 floor silently excluded every bank whose loan book is
    smaller than the floor (the new digital banks);
  * a '-' in the Toplam column was stored as a fabricated 0.0.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fitz")  # credit_quality is fitz-only

from src.audit_reports.credit_quality import (  # noqa: E402
    _extract_from_page,
    _extract_loans_by_stage_from_page,
)

# A ZIRAATD/TOMK-shaped §7.2 block: real section title, ₺308m book — two orders
# of magnitude below the default ₺1bn Stage-1 floor.
_SMALL_BANK_S12 = "\n".join([
    "7.2. Standart Nitelikli ve Yakın İzlemedeki (Birinci ve İkinci Grup Krediler) İle Yeniden",
    "Yapılandırılan Yakın İzlemedeki Kredilere İlişkin Bilgiler",
    "Cari Dönem Yakın İzlemedeki Krediler",
    "Nakdi Krediler Krediler Almayanlar Değişiklik Finansman",
    "İhtisas Dışı Krediler 308.232 248 - -",
    "Tüketici Kredileri 271.542 248 - -",
    "Kredi Kartları 36.690 - - -",
    "Toplam 308.232 248 - -",
])

# SKBNK 2024Q4 p89 — a §4 credit-risk table. Its column header says "Loans Under
# Follow-Up", so it matches the loose Stage-2 phrase, but it names no standard-
# loan portfolio. It sits 22 pages BEFORE the real §7.2 table, so admitting it
# would win the first-wins dedup and replace a ₺56bn Stage 1 with ₺893m.
_S4_RISK_TABLE = "\n".join([
    "c.4.3. Exposures provisioned against by major regions and sectors (cont'd)",
    "Current Period Loans Under Follow-Up Stage 3 Provisions Write-Offs",
    "Agricultural 100,894 79,829 -",
    "Manufacturing 167,171 88,551 -",
    "Construction 226,673 218,514 -",
    "Total 893,026 622,569 -",
])


def test_small_bank_below_floor_is_skipped_by_default():
    """Default pass keeps the ₺1bn floor — a ₺308m book yields nothing."""
    assert _extract_loans_by_stage_from_page(1, _SMALL_BANK_S12) == []


def test_small_bank_extracted_by_section_title_fallback():
    """The fallback drops the floor and anchors on the §7.2 title instead."""
    rows = _extract_loans_by_stage_from_page(
        1, _SMALL_BANK_S12, require_section_title=True, min_stage1=1)
    assert len(rows) == 1
    r = rows[0]
    assert r.section == "loans_by_stage"
    assert r.stage1 == 308_232
    assert r.stage2 == 248
    assert r.total == 308_480  # foots to the balance-sheet loan line


def test_s4_follow_up_table_rejected_even_without_the_floor():
    """The §4 risk table names no standard-loan portfolio, so the section-title
    anchor rejects it on structure — the floor is not what keeps it out."""
    assert _extract_loans_by_stage_from_page(
        1, _S4_RISK_TABLE, require_section_title=True, min_stage1=1) == []


def test_nil_total_row_is_not_rescued():
    """A genuinely empty §7.2 table (TOMK's nil prior period) stays out rather
    than landing as a row of zeros."""
    nil = _SMALL_BANK_S12.replace("Toplam 308.232 248 - -", "Toplam - - - -")
    assert _extract_loans_by_stage_from_page(
        1, nil, require_section_title=True, min_stage1=1) == []


# --- the dash-in-Toplam case (DUNYAK 2026Q1 note 8.4) ----------------------
def _lease_ecl_page(total_cell: str) -> str:
    return "\n".join([
        "8.4. Finansal kiralama alacaklarının TFRS9'a göre karşılık değişimleri:",
        "1. Aşama 2. Aşama 3. Aşama Toplam",
        "Önceki dönem sonu bakiye 2.234 9.331 - 11.565",
        "Dönem İçi İlave 15.289 760 - 16.049",
        f"Dönem Sonu Bakiyesi 10.091 17.523 - {total_cell}",
    ])


def test_dash_total_with_nonnil_stages_is_not_disclosed():
    """A nil total beside non-nil stages is arithmetically impossible, so the
    bank omitted it — record None, never a fabricated 0."""
    rows = _extract_from_page(1, _lease_ecl_page("-"))
    assert len(rows) == 1
    r = rows[0]
    assert (r.stage1, r.stage2, r.stage3) == (10_091, 17_523, 0)
    assert r.total is None


def test_stated_total_is_kept_verbatim():
    """The same row with the total the bank should have printed stays a value."""
    rows = _extract_from_page(1, _lease_ecl_page("27.614"))
    assert rows[0].total == 27_614


def test_all_nil_row_keeps_zero_total():
    """A dash total whose stages are ALSO nil is a genuine zero, not an
    omission — it must stay 0.0 rather than degrade to None."""
    page = "\n".join([
        "1. Aşama 2. Aşama 3. Aşama Toplam",
        "Dönem Sonu Bakiyesi - - - -",
    ])
    rows = _extract_from_page(1, page)
    assert len(rows) == 1
    assert rows[0].total == 0.0
