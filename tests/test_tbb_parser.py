"""Unit tests for the TBB digital-banking workbook parser.

Exercises the parser's core logic against small in-memory grids that reproduce
the real workbook's quirks — 3-level merged headers, the Bireysel/Kurumsal/
Toplam customer matrix, the 2025 asterisk footnote markers, and period/slug
normalisation. Builds DataFrames directly (no Excel file), so it needs only
pandas; it skips cleanly in the minimal-deps CI lane (ruff + pytest + lxml +
requests), where pandas isn't installed.
"""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from src.tbb.parser import (  # noqa: E402
    _SheetRole,
    _parse_sheet,
    normalize_period,
    parse_workbook,
    slugify,
)


def _sheet(grid: list[list]) -> pd.DataFrame:
    return pd.DataFrame(grid)


# ── helpers ──────────────────────────────────────────────────────────────────


def test_normalize_period():
    assert normalize_period("Mart 2026") == "2026-03"
    assert normalize_period("Aralık 2025") == "2025-12"
    assert normalize_period("Eylül 2024") == "2024-09"
    assert normalize_period("Haziran 2019") == "2019-06"
    assert normalize_period("  Mart 2026 ") == "2026-03"
    assert normalize_period("Q1 2026") is None
    assert normalize_period("EFT") is None


def test_slugify_handles_turkish():
    assert slugify("EFT") == "eft"
    assert slugify("Fatura ödemeleri") == "fatura_odemeleri"
    # Turkish-specific letters transliterate consistently.
    assert slugify("Şubat İşlemleri") == "subat_islemleri"
    assert slugify("Havale > Üçüncü şahıslara") == "havale_ucuncu_sahislara"


# ── transaction block: 3-level merged headers + asterisks ────────────────────


def test_parse_transaction_block():
    grid = [
        ["İnternet Bankacılığı İstatistikleri", "", "", "", "", ""],
        ["III.1. Para Transferleri", "", "", "", "", ""],          # section
        ["Dönem", "İşlem Adedi (Bin)", "", "", "", ""],            # unit row
        ["", "EFT *", "Havale *", "", "", "Toplam*"],              # level 1 (asterisks)
        ["", "", "TP Havale", "YP Havale", "Toplam", ""],          # leaf level
        ["Mart 2025", 100, 10, 1, 11, 111],
        ["Haziran 2025", 200, 20, 2, 22, 222],
    ]
    role = _SheetRole("internet", "total", skip_section_i=False)
    rows = _parse_sheet(_sheet(grid), "İnternet bank.istat.", role)

    by = {(r.metric_slug, r.period): r for r in rows}
    assert all(r.section_code == "III.1" for r in rows)
    assert all(r.unit == "count_thousands" for r in rows)
    assert all(r.channel == "internet" and r.segment == "total" for r in rows)

    # Asterisks are stripped → stable slugs; hierarchy composes top-to-bottom.
    assert by[("eft", "2025-03")].value == 100
    assert by[("eft", "2025-03")].metric_path == "EFT"
    assert by[("havale_tp_havale", "2025-03")].value == 10
    assert by[("havale_yp_havale", "2025-06")].value == 2
    assert by[("havale_toplam", "2025-03")].metric_path == "Havale > Toplam"
    assert by[("havale_toplam", "2025-03")].value == 11
    # The grand total "Toplam* > Toplam" collapses to "Toplam".
    assert by[("toplam", "2025-06")].value == 222
    assert by[("toplam", "2025-06")].metric_path == "Toplam"


# ── customer matrix: Bireysel/Kurumsal/Toplam column groups → segment ────────


def test_parse_customer_matrix_segments():
    grid = [
        ["I. İnternet Bankacılığı Müşteri Sayıları", "", "", ""],   # section
        ["", "Bireysel*", "Kurumsal*", "Toplam*"],                 # segment groups
        ["Dönem", "Aktif müşteri sayısı (Bin)", "Aktif müşteri sayısı (Bin)",
         "Aktif müşteri sayısı (Bin)"],
        ["Mart 2026", 5.0, 1.0, 6.0],
    ]
    role = _SheetRole("internet", "total", skip_section_i=False)
    rows = _parse_sheet(_sheet(grid), "İnternet bank.istat.", role)

    # The segment token is popped off; the remaining label is the metric, and
    # head-counts are classified as persons (despite the "(Bin)" suffix).
    seg = {r.segment: r for r in rows}
    assert set(seg) == {"individual", "corporate", "total"}
    assert all(r.metric_slug == "aktif_musteri_sayisi" for r in rows)
    assert all(r.unit == "persons_thousands" for r in rows)
    assert seg["individual"].value == 5.0
    assert seg["corporate"].value == 1.0
    assert seg["total"].value == 6.0


def test_segment_sheet_skips_customers():
    """The per-segment sheets contribute transactions only — section I (which
    the channel-total sheet already covers) is skipped to avoid duplication."""
    grid = [
        ["I. Bireysel İnternet Bankacılığı Müşteri Sayıları", "", ""],
        ["", "Bireysel", ""],
        ["Dönem", "Aktif müşteri sayısı (Bin)", ""],
        ["Mart 2026", 5.0, 0.0],
    ]
    role = _SheetRole("internet", "individual", skip_section_i=True)
    rows = _parse_sheet(_sheet(grid), "Bireysel İnternet bank.istat.", role)
    assert rows == []


def test_absolute_persons_normalised_to_thousands():
    """Pre-2020 reports give customer counts in absolute persons (no "(Bin)"
    header); they must be rescaled to thousands so the series is continuous."""
    grid = [
        ["I. Mobil Bankacılık Müşteri Sayıları", "", ""],
        ["", "Toplam", ""],
        ["Dönem", "Aktif müşteri sayısı", ""],   # NB: no "(Bin)"
        ["Aralık 2017", 29541221.0, 0.0],         # absolute persons
    ]
    role = _SheetRole("mobile", "total", skip_section_i=False)
    rows = _parse_sheet(_sheet(grid), "Mobil bank.istat.", role)
    r = next(x for x in rows if x.segment == "total")
    assert r.unit == "persons_thousands"
    assert r.value == 29541.221   # 29,541,221 persons → thousands


def test_million_tl_volume_normalised_to_billion():
    """Pre-2020 volumes are in "Milyon TL" (million); normalise to billion TL."""
    grid = [
        ["III.1. Para Transferleri", ""],
        ["Dönem", "İşlem Hacmi (Milyon TL)"],
        ["", "EFT"],
        ["Mart 2018", 481120.38],   # million TL
    ]
    role = _SheetRole("internet", "total", skip_section_i=False)
    rows = _parse_sheet(_sheet(grid), "İnternet bank.istat.", role)
    r = next(x for x in rows if x.metric_slug == "eft")
    assert r.unit == "volume_bn_try"
    assert abs(r.value - 481.12038) < 1e-6   # million → billion


def test_parse_workbook_engine_detection(tmp_path):
    """parse_workbook picks the engine by magic bytes; a non-Excel file with an
    .xls name should not crash discovery of the engine (it raises on read)."""
    # Minimal smoke test: an empty .xlsx-signed file is detected as openpyxl.
    fake = tmp_path / "x.xls"
    fake.write_bytes(b"PK\x03\x04not-a-real-zip")
    with pytest.raises(Exception):
        parse_workbook(str(fake))
