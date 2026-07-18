"""Consolidation-basis classifier — the acquisition-time wrong-PDF guard.

Pure-text tests (no PDF / fitz needed): classify_report_basis takes front-matter
text and returns 'consolidated' / 'unconsolidated' / None. The two languages each
hide a substring trap — TR "konsolide olmayan" contains "konsolide", EN
"unconsolidated" contains "consolidated" — so the counting must not double-map.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sync_audit_reports import classify_report_basis  # noqa: E402


def test_turkish_consolidated():
    t = ("31 Aralık 2023 Konsolide Finansal Tablolar. Konsolide bilanço. "
         "Konsolide gelir tablosu. Bu konsolide raporda...")
    assert classify_report_basis(t) == "consolidated"


def test_turkish_unconsolidated_substring_trap():
    # "konsolide olmayan" contains "konsolide" — must NOT read as consolidated.
    t = ("31 Aralık 2023 Konsolide Olmayan Finansal Tablolar. Konsolide Olmayan "
         "bilanço. Konsolide olmayan gelir tablosu ve bağımsız denetim raporu.")
    assert classify_report_basis(t) == "unconsolidated"


def test_english_consolidated():
    t = ("Consolidated Financial Report 31 December 2023. Consolidated balance "
         "sheet. Consolidated statement of profit or loss.")
    assert classify_report_basis(t) == "consolidated"


def test_english_unconsolidated_substring_trap():
    # "unconsolidated" contains "consolidated" — must NOT read as consolidated.
    t = ("Unconsolidated Financial Report 31 December 2023. Unconsolidated balance "
         "sheet. Unconsolidated statement of profit or loss.")
    assert classify_report_basis(t) == "unconsolidated"


def test_consolidated_survives_a_few_unconsolidated_notes():
    # A consolidated report references "konsolide olmayan" in a handful of
    # comparative notes; dominance (>=2x) must still call it consolidated
    # (the real KUVEYT case: ~163 konsolide vs ~4 konsolide olmayan).
    t = "konsolide " * 40 + " konsolide olmayan " * 3
    assert classify_report_basis(t) == "consolidated"


def test_garan_poisoned_url_case():
    # The bug: a "…_Unconsolidated_…pdf" URL that actually serves the CONSOLIDATED
    # report. The classifier sees consolidated content; the caller compares to the
    # key's 'unconsolidated' kind and blocks the upload.
    consolidated_content = "Consolidated Financial Report. " + "consolidated " * 20
    assert classify_report_basis(consolidated_content) == "consolidated"


def test_ambiguous_returns_none():
    assert classify_report_basis("Financial report cover page, no basis words") is None


def test_below_threshold_returns_none():
    # A single stray mention is not enough to act on (needs >=3 and >=2x).
    assert classify_report_basis("... the consolidated group ...") is None


def test_empty_returns_none():
    assert classify_report_basis("") is None
