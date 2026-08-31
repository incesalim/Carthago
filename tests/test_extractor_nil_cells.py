"""A printed double dash is one disclosed nil cell, not missing evidence."""
import pytest

from src.audit_reports.extractor import (
    _count_values, _fitz_merge_rows, _parse_rows, _value_matches, parse_num,
)


@pytest.mark.parametrize(("line", "values"), [
    ("1.1.4 Beklenen Zarar Karşılıkları (-) -- 1 1 1 -- 1", [0, 1, 1, 1, 0, 1]),
    ("1.3.2 Sermayede Payı Temsil Eden Menkul Değerler 1 -- 1 1 -- 1", [1, 0, 1, 1, 0, 1]),
    ("4.3.2 Konsolide Edilmeyenler 3 -- 3 3 -- 3", [3, 0, 3, 3, 0, 3]),
])
def test_deniz_nil_cells_preserve_all_six_printed_columns(line, values):
    # DENIZ 2026Q2 unconsolidated p11. Dropping '--' produced [1,1,1] / [3,3,3].
    assert _count_values(line) == 6
    assert _parse_rows(line, 6)[0][1] == values
    assert values[0] + values[1] == values[2]


def test_complete_nil_row_does_not_swallow_the_following_grand_total():
    text = "\n".join([
        "16.7 Azınlık Payları -- -- -- -- -- --",
        "YÜKÜMLÜLÜKLER TOPLAMI 1.177.570 886.894 2.064.464 945.523 787.520 1.733.043",
    ])
    parsed = _parse_rows(_fitz_merge_rows(text, 6), 6)
    assert len(parsed) == 2
    assert parsed[0] == ("16.7 Azınlık Payları", [0] * 6)
    assert parsed[1][1][:3] == [1177570, 886894, 2064464]


def test_dash_run_is_nil_only_as_a_standalone_token():
    assert parse_num("--") == 0
    assert parse_num("-15") == -15
    assert [m.group() for m in _value_matches("1.2 Held-for-Sale (-) -- 1 1")] == ["--", "1", "1"]
