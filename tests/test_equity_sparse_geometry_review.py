"""Independent geometry review: PDF rotation must not change period or cells."""
import pytest

fitz = pytest.importorskip("fitz")

from src.audit_reports import equity_change as EC  # noqa: E402
from test_equity_sparse_grid import _block  # noqa: E402


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("prior_first", [True, False])
def test_sparse_geometry_preserves_distinct_periods_under_rotation(tmp_path, rotation, prior_first):
    # Build two different, internally consistent source matrices. Rotating the
    # physical text and the PDF display in opposite directions leaves the same
    # visible report while changing the coordinates returned by get_text().
    source = fitz.open()
    page = source.new_page(width=860, height=500)
    periods = ["PRIOR PERIOD", "CURRENT PERIOD"]
    if not prior_first:
        periods.reverse()
    for block_index, period in enumerate(periods):
        top = 35 + block_index * 210
        factor = 1 if period == "PRIOR PERIOD" else 2
        page.insert_text((15, top), period, fontsize=7)
        for row_index, (label, values) in enumerate(_block()):
            y = top + 20 + row_index * 17
            page.insert_text((15, y), label, fontsize=6)
            for column, value in enumerate(values):
                if value is None:
                    continue
                text = f"{value * factor:,}"
                edge = 270 + column * 36
                page.insert_text((edge - fitz.get_text_length(text, fontsize=6), y),
                                 text, fontsize=6)
    rotated = fitz.open()
    size = (500, 860) if rotation in (90, 270) else (860, 500)
    page = rotated.new_page(width=size[0], height=size[1])
    page.show_pdf_page(page.rect, source, 0, rotate=rotation)
    page.set_rotation(rotation)
    path = tmp_path / "rotated-sparse.pdf"
    rotated.save(path)
    rotated.close()
    source.close()

    report = EC.extract_from_pdf(str(path), 0)
    assert len(report.rows) == 18
    for period, factor in [("prior", 1), ("current", 2)]:
        rows = {row.hierarchy: row for row in report.rows if row.period_type == period}
        assert rows["I."].paid_in_capital == 1000 * factor
        assert rows["I."].share_cancellation_profits == 0
        assert rows["III."].share_cancellation_profits is None
        assert rows["IV."].paid_in_capital is None
        assert rows["11.2"].total_equity is None
        assert rows[""].total_equity == 1245 * factor
