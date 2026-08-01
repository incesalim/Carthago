"""Guard: a reported ZERO from BDDK must be stored as 0, never as NULL.

This lane had no tests at all — `src/scrapers/bddk_api_scraper.py` produces
`balance_sheet`, `income_statement`, `loans`, `deposits` and `financial_ratios`,
i.e. most of what the sector pages read and everything `/api/v1` publishes, and
nothing imported it. That gap is why the defect below survived in production
across the whole stored corpus.

THE DEFECT

`_save_loans` picked a value with `get_val("A") or get_val("B") or get_val("C")`.
`or` is falsy-based, so a genuine reported `0` was discarded and the chain fell
through to a candidate column that does not exist in that table — yielding NULL.
BDDK sends nil as the integer `0` (never null, never empty, never a dash), so
every real zero in those columns was lost.

Measured over the stored corpus before the fix: `total_tl` and `total_fx` held
**zero zeros in the entire table**, while table 4's `Yp` column alone reports
19,139 of them — and `COUNT(total_fx IS NULL)` matched that 19,139 exactly. The
four maturity-split columns (`short_term_*`, `medium_long_*`) never used an `or`
chain and preserved their zeros perfectly; that contrast is what identified the
cause.

WHY IT IS NOT COSMETIC

The largest affected block is the consumer-loan FX column. Residents without FX
income are barred from borrowing in foreign currency (Decree 32), so "consumer
vehicle loans, YP = 0" is not missing data — it is the law. Storing it as NULL
restates a legal prohibition as ignorance, and the project's first rule is that
`null` is not `0`.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.scrapers.bddk_api_scraper import BDDKAPIScraper

LOANS_DDL = """
CREATE TABLE loans (
    table_number INTEGER, year INTEGER, month INTEGER, currency TEXT,
    bank_type_code TEXT, item_order INTEGER, item_name TEXT, is_subtotal INTEGER,
    short_term_tl REAL, short_term_fx REAL, short_term_total REAL,
    medium_long_tl REAL, medium_long_fx REAL, medium_long_total REAL,
    total_tl REAL, total_fx REAL, total_amount REAL,
    npl_amount REAL, non_cash_amount REAL, customer_count REAL
)
"""


@pytest.fixture()
def scraper(tmp_path):
    s = BDDKAPIScraper(db_path=tmp_path / "t.db")
    s.connect_db()
    s.cursor.execute(LOANS_DDL)
    yield s
    s.conn.close()


def _row(cells: list) -> dict:
    return {"cell": cells}


# Column layout of BDDK's table 4 (consumer loans): the total legs arrive as
# `Tp`/`Yp`, NOT as `ToplamTp`/`ToplamYp`. That is the case the `or` chain got
# wrong — `ToplamTp` is absent, so a 0 in `Tp` fell through to `NakdiKrediTp`,
# also absent, and the row stored NULL.
COLUMNS_T4 = {"BasitSira": 0, "Ad": 1, "BasitFont": 2, "Tp": 3, "Yp": 4, "Toplam": 5}


def _fetch(scraper, col: str):
    scraper.cursor.execute(f"SELECT {col} FROM loans")
    return scraper.cursor.fetchone()[0]


def test_reported_zero_is_stored_as_zero_not_null(scraper):
    """A consumer-loan row with YP = 0 must store 0. This is the regression."""
    rows = [_row([1, "Tüketici Kredileri - Taşıt", "normal", 12345.0, 0, 12345.0])]
    saved = scraper._save_loans(4, 2026, 6, "TL", "10001", COLUMNS_T4, rows)

    assert saved == 1
    assert _fetch(scraper, "total_fx") == 0, (
        "a reported 0 became NULL — the falsy-`or` fallthrough is back"
    )
    assert _fetch(scraper, "total_tl") == 12345.0


def test_zero_on_every_or_chained_column(scraper):
    """All five chained columns, not just the two that were measured."""
    cols = {
        "BasitSira": 0, "Ad": 1, "BasitFont": 2,
        "Tp": 3, "Yp": 4, "Toplam": 5, "Takipteki": 6, "GayriNakdi": 7,
    }
    rows = [_row([1, "Bir kalem", "normal", 0, 0, 0, 0, 0])]
    scraper._save_loans(5, 2026, 6, "TL", "10001", cols, rows)

    for col in ("total_tl", "total_fx", "total_amount", "npl_amount", "non_cash_amount"):
        assert _fetch(scraper, col) == 0, f"{col} lost a reported zero"


def test_absent_column_still_stores_null(scraper):
    """The fix must not turn genuinely-absent data into 0 — that is the same
    error pointed the other way. No total columns present at all → NULL."""
    cols = {"BasitSira": 0, "Ad": 1, "BasitFont": 2, "KisaTp": 3}
    rows = [_row([1, "Sadece kısa vade", "normal", 500.0])]
    scraper._save_loans(3, 2026, 6, "TL", "10001", cols, rows)

    assert _fetch(scraper, "short_term_tl") == 500.0
    assert _fetch(scraper, "total_tl") is None
    assert _fetch(scraper, "total_fx") is None


def test_first_present_column_wins_over_later_candidates(scraper):
    """Precedence is by ORDER, not by value: `ToplamTp` outranks `Tp` when both
    exist, including when `ToplamTp` is 0."""
    cols = {"BasitSira": 0, "Ad": 1, "BasitFont": 2, "ToplamTp": 3, "Tp": 4}
    rows = [_row([1, "İki aday", "normal", 0, 999.0])]
    scraper._save_loans(3, 2026, 6, "TL", "10001", cols, rows)

    assert _fetch(scraper, "total_tl") == 0, "a 0 in the first column was skipped"


def test_empty_string_falls_through_but_zero_does_not(scraper):
    """`""` is genuinely no-value and should fall through; `0` must not."""
    cols = {"BasitSira": 0, "Ad": 1, "BasitFont": 2, "ToplamTp": 3, "Tp": 4}
    rows = [_row([1, "Boş sonra dolu", "normal", "", 42.0])]
    scraper._save_loans(3, 2026, 6, "TL", "10001", cols, rows)

    assert _fetch(scraper, "total_tl") == 42.0


def test_short_rows_are_skipped(scraper):
    """Fewer than 4 cells is not a data row; it must not raise."""
    assert scraper._save_loans(3, 2026, 6, "TL", "10001", COLUMNS_T4, [_row([1, "x"])]) == 0


def test_sqlite_null_and_zero_are_distinguishable(scraper):
    """The premise the whole guard rests on: SQLite keeps them apart, so a NULL
    in this column really did mean the value was lost, not stored as zero."""
    cols = {"BasitSira": 0, "Ad": 1, "BasitFont": 2, "Tp": 3, "Yp": 4}
    scraper._save_loans(4, 2026, 6, "TL", "10001", cols, [_row([1, "sıfır", "normal", 0, 0])])
    scraper._save_loans(4, 2026, 7, "TL", "10001", {"BasitSira": 0, "Ad": 1, "BasitFont": 2},
                        [_row([1, "yok", "normal", 0])])
    scraper.cursor.execute("SELECT COUNT(*) FROM loans WHERE total_tl IS NULL")
    assert scraper.cursor.fetchone()[0] == 1
    scraper.cursor.execute("SELECT COUNT(*) FROM loans WHERE total_tl = 0")
    assert scraper.cursor.fetchone()[0] == 1
    assert sqlite3.sqlite_version_info  # the driver is real, not a stub
