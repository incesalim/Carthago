"""Sparse source cells retain their positions and null disclosure semantics."""
from copy import deepcopy

import pytest

fitz = pytest.importorskip("fitz")

from src.audit_reports import equity_change as EC  # noqa: E402
from src.audit_reports.validator import (  # noqa: E402
    check_equity_change,
    rows_from_equity_rows,
)


def _values(**columns):
    values = [None] * 16
    for key, value in columns.items():
        values[int(key.removeprefix("c"))] = value
    return values


def _block():
    # A source-shaped sparse matrix: blank correction/capital-raise rows carry
    # no numbers, while reserve transfers disclose components but no total.
    opening = [0] * 16
    for index, value in {0: 1000, 11: 200, 13: 1200, 14: 10, 15: 1210}.items():
        opening[index] = value
    adjusted = list(opening)
    adjusted[2] = None
    closing = [0] * 16
    for index, value in {0: 1000, 10: 15, 11: 180, 12: 50,
                         13: 1245, 14: 11, 15: 1256}.items():
        closing[index] = value
    return [
        ("I. Beginning Balance", opening),
        ("III. New Balance (I+II)", adjusted),
        ("IV. Total Comprehensive Income", _values(c12=50, c13=50, c14=2, c15=52)),
        ("X. Other Changes", _values(c10=-10, c11=10, c13=0, c15=0)),
        ("XI. Profit Distribution", _values(c10=25, c11=-30, c13=-5, c14=-1, c15=-6)),
        ("11.1 Dividend Paid", _values(c11=-10, c13=-10, c14=-1, c15=-11)),
        ("11.2 Transfer to Reserves", _values(c10=20, c11=-20)),
        ("11.3 Other", _values(c10=5, c13=5, c14=0, c15=5)),
        ("Ending Balance (III+IV+X+XI)", closing),
    ]


def _source_pdf(tmp_path, *, shift_cell=False, remove_anchor=False, stray_left_zero=False,
                current_first=False, unknown_movements=False):
    path = tmp_path / "sparse.pdf"
    document = fitz.open()
    page = document.new_page(width=860, height=500)
    periods = (("CURRENT PERIOD", "PRIOR PERIOD") if current_first
               else ("PRIOR PERIOD", "CURRENT PERIOD"))
    for block_index, period in enumerate(periods):
        top = 35 + block_index * 210
        page.insert_text((15, top), period, fontsize=7)
        for row_index, (label, values) in enumerate(_block()):
            if current_first and block_index == 1 and row_index in (0, 1, 8):
                for column in (0, 13, 15):
                    values[column] += 45
            y = top + 20 + row_index * 17
            page.insert_text((15, y), label, fontsize=6)
            if stray_left_zero and block_index == 1 and row_index == 2:
                page.insert_text((267 - fitz.get_text_length('0', fontsize=6), y),
                                 '0', fontsize=6)
            for column, value in enumerate(values):
                if value is None or (remove_anchor and block_index == 1
                                     and row_index == 8 and column == 2):
                    continue
                text = f"{value:,}"
                edge = 270 + column * 36
                if shift_cell and block_index == 1 and row_index == 2 and column == 12:
                    edge += 3
                page.insert_text((edge - fitz.get_text_length(text, fontsize=6), y),
                                 text, fontsize=6)
    if unknown_movements:
        for y, label, amount in ((97.5, "New source movement", 10),
                                 (114.5, "Unmodeled reversal", -10)):
            page.insert_text((15, y), label, fontsize=6)
            for column, value in ((10, amount), (11, -amount)):
                text = str(value)
                page.insert_text((270 + column * 36 - fitz.get_text_length(text, fontsize=6), y),
                                 text, fontsize=6)
    document.save(path)
    document.close()
    return str(path)


def test_sparse_grid_preserves_blank_and_disclosed_zero(tmp_path):
    path = _source_pdf(tmp_path)
    grid = EC._fitz_sparse_page_grid(path, 0)
    assert grid is not None
    assert len(grid[1]) == 18
    report = EC.extract_from_pdf(path, 0)
    assert len(report.rows) == 18
    assert {row.period_type for row in report.rows} == {"current", "prior"}
    current = {row.hierarchy: row for row in report.rows if row.period_type == "current"}
    assert current["I."].share_cancellation_profits == 0
    assert current["III."].share_cancellation_profits is None
    assert current["IV."].paid_in_capital is None
    assert current["11.2"].total_equity is None
    assert current["11.2"].profit_reserves == 20
    assert current["11.2"].prior_period_profit_loss == -20
    assert current[""].total_equity == 1245
    assert not check_equity_change(rows_from_equity_rows(report)).failures


@pytest.mark.parametrize("change", ["row_total", "column", "missing_total", "duplicate"])
def test_sparse_grid_requires_exact_independent_identities(change):
    rows = deepcopy(_block() + _block())
    if change == "row_total":
        rows[2][1][13] += 1
    elif change == "column":
        # Both row totals still foot; the printed component chain does not.
        rows[2][1][12] -= 1
        rows[2][1][11] = 1
    elif change == "missing_total":
        rows[2][1][13] = None
    else:
        rows.insert(2, deepcopy(rows[1]))
    assert not EC._sparse_grid_closes(rows)


@pytest.mark.parametrize("options", [
    {"shift_cell": True}, {"remove_anchor": True}, {"stray_left_zero": True},
    {"unknown_movements": True},
])
def test_sparse_grid_rejects_ambiguous_geometry(tmp_path, options):
    assert EC._fitz_sparse_page_grid(_source_pdf(tmp_path, **options), 0) is None


def test_sparse_grid_does_not_replace_valid_existing_parse(monkeypatch):
    def forbidden(*_):
        pytest.fail("valid existing parser must not call sparse recovery")

    source = [label + " " + " ".join(f"{value or 0:,}" for value in values)
              for label, values in _block()]
    text = "CURRENT PERIOD\n" + "\n".join(source)
    monkeypatch.setattr(EC, "_fitz_page_lines", lambda *_: text.splitlines())
    monkeypatch.setattr(EC, "_fitz_page_text", lambda *_: text)
    monkeypatch.setattr(EC, "_fitz_sparse_page_grid", forbidden)
    assert EC._parse_equity_page("unused.pdf", 1, "current", 16)


def test_explicit_periods_override_coincident_closing_and_opening(tmp_path):
    # Current closing=1245 happens to equal prior opening=1245. Equality must
    # not reverse the table's explicit CURRENT/Prior headings.
    report = EC.extract_from_pdf(_source_pdf(tmp_path, current_first=True), 0)
    assert len(report.rows) == 18
    opening = {row.period_type: row for row in report.rows if row.hierarchy == 'I.'}
    assert opening['current'].paid_in_capital == 1000
    assert opening['prior'].paid_in_capital == 1045
