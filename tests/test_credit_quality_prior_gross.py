"""Small NPL borrower rows need complete source evidence before becoming totals."""
import pytest

pytest.importorskip("fitz")

from src.audit_reports.credit_quality import _extract_npl_brsa_from_page  # noqa: E402


def _block(period="Önceki", gross="29", provision="24", net="5"):
    return "\n".join([
        f"{period} Dönem (Net) - - {net}",
        f"Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt) - - {gross}",
        f"Özel Karşılık Tutarı (-) - - {provision}",
        f"Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Net) - - {net}",
        "Bankalar (Brüt) - - -",
        "Özel Karşılık Tutarı (-) - - -",
        "Bankalar (Net) - - -",
        "Diğer Kredi ve Alacaklar (Brüt) - - -",
        "Özel Karşılık Tutarı (-) - - -",
        "Diğer Kredi ve Alacaklar (Net) - - -",
    ])


def _gross(page):
    rows = _extract_npl_brsa_from_page(
        67, "III. Grup IV. Grup V. Grup\n" + page, unit_scale=1000)
    return {row.period_type: row for row in rows if row.section == "npl_brsa_gross"}


def test_complete_borrower_note_fills_small_prior_gross_without_period_swap():
    # ICBC 2026Q2 consolidated p67; all three borrower categories are printed.
    rows = _gross(_block("Cari", "29", "25", "4") + "\n" + _block())
    assert set(rows) == {"current", "prior"}
    assert rows["prior"].total == 29
    assert (rows["prior"].stage1, rows["prior"].stage2, rows["prior"].stage3) == (0, 0, 29)
    assert rows["current"].total == 29


@pytest.mark.parametrize("change", [
    "missing_gross", "unknown_cell", "missing_category", "broken_identity", "wrong_parent",
])
def test_incomplete_or_inconsistent_borrower_note_keeps_gross_missing(change):
    block = _block()
    if change == "missing_gross":
        block = block.replace(
            "Gerçek ve Tüzel Kişilere Kullandırılan Krediler (Brüt) - - 29\n", "")
    elif change == "unknown_cell":
        block = block.replace("(Brüt) - - 29", "(Brüt) - unknown 29")
    elif change == "missing_category":
        block = block.replace("Bankalar (Brüt) - - -\n", "")
    elif change == "broken_identity":
        block = block.replace("(Brüt) - - 29", "(Brüt) - - 28")
    else:
        block = block.replace("Dönem (Net) - - 5", "Dönem (Net) - - 6")
    assert _gross(block) == {}


def test_one_nonzero_borrower_category_is_not_promoted_to_bank_total():
    # The independently printed total is 11 net, while the existing regex's
    # first category represents only 5 net. Do not attach 29 gross to that total.
    block = _block().replace("Dönem (Net) - - 5", "Dönem (Net) - - 11")
    block = block.replace(
        "Bankalar (Brüt) - - -\nÖzel Karşılık Tutarı (-) - - -\nBankalar (Net) - - -",
        "Bankalar (Brüt) - - 8\nÖzel Karşılık Tutarı (-) - - 2\nBankalar (Net) - - 6",
    )
    assert _gross(block) == {}


def test_complete_explicit_nil_borrower_note_is_zero_not_missing():
    assert _gross(_block(gross="-", provision="-", net="-"))["prior"].total == 0


def test_borrower_fallback_does_not_overwrite_an_existing_gross_balance():
    page = "\n".join([
        "Önceki Dönem",
        "Dönem Sonu Bakiyesi - - 30",
        "Karşılık (-) - - 25",
        "Bilançodaki Net Bakiyesi - - 5",
        "III. Grup IV. Grup V. Grup",
        _block(),
    ])
    assert _gross(page)["prior"].total == 30
