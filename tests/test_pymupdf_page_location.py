"""Guard the PyMuPDF engine that statement page location depends on.

PyMuPDF 1.28.0 (MuPDF 1.29.0) changed text extraction enough that
`_locate_pages` stopped finding anything on REAL filings. Same PDF, same code:

    1.27.2.3  AKBNK 2026Q1 uncon -> {'bs_assets': 7, 'bs_liab': 8, ...}
    1.28.0    AKBNK 2026Q1 uncon -> {'off_bs': 78}
    1.28.0    GARAN / YKBNK / TEB / ISCTR / AKBNK conso -> {}

It fails SILENTLY: an extraction run finds no balance sheet, no P&L and no
off-balance page, and reports zero rows rather than raising. Found 2026-08-02,
when requirements.txt said `pymupdf>=1.28.0` while local dev ran 1.27.2.3 — so
CI and the developer were on different engines and only CI was broken.

⚠️ A synthetic PDF does NOT reproduce this. A page built with
`page.insert_text()` locates correctly under BOTH versions; the divergence only
shows on real filings, whose multi-column layout goes through the word-coordinate
grouping in `_fitz_page_text`. So this is a version guard, not a behavioural
test, and it is deliberately labelled as such rather than dressed up as one.
Replacing it with a real check means committing a filing as a fixture.
"""
from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

BROKEN_FROM = (1, 28)


def _version() -> tuple[int, ...]:
    raw = getattr(fitz, "VersionBind", None) or fitz.__doc__.split()[1].rstrip(":")
    return tuple(int(p) for p in raw.split(".")[:2] if p.isdigit())


def test_pymupdf_is_below_the_version_that_breaks_page_location():
    v = _version()
    assert v < BROKEN_FROM, (
        f"PyMuPDF {'.'.join(map(str, v))} is installed. 1.28.0 breaks "
        "_locate_pages on real filings — it returns {} and extraction silently "
        "yields zero rows. requirements.txt caps it below 1.28 for this reason. "
        "Re-test _locate_pages across several real filings before raising the cap."
    )
