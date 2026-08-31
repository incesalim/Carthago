"""Candidate selection must prove each source period, without mixing years."""
import pytest

pytest.importorskip('fitz')

from src.audit_reports import equity_change as EC  # noqa: E402


def _block(opening, movement):
    return [
        {'hierarchy': 'I.', 'item_name': 'Beginning Balance', 'total_equity': opening},
        {'hierarchy': 'II.', 'item_name': 'Corrections', 'total_equity': 0},
        {'hierarchy': 'III.', 'item_name': 'New Balance', 'total_equity': opening},
        {'hierarchy': 'IV.', 'item_name': 'Comprehensive income', 'total_equity': movement},
        {'hierarchy': 'XI.', 'item_name': 'Distribution', 'total_equity': 0},
        {'hierarchy': '', 'item_name': 'Closing Balance', 'total_equity': opening + movement},
    ]


def test_two_different_source_periods_are_validated_separately():
    assert EC._eq_chain_closes(_block(100000, 5000) + _block(200000, 6000))


def test_valid_first_period_cannot_hide_incomplete_second_period():
    assert not EC._eq_chain_closes(_block(100000, 5000) + _block(200000, 6000)[:-1])


def test_valid_current_period_cannot_hide_missing_prior_opening():
    assert not EC._eq_chain_closes(_block(100000, 5000)[1:] + _block(200000, 6000))


def test_a_failure_in_either_source_period_rejects_candidate():
    first, second = _block(100000, 5000), _block(200000, 6000)
    first[-1]['total_equity'] += 1000
    assert not EC._eq_chain_closes(first + second)
    assert not EC._eq_chain_closes(second + first)


@pytest.mark.parametrize('width', [14, 16])
def test_separate_source_label_and_full_values_rejoin(width):
    values = '100,000 ' + '- ' * 12 + '100,000'
    if width == 16:
        values += ' 3,000 103,000'
    lines = ['I.', 'Beginning Balance ' + values,
             'II. Adjustment in accordance with TAS 8', '- ' * width,
             'III. New Balance (I+II)', values]
    joined = EC._join_split_equity_labels(lines, width)
    assert len(joined) == 3
    assert joined[0] == 'I. Beginning Balance ' + values
    assert joined[2] == 'III. New Balance (I+II) ' + values


def test_source_label_join_does_not_cross_another_explicit_marker():
    lines = ['III. New Balance (I+II)', 'IV. Comprehensive income ' + '- ' * 16]
    assert EC._join_split_equity_labels(lines, 16) == lines


def test_source_label_join_does_not_pad_partial_values():
    lines = ['III. New Balance (I+II)', '100,000 ' + '- ' * 10 + '100,000']
    assert EC._join_split_equity_labels(lines, 16) == lines


@pytest.mark.parametrize('width', [14, 16])
def test_unclosed_negative_retains_printed_sign_only_when_row_foots(width):
    line = 'XI. Profit Distribution ' + '- ' * 10 + '12.173.740 (12.184.801 - (11.061)'
    if width == 16:
        line += ' 11.061 -'
    values = EC._parse_row_tokens(line, width)
    assert values[11] == -12184801
    assert values[13] == -11061
    assert EC._row_fit_residual(values, width) == 0


def test_unclosed_negative_does_not_repair_a_nonclosing_source_row():
    line = 'XI. Profit Distribution ' + '- ' * 10 + '12.173.740 (12.184.801 - (11.062)'
    assert EC._parse_row_tokens(line, 14)[11] == 12184801


def test_unclosed_reference_cannot_replace_an_already_footing_read():
    line = 'IV. Income ' + '- ' * 12 + '(1,000 1,000'
    values = EC._parse_row_tokens(line, 14)
    assert values[12:] == [1000, 1000]
