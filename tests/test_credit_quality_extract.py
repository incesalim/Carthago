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
    _extract_npl_brsa_from_page,
    extract,
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


@pytest.mark.parametrize(
    ("gross", "provision", "net", "expected"),
    [
        ("4 13 74", "4 12 72", "- 1 2", (91, 88, 3)),  # HSBC 2026Q2
        ("90 28 -", "18 14 -", "72 14 -", (118, 32, 86)),  # COLENDI 2026Q2
        ("- - -", "- - -", "- - -", (0, 0, 0)),
    ],
)
def test_small_npl_closing_balances_do_not_require_thousands_separator(
    gross, provision, net, expected,
):
    """The Milyon TL switch made genuine gross/net rows short integers.

    A printed all-dash balance is nil; an absent balance remains missing.
    """
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "Cari Dönem",
        "Dönem İçinde İntikal (+) 900 28 -",
        f"Dönem Sonu Bakiyesi: 30 Haziran 2026 {gross}",
        f"Karşılık (-) {provision}",
        f"Bilançodaki Net Bakiyesi {net}",
    ])
    rows = _extract_npl_brsa_from_page(1, page)
    by_section = {r.section: r for r in rows}
    assert tuple(by_section[f"npl_brsa_{section}"].total
                 for section in ("gross", "provision", "net")) == expected


def test_small_npl_movement_is_not_promoted_to_missing_gross_balance():
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "Cari Dönem",
        "Dönem İçinde İntikal (+) 14 - 1",
        "Karşılık (-) 4 12 72",
    ])
    rows = _extract_npl_brsa_from_page(1, page)
    assert [r.section for r in rows] == ["npl_brsa_provision"]


def test_small_closing_balance_beats_large_negative_npl_movement():
    """TFKB prior-period closing used to lose to a signed transfer row."""
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "Önceki Dönem",
        "Diğer Donuk Alacak Hesaplarına Çıkış (-) (1,377) (922) -",
        "Dönem Sonu Bakiyesi (***) 753 662 983",
        "Özel Karşılık (-) (485) (402) (790)",
        "Bilançodaki Net Bakiyesi 268 260 193",
    ])
    rows = _extract_npl_brsa_from_page(1, page)
    gross = next(r for r in rows if r.section == "npl_brsa_gross")
    assert (gross.period_type, gross.stage1, gross.stage2, gross.stage3) == (
        "prior", 753, 662, 983)


def test_million_npl_columns_are_not_merged_as_split_digits():
    """TSKB's adjacent 48 and 3.834 are different BRSA groups."""
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "Cari Dönem",
        "Dönem Sonu Bakiyesi 48 3.834 1.805",
        "Karşılık (-) 29 2.377 1.805",
        "Bilançodaki Net Bakiyesi 19 1.457 -",
    ])
    rows = _extract_npl_brsa_from_page(1, page, unit_scale=1000)
    gross = next(r for r in rows if r.section == "npl_brsa_gross")
    assert (gross.stage1, gross.stage2, gross.stage3, gross.total) == (48, 3834, 1805, 5687)
    assert next(r for r in rows if r.section == "npl_brsa_net").total == 1476


def test_date_labelled_small_npl_close_is_scoped_to_provision():
    """ALNTF prints dates instead of opening/closing balance labels."""
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "31 Aralık 2025 249 27 397",
        "Dönem İçinde İntikal (+) 28 51 20",
        "30 Haziran 2026 40 290 337",
        "Karşılık (-) 32 196 166",
        "Bilançodaki Net Bakiyesi 8 94 171",
    ])
    rows = _extract_npl_brsa_from_page(1, page, unit_scale=1000)
    assert next(r for r in rows if r.section == "npl_brsa_gross").total == 667
    # An opening date elsewhere in the band is insufficient evidence of gross.
    incomplete = page.replace("30 Haziran 2026 40 290 337\n", "")
    assert all(r.section != "npl_brsa_gross"
               for r in _extract_npl_brsa_from_page(1, incomplete, unit_scale=1000))


def test_turkish_accounting_provision_without_minus_label():
    """EXIM encodes the deduction in each cell, without a (-) in the label."""
    page = "\n".join([
        "III. Grup IV. Grup V. Grup",
        "Dönem Sonu Bakiyesi 18 42 1.425",
        "Karşılık (18) (42) (1.425)",
        "Bilançodaki Net Bakiyesi - - -",
    ])
    rows = _extract_npl_brsa_from_page(1, page, unit_scale=1000)
    assert {r.section: r.total for r in rows} == {
        "npl_brsa_gross": 1485, "npl_brsa_provision": 1485, "npl_brsa_net": 0,
    }


def test_third_stage_provision_label_keeps_current_and_prior_separate():
    """TOMK's Stage-3 label belongs to the III/IV/V table, with two periods."""
    page = "\n".join([
        "III. Grup: IV. Grup: V. Grup:",
        "Cari Dönem",
        "Dönem İçinde İntikal (+) 1.274 46 6",
        "Dönem Sonu Bakiyesi 542 668 196",
        "Özel Kredi Karşılığı (3. Aşama) (-) 108 334 196",
        "Bilançodaki Net Bakiyesi 434 334 -",
        "III. Grup: IV. Grup: V. Grup:",
        "Önceki Dönem",
        "Dönem İçinde İntikal (+) 1.061 2 1",
        "Dönem Sonu Bakiyesi 338 264 26",
        "Özel Kredi Karşılığı (3. Aşama) (-) 67 132 26",
        "Bilançodaki Net Bakiyesi 271 132 -",
    ])
    rows = _extract_npl_brsa_from_page(1, page, unit_scale=1000)
    gross = {r.period_type: r.total for r in rows if r.section == "npl_brsa_gross"}
    provision = {r.period_type: r.total for r in rows if r.section == "npl_brsa_provision"}
    assert gross == {"current": 1406, "prior": 628}
    assert provision == {"current": 638, "prior": 225}


def test_million_stage2_subcolumns_are_not_merged_as_split_digits():
    page = "\n".join([
        "Standard Loans",
        "Loans Under Close Monitoring",
        "Current Period",
        "Total 117,607 4 1,425 -",
    ])
    rows = _extract_loans_by_stage_from_page(
        1, page, min_stage1=1000, unit_scale=1000)
    assert (rows[0].stage1, rows[0].stage2) == (117_607, 1429)


@pytest.mark.parametrize("unit, expected", [("millions", 120_923), ("thousands", None)])
def test_document_stage_admission_uses_printed_reporting_unit(tmp_path, unit, expected):
    """A wrapped section heading must not make the same loan book disappear
    merely because a filing switched from thousands to millions.
    """
    import fitz

    path = tmp_path / "stage-amounts.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "\n".join([
            f"Amounts expressed in {unit} of Turkish Lira",
            "Standard Loans",
            "Loans Under Close Monitoring",
            "Current Period",
            "Total 117,607 2,091 1,225 -",
        ]))
        doc.save(path)
    stages = [r for r in extract(path).rows if r.section == "loans_by_stage"]
    assert (stages[0].total if stages else None) == expected
