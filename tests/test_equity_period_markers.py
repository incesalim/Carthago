"""Guard the equity-change current/prior period markers.

A bank that prints its prior-period matrix FIRST (HSBC) relied on _PRIOR_RX
matching "Önceki Dönem"; the old pattern only covered "Önce(si) Dönem" and
missed the "ki", so the page defaulted to 'current' and the enforce-distinct
fallback swapped the two periods (stored "current" = the prior-year matrix).

Guarded by importorskip: equity_change imports fitz (CI minimal deps omit).
"""
import pytest

pytest.importorskip("fitz")

from src.audit_reports import equity_change as EC  # noqa: E402

_CURRENT_RX = EC._CURRENT_RX
_PRIOR_RX = EC._PRIOR_RX
_max_year = EC._max_year


def test_max_year_picks_latest_period_end():
    # The current table closes on the later date, so the marker-less period
    # resolver (ALNTF) keys off the larger max-year. Current page shows
    # opening 2024 + closing 2025; prior page shows 2023 + 2024.
    assert _max_year("31 Aralık 2024 ... 31 Aralık 2025 ...") == 2025
    assert _max_year("31 Aralık 2023 ... 31 Aralık 2024 ...") == 2024
    assert _max_year("no years here") is None


def test_prior_marker_matches_onceki_and_variants():
    for s in ("Önceki Dönem", "ÖNCEKİ DÖNEM", "Öncesi Dönem", "Önce Dönem",
              "Prior Period", "Previous Period"):
        assert _PRIOR_RX.search(s), s
        assert not _CURRENT_RX.search(s), s


def test_current_marker_matches_cari():
    for s in ("Cari Dönem", "CARİ DÖNEM", "Current Period"):
        assert _CURRENT_RX.search(s), s
        assert not _PRIOR_RX.search(s), s


def test_single_page_prior_first_uses_explicit_block_headers(monkeypatch):
    """ANADOLU prints prior first and current second, with no dates beside the
    block headers.  The report-title year therefore cannot establish order."""
    text = "\n".join([
        "31 MART 2024 ... ÖZKAYNAKLAR DEĞİŞİM TABLOSU",
        "Önceki Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "Dönem Sonu Bakiyesi (III+IV+…+X+XI) " + "- " * 16,
        "Cari Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
    ])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    assert EC._block1_period_for_split("unused.pdf", 13) == "prior"


def test_single_page_current_first_stays_current(monkeypatch):
    text = "\n".join([
        "Cari Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "Dönem Sonu Bakiyesi (III+IV+…+X+XI) " + "- " * 16,
        "Önceki Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
    ])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    assert EC._block1_period_for_split("unused.pdf", 13) == "current"


def test_dated_period_heading_excludes_profit_column_labels():
    assert EC._period_header("Prior Period – 31 March 2022") == "prior"
    assert EC._period_header("Current Period – 31 March 2023") == "current"
    assert EC._period_header("Cari Dönem (01.01.2026-30.06.2026)") == "current"
    assert EC._period_header("Prior Period Profit or Loss") is None
    assert EC._period_header("Paid-in Capital Prior Period Current Period Profit") is None
    assert EC._period_header("I. Prior Period End Balance 2.800.000") is None


def test_prior_first_block_order_survives_missing_first_closing_label(monkeypatch):
    # ANADOLU 2023Q1: first closing line is values only; only the final formula
    # is readable. The explicit headings still establish the correct order.
    text = "\n".join([
        "31 MART 2023 ... ÖZKAYNAKLAR DEĞİŞİM TABLOSU",
        "Önceki Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "1,100,000 " + "- " * 15,
        "Cari Dönem",
        "I. Önceki Dönem Sonu Bakiyesi " + "- " * 16,
        "Dönem Sonu Bakiyesi (III+IV+…+X+XI) " + "- " * 16,
    ])
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    assert EC._block1_period_for_split("unused.pdf", 13) == "prior"


def test_page_locator_uses_dated_heading_not_current_profit_column(monkeypatch):
    wide = "I. Prior Period End Balance " + "- " * 16
    pages = [
        "Report for March 2023\nPaid-in Capital Prior Period Current Period Profit\n"
        "Prior Period – 31 March 2022\n" + "\n".join([wide] * 3),
        "Report for March 2023\nPaid-in Capital Prior Period Profit\n"
        "Current Period – 31 March 2023\n" + "\n".join([wide] * 3),
    ]
    monkeypatch.setattr(EC, "_HAS_FITZ", True)
    monkeypatch.setattr(EC, "_fitz_page_count", lambda *_: 2)
    monkeypatch.setattr(EC, "_fitz_page_text", lambda _, index: pages[index])
    assert EC._locate_equity_pages("unused.pdf", 0) == [(1, "prior"), (2, "current")]


def test_separate_negative_sign_is_joined_but_a_zero_column_is_preserved():
    text = EC._join_equity_words([
        (0, 2, '-'), (3.06, 7, '33'),
        (30, 32, '-'), (59, 65, '100'),
    ])
    assert text == '-33 - 100'
    assert EC._parse_row_tokens(text) == [-33, 0, 100]


def test_dense_geometry_joins_same_row_without_borrowing_the_next_row(monkeypatch):
    # FIBA: left dash glyphs and right figures are 3.8pt apart vertically;
    # the next row starts 7.2pt below this row's first glyph.
    words = [(0, 182.6, 4, 188, 'IV.'), (6, 183.8, 20, 189, 'Income')]
    for column in range(14):
        y = 180 if column < 8 else 183.8
        value = '100' if column in (12, 13) else '-'
        words.append((80 + column * 20, y, 84 + column * 20, y + 5, value))
    words.append((0, 189.8, 4, 195, 'V.'))
    words.append((6, 189.8, 20, 195, 'Capital'))
    for column in range(14):
        words.append((80 + column * 20, 187.2, 84 + column * 20, 192.2, '-'))

    class Page:
        rotation = 0

        def get_text(self, _kind):
            return words

    class Document:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __getitem__(self, _index):
            return Page()

    monkeypatch.setattr(EC._fitz, 'open', lambda *_: Document())
    lines = EC._fitz_dense_page_lines('unused.pdf', 0)
    assert len(lines) == 2
    first = EC._parse_row_tokens(lines[0], 14)
    second = EC._parse_row_tokens(lines[1], 14)
    assert first == [0] * 12 + [100, 100]
    assert second == [0] * 14
    assert EC._row_gate(first, 14)
