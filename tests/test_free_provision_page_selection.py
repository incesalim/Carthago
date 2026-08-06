"""A reversal page must never outrank a genuine stock disclosure.

TEB 2026Q1 stored `free_provision = 0`. The filing states the stock plainly on
cons p74 / unco p71:

    "(*) 31 Mart 2026 itibarıyla 1,108,135 TL (31 Aralık 2025: 1,230,000 TL)
     tutarında serbest karşılığı içermektedir."

Three independent defects hid it:

1. `_SUBJ_TR` required the hard final `k`. Turkish softens it to `ğ` before a
   vowel suffix, and "serbest karşılığı" is the form banks use in exactly the
   sentence that states the stock. The subject never matched, so no stock
   candidate existed on that page at all.
2. The amount-before-subject pattern required "N TL" and "tutarında" adjacent.
   Here the prior-period comparison sits between them.
3. `_NONE` matched the SEPARATE reversal note on a later page — "… serbest
   karşılık iptal tutarını içermektedir (31 Mart 2025: Bulunmamaktadır)" —
   where the "none" describes the PRIOR period, not the current stock. With no
   stock candidate to beat, that 0 won.

Fixed at page selection, not by curating the partition: the same fingerprint
hits ZIRAATK 2024Q1 too, and an override would have left that one wrong.

Text fixtures rather than PDFs — `data/_bench/` is gitignored, and
`classify_free_provision` is pure over page text precisely so this is testable
in CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.free_provision import (  # noqa: E402
    _NONE, _SUBJ_TR, _none_describes_only_the_prior, classify_free_provision,
)

# Verbatim from the filings.
TEB_STOCK_PAGE = (
    "7. Karşılıklara ilişkin açıklamalar\n"
    "Diğer karşılıklar (*)\n"
    "(*) 31 Mart 2026 itibarıyla 1,108,135 TL (31 Aralık 2025: 1,230,000 TL) "
    "tutarında serbest karşılığı içermektedir.\n"
    "8. Vergi borcuna ilişkin açıklamalar\n"
)
TEB_REVERSAL_PAGE = (
    "6. Diğer faaliyet gelirlerine ilişkin bilgiler\n"
    "(*) 31 Mart 2026 tarihi itibarıyla 121,865 TL tutarında ayrılan serbest "
    "karşılık iptal tutarını içermektedir (31 Mart 2025: Bulunmamaktadır).\n"
)


def _pages(*late, lead=6):
    """Filler front matter, then the given note pages (page_rank needs i >= 5)."""
    return ["auditor front matter"] * lead + list(late)


def test_the_stock_page_wins_over_the_reversal_page():
    r = classify_free_provision(_pages(TEB_STOCK_PAGE, TEB_REVERSAL_PAGE))
    assert (r.free_provision, r.free_provision_prior) == (1_108_135, 1_230_000)


def test_it_wins_regardless_of_which_page_comes_first():
    """The reversal sits AFTER the stock in TEB's filing; order must not decide
    it — a later page must not win merely by being later."""
    r = classify_free_provision(_pages(TEB_REVERSAL_PAGE, TEB_STOCK_PAGE))
    assert (r.free_provision, r.free_provision_prior) == (1_108_135, 1_230_000)


def test_the_reversal_page_alone_yields_no_stock():
    """Its parenthetical describes the PRIOR period. Reading it as the current
    stock is what stored 0."""
    r = classify_free_provision(_pages(TEB_REVERSAL_PAGE))
    assert r.free_provision != 0, "the prior-period 'none' was read as the stock"


def test_the_softened_subject_is_recognised():
    import re
    for form in ("serbest karşılık", "serbest karşılığı", "serbest karşılığın"):
        assert re.search(_SUBJ_TR, form, re.I), form


def test_a_genuine_none_still_reads_as_zero():
    """`0` is a real disclosure — the bank says it holds none — and must survive.
    It is not the same fact as `null`."""
    page = ("Muhtemel riskler için ayrılan serbest karşılıklara ilişkin "
            "bilgiler: Bulunmamaktadır (31 Aralık 2025: Bulunmamaktadır).")
    r = classify_free_provision(_pages(page))
    assert r.disclosed is True and r.free_provision == 0


def test_a_full_cancellation_to_zero_still_reads_as_zero():
    """The override file's own rule: held one, then cancelled it in full. The
    veto is deliberately narrower than 'a reversal verb is present', so this
    keeps working."""
    page = ("Banka, geçmiş dönemde ayrılan serbest karşılığın tamamını iptal "
            "etmiş olup 31 Mart 2026 itibarıyla serbest karşılık "
            "bulunmamaktadır.")
    r = classify_free_provision(_pages(page))
    assert r.disclosed is True and r.free_provision == 0


@pytest.mark.parametrize("text,expected", [
    ("serbest karşılık iptal tutarını içermektedir (31 Mart 2025: Bulunmamaktadır)",
     True),
    ("serbest karşılık tutarı bulunmamaktadır (31 Aralık 2024: 1.000.000 TL)",
     False),
    ("serbest karşılık bulunmamaktadır", False),
    ("free provision: none (December 31, 2024: TL 500.000)", False),
])
def test_the_prior_only_none_is_identified(text, expected):
    m = _NONE.search(text)
    assert m is not None, text
    assert _none_describes_only_the_prior(text, m) is expected, text


def test_the_prior_parenthetical_is_still_read_as_the_prior():
    """Vetoing the 'none' as a CURRENT stock must not stop it being recorded as
    the PRIOR one where a real current amount is present."""
    page = ("31 Mart 2026 itibarıyla 5.000.000 TL (31 Aralık 2025: "
            "Bulunmamaktadır) tutarında serbest karşılığı içermektedir.")
    r = classify_free_provision(_pages(page))
    assert r.free_provision == 5_000_000
    assert r.free_provision_prior == 0, "an explicit prior 'none' is 0, not null"


def test_ziraatk_2024q1_no_longer_reads_a_prior_none_as_the_stock():
    """The second victim, verbatim from its stored snippet. Its true current
    stock is not knowable from this sentence — which is the point: a 0 derived
    from a 2023 comparative is not a disclosure about 2024Q1. What the page
    really yields is measured over the corpus in Actions, not guessed here."""
    text = ("serbest karşılık iptallerinden (31 Mart 2023: Bulunmamaktadır), "
            "1.071.885 TL'si katılma hesapları karşılık iptallerinden")
    m = _NONE.search(text)
    assert m is not None
    assert _none_describes_only_the_prior(text, m) is True
    r = classify_free_provision(_pages(text))
    assert r.free_provision != 0, (
        "a prior-period 'none' must not stand in for the current stock")


def test_teb_2026q1_is_pinned():
    """Both kinds carry identical figures; 1,230,000 is TEB's stored 2025Q4
    current stock, and 1,230,000 - 121,865 = 1,108,135."""
    r = classify_free_provision(_pages(TEB_STOCK_PAGE, TEB_REVERSAL_PAGE))
    assert r.free_provision == 1_108_135
    assert r.free_provision_prior == 1_230_000
    assert r.free_provision_prior - 121_865 == r.free_provision
