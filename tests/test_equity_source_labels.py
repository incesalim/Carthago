"""Wrapped labels must trace existing complete rows without changing figures."""
from dataclasses import asdict, fields

import pytest

pytest.importorskip("fitz")

from src.audit_reports.equity_change import (  # noqa: E402
    EquityChangeRow, _restore_equity_source_labels,
)


def _row(hierarchy, values, name="", order=1):
    value_fields = [field.name for field in fields(EquityChangeRow)][5:]
    return EquityChangeRow(order, hierarchy, name, "current", 18,
                           **dict(zip(value_fields, values)))


def _non_metadata(row):
    return {key: value for key, value in asdict(row).items()
            if key not in {"hierarchy", "name"}}


def test_wrapped_correction_keeps_the_printed_standard_citation():
    original = _row("II.", [0] * 16)
    restored = _restore_equity_source_labels([original], [[
        "II. Corrections and Accounting Policy Changes Made",
        "According to TAS 8 " + "- " * 16,
    ]])
    assert restored[0].name == "Corrections and Accounting Policy Changes Made According to TAS 8"
    assert restored[0].hierarchy == "II."
    assert _non_metadata(restored[0]) == _non_metadata(original)
    assert original.name == ""  # preserve the original candidate


def test_wrapped_adjusted_opening_uses_complete_values_beside_note():
    values = [2500, 7, 0, -4, 4709, -244, 0, 260, -6, 0,
              5104, 3663, 0, 15989, 2191, 18180]
    original = _row("III.", values)
    restored = _restore_equity_source_labels([original], [[
        "III. Adjusted Balances at the Beginning of the Period",
        "(I+II) (13) 2,500 7 - (4) 4,709 (244) - 260 (6) - 5,104 3,663 - 15,989 2,191 18,180",
    ]])
    assert restored[0].name == "Adjusted Balances at the Beginning of the Period (I+II)"
    assert _non_metadata(restored[0]) == _non_metadata(original)


def test_transfer_siblings_disambiguate_identical_parent_values():
    values = [0] * 10 + [73826, -73826, 0, 0]
    rows = [_row("XI.", values, "Kâr Dağıtımı", 1),
            _row("11.1", [0] * 14, "Dağıtılan Temettü", 2),
            _row("", values, order=3), _row("11.3", [0] * 14, "Diğer", 4)]
    source = ["XI. Kâr Dağıtımı " + "- " * 10 + "73,826 (73,826) - -",
              "11.1. Dağıtılan Temettü " + "- " * 14,
              "11.2. Yedeklere Aktarılan", "Tutarlar " + "- " * 10 + "73,826 (73,826) - -",
              "11.3. Diğer " + "- " * 14]
    restored = _restore_equity_source_labels(rows, [source])
    assert (restored[2].hierarchy, restored[2].name) == ("11.2", "Yedeklere Aktarılan Tutarlar")
    assert [_non_metadata(row) for row in restored] == [_non_metadata(row) for row in rows]
    # Without both stored sibling identities, identical values do not prove 11.2.
    assert _restore_equity_source_labels([rows[2]], [source])[0] == rows[2]


@pytest.mark.parametrize("source", [
    ["II. Source label " + "- " * 15],  # incomplete source vector
    ["II. Source label 1 " + "- " * 15],  # one changed cell
    ["II. Source label " + "- " * 16, "II. Conflicting label " + "- " * 16],
    ["III. Different row " + "- " * 16],
])
def test_unproven_or_conflicting_source_metadata_is_not_attached(source):
    original = _row("II.", [0] * 16)
    assert _restore_equity_source_labels([original], [source]) == [original]


def test_existing_label_and_undisclosed_values_remain_unchanged():
    source = [["II. Replacement label " + "- " * 16]]
    labelled = _row("II.", [0] * 16, "Retained label")
    undisclosed = _row("II.", [None] + [0] * 15)
    assert _restore_equity_source_labels([labelled], source) == [labelled]
    assert _restore_equity_source_labels([undisclosed], source) == [undisclosed]
