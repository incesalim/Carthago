"""Consolidation-basis classifier — the acquisition-time wrong-PDF guard.

Pure-text tests (no PDF / fitz): classify_report_basis takes front-matter text and
returns 'consolidated' / 'unconsolidated' / None. It keys on the DECLARATIVE title
phrase ("Konsolide [Olmayan] Finansal …" / "[Un]consolidated Financial …"), not raw
"konsolide" counts — the two regression tests below encode real failures a bare-count
version produced on the live archive (2026-07-18):
  * ALL-CAPS Turkish "KONSOLİDE OLMAYAN": İ (U+0130) lower()s to i+U+0307, so it
    scored ZERO against "konsolide" and 8 PASHA/TAKAS unconsolidated reports were
    mis-flagged as consolidated.
  * An unconsolidated report that names its consolidated group in the notes
    out-counted its own title (ODEA/TFKB).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_audit_reports import classify_report_basis  # noqa: E402


def test_turkish_consolidated():
    assert classify_report_basis(
        "31 Aralık 2023 Konsolide Finansal Tablolar. Konsolide Finansal rapor. "
        "Bağımsız denetim raporu — konsolide finansal tablolar.") == "consolidated"


def test_turkish_unconsolidated():
    assert classify_report_basis(
        "31 Aralık 2023 Konsolide Olmayan Finansal Tablolar. Konsolide Olmayan "
        "Finansal Tablolara İlişkin Bağımsız Denetim Raporu.") == "unconsolidated"


def test_english_consolidated():
    assert classify_report_basis(
        "Consolidated Financial Report 31 December 2023. Consolidated Financial "
        "Statements and independent auditor's report.") == "consolidated"


def test_english_unconsolidated_substring_trap():
    # "unconsolidated financial" contains "consolidated financial" — must not flip.
    assert classify_report_basis(
        "Unconsolidated Financial Report 31 December 2023. Unconsolidated "
        "Financial Statements.") == "unconsolidated"


def test_allcaps_turkish_unconsolidated_dotted_capital_i():
    # REGRESSION (PASHA/TAKAS): "İ" (U+0130) lowercases to i + combining dot; the
    # normaliser must strip it so ALL-CAPS titles still match "konsolide".
    assert classify_report_basis(
        "PASHA YATIRIM BANKASI A.Ş. 30 EYLÜL 2024 TARİHİNE AİT KONSOLİDE OLMAYAN "
        "FİNANSAL TABLOLAR VE BAĞIMSIZ DENETİM RAPORU. KONSOLİDE OLMAYAN FİNANSAL "
        "TABLOLAR.") == "unconsolidated"


def test_unconsolidated_survives_consolidated_group_notes():
    # REGRESSION (ODEA/TFKB): an unconsolidated report references the consolidated
    # group; the declarative phrase must still win over the incidental mention.
    assert classify_report_basis(
        "Konsolide Olmayan Finansal Tablolar. Konsolide Olmayan Finansal Tablolara "
        "ilişkin dipnotlar. Banka ayrıca konsolide finansal tablolarını ayrı olarak "
        "yayımlamaktadır.") == "unconsolidated"


def test_line_broken_title_still_matches():
    # get_text can return the cover title split across lines.
    assert classify_report_basis(
        "Konsolide\nOlmayan\nFinansal\nTablolar\nKonsolide Olmayan Finansal rapor"
    ) == "unconsolidated"


def test_garan_poisoned_url_case():
    # The bug that started this: a "…Unconsolidated…" URL that serves the
    # CONSOLIDATED report. The classifier sees consolidated; the caller compares to
    # the 'unconsolidated' key and blocks the upload.
    assert classify_report_basis(
        "Consolidated Financial Report. Consolidated Financial Statements of the "
        "Bank and its Financial Subsidiaries.") == "consolidated"


def test_ambiguous_returns_none():
    assert classify_report_basis("Financial report cover page, no basis phrase") is None


def test_single_mention_below_threshold_returns_none():
    assert classify_report_basis("... the consolidated financial group ...") is None


def test_empty_returns_none():
    assert classify_report_basis("") is None
