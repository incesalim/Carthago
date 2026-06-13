"""Unit tests for the TBB remote-vs-branch acquisition parser.

Builds a small in-memory grid reproducing the real ``müşteri edinim`` sheet's
3-panel layout (Gerçek Kişiler / Gerçek Kişi Tacirler / Tüzel Kişiler), so it
needs only pandas and skips cleanly in the minimal-deps CI lane (ruff + pytest +
lxml + requests), where pandas isn't installed.
"""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from src.tbb.acquisition import (  # noqa: E402
    _classify_method,
    _normalize_period,
    parse_frame,
)


def test_normalize_period_only_matches_clean_month_rows():
    assert _normalize_period("Mayıs 2021") == "2021-05"
    assert _normalize_period("Ocak 2023**") == "2023-01"        # trailing footnote star
    assert _normalize_period("Aralık 2025") == "2025-12"
    # Footnote / commentary rows carry trailing text → never parsed as data.
    assert _normalize_period("** Ocak 2023 itibarıyla tanımlar değişti") is None
    assert _normalize_period("Ocak 2023'ten itibaren değişen") is None
    assert _normalize_period("Toplam") is None


def test_classify_method():
    assert _classify_method("Şubeden - Sonuçlandırılan Müşteri Sayısı*") == "branch"
    assert _classify_method("Uzaktan - Başvuru Sayısı") == "remote_application"
    assert _classify_method("Uzaktan - Müşteri Temsilcisi ile Sonuçlandırılan Müşteri Sayısı") == "remote_rep"
    assert _classify_method("Toplu Edinim - Sonuçlandırılan Müşteri Sayısı*") == "bulk"
    # "Kurye" must win over the generic "Başvuru" branch.
    assert _classify_method("Uzaktan Başvuru - Kurye ile Sonuçlandırılan Müşteri Sayısı*") == "remote_courier"
    assert _classify_method("Online Başvuru - Kurye ile Sonuçlandırılan Müşteri Sayısı") == "remote_courier"
    assert _classify_method("Dönem") is None


def _grid():
    """Two panels (individual + legal), one method col each side a month col,
    plus a footnote row and a not-yet-reported ('-') legal cell."""
    return pd.DataFrame([
        # r0: panel titles at the panel start columns
        ["… Gerçek Kişiler", None, None, None, "… Tüzel Kişiler", None],
        [None, None, None, None, None, None],                                  # r1 blank
        # r2: method headers
        [None, "Şubeden - Sonuçlandırılan Müşteri Sayısı*",
               "Uzaktan - Müşteri Temsilcisi ile Sonuçlandırılan Müşteri Sayısı", None,
         None, "Şubeden - Sonuçlandırılan Müşteri Sayısı*"],
        # data rows (col0 = individual month, col4 = legal month)
        ["Mayıs 2021", 418838, 69760, None, "Mayıs 2021", "-"],
        ["Haziran 2021", 725093, 63829, None, "Haziran 2021", 1234],
        # footnote row — not data
        ["** Ocak 2023 itibarıyla tanımlar değişti", None, None, None, None, None],
    ])


def test_parse_frame_panels_methods_and_skips():
    stats = parse_frame(_grid())
    by = {(s.period, s.entity_type, s.method): s.value for s in stats}

    # Individual panel: branch + remote_rep for both months.
    assert by[("2021-05", "individual", "branch")] == 418838
    assert by[("2021-05", "individual", "remote_rep")] == 69760
    assert by[("2021-06", "individual", "branch")] == 725093

    # Legal panel: "-" (May) skipped, June present.
    assert ("2021-05", "legal", "branch") not in by
    assert by[("2021-06", "legal", "branch")] == 1234

    # Footnote row produced no rows.
    assert all(s.period in ("2021-05", "2021-06") for s in stats)
    # Entity types detected from the two panel titles only.
    assert {s.entity_type for s in stats} == {"individual", "legal"}
