"""Unit tests for the free-provision (serbest karşılık) classifier.

Pure text in, structured stock out — no PDF, no fitz — so these run under CI's
minimal deps. The fixtures are the real disclosure forms seen across the fleet
(deposit/participation/state/development, EN + TR), page-indexed the way the
extractor reads them: index 0-4 = auditor's report, 5+ = balance-sheet notes.
The classifier is proven at 11/11 on the hand-verified 2025Q1 sample; these pin
the forms and the two hazards (flow-vs-stock, and European "." separators).
"""
from src.audit_reports.free_provision import classify_free_provision


def _pages(note: str, auditor: str = "") -> list[str]:
    # Put the note on a later page (index 8) and any auditor text up front.
    pages = [auditor] + [""] * 7 + [note]
    return pages


def test_albrk_note_footnote_form():
    # "Includes free provisions amounting to TL 300.000 (December 31, 2024: TL 7.300.000)"
    r = classify_free_provision(_pages(
        "(*) Includes free provisions amounting to TL 300.000 "
        "(December 31, 2024: TL 7.300.000), which was provided by the Bank management."
    ))
    assert r.free_provision == 300000
    assert r.free_provision_prior == 7300000


def test_flow_not_stock_is_rejected():
    # The auditor paragraph states the REVERSAL (a flow), not the stock.
    r = classify_free_provision([
        "a portion of the free provision amounting to TL 7,000,000 thousand is "
        "reversed in the current period",  # page 0 (auditor)
    ] + [""] * 8)
    assert r.free_provision != 7000000  # must not capture the reversal


def test_free_provision_expense_is_rejected():
    # QNBFB p99-style: "free provision expense … amounting to TL 1,900,000" is a flow.
    r = classify_free_provision(_pages(
        "Includes free provision expense for possible risks amounting to TL 1,900,000 "
        "allocated in the current period."
    ))
    assert r.free_provision != 1900000


def test_qnbfb_current_over_prior_when_both_stated():
    # The report states all three periods; the CURRENT stock must win, and the
    # "free\nprovision" line break must not hide the sentence from the reader.
    auditor = (
        "financial statements as of March 31, 2025 include a free\nprovision at an "
        "amount of thousand TL 6.600.000, of which thousand TL 4.700.000 was provided "
        "in prior periods.\n"
        "statements as of December 31, 2024 include a free provision at an amount of "
        "thousand TL 4.700.000 of which thousand TL 6.800.000 provided."
    )
    r = classify_free_provision([auditor] + [""] * 8)
    assert r.free_provision == 6600000


def test_turkish_prose_tutari_form():
    # VAKBN: "serbest karşılık tutarı 4,000,000 TL'dir (31 Aralık 2024: 15,000,000 TL)"
    r = classify_free_provision(_pages(
        "31 Mart 2025 tarihi itibarıyla finansal tablolarda yer alan serbest karşılık "
        "tutarı 4,000,000 TL'dir (31 Aralık 2024: 15,000,000 TL)."
    ))
    assert r.free_provision == 4000000
    assert r.free_provision_prior == 15000000


def test_turkish_tutarinda_yer_almaktadir_form():
    # ZIRAAT: "9.000.000 TL tutarında serbest karşılık yer almaktadır"
    r = classify_free_provision(_pages(
        "tamamı geçmiş yıllarda ayrılan 9.000.000 TL tutarında serbest karşılık yer "
        "almaktadır."
    ))
    assert r.free_provision == 9000000


def test_explicit_none_is_zero():
    # AKBNK: "serbest karşılıklara ilişkin bilgiler: Bulunmamaktadır"
    r = classify_free_provision(_pages(
        "Muhtemel riskler için ayrılan serbest karşılıklara ilişkin bilgiler:"
        "Bulunmamaktadır (31 Aralık 2024: Bulunmamaktadır)."
    ))
    assert r.free_provision == 0
    assert r.disclosed


def test_european_separator_not_truncated():
    # The "." in "1.650.000" must survive — it is the thousands separator.
    r = classify_free_provision(_pages(
        "Free provision amounting to TL 1.650.000 provided by the Bank management."
    ))
    assert r.free_provision == 1650000


def test_no_disclosure_is_empty():
    r = classify_free_provision(["Balance sheet and notes with no such reserve."] * 5)
    assert r.is_empty()
    assert r.free_provision is None
