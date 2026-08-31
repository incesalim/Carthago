"""Only physically adjacent, uniquely paired printed digits may be rejoined."""
import pytest

fitz = pytest.importorskip('fitz')

from src.audit_reports import equity_change as EC  # noqa: E402


def _pdf(tmp_path, *, tail_shift=0, tail_gap=9, duplicate=False, wrong_total=False):
    path = tmp_path / 'wrapped.pdf'
    document = fitz.open()
    page = document.new_page(width=850, height=300)
    page.insert_text((15, 25), 'CURRENT PERIOD', fontsize=6)
    opening = [0] * 16
    opening[0], opening[4] = 100000, 2071477
    opening[13], opening[14], opening[15] = 2171477, 1000, 2172477
    movement = [0] * 16
    movement[4] = movement[13] = movement[15] = 2410
    closing = [a + b for a, b in zip(opening, movement)]
    if wrong_total:
        closing[13] += 10000
        closing[15] += 10000
    rows = [('I. Beginning Balance', opening), ('III. New Balance (I+II)', opening),
            ('IV. Total Comprehensive Income', movement),
            ('Ending Balance (III+IV+X+XI)', closing)]
    for row_index, (label, values) in enumerate(rows):
        y = 60 + row_index * 35
        page.insert_text((15, y), label, fontsize=6)
        for column, value in enumerate(values):
            text = f'{value:,}'.replace(',', '.')
            edge = 280 + column * 34
            if column == 4 and row_index != 2:
                head, tail = text[:-1], text[-1]
                page.insert_text((edge - fitz.get_text_length(head, fontsize=6), y - tail_gap),
                                 head, fontsize=6)
                x = edge + tail_shift - fitz.get_text_length(tail, fontsize=6)
                page.insert_text((x, y), tail, fontsize=6)
                if duplicate:
                    page.insert_text((x + 0.8, y + 0.1), tail, fontsize=6)
            else:
                page.insert_text((edge - fitz.get_text_length(text, fontsize=6), y),
                                 text, fontsize=6)
    document.save(path)
    document.close()
    return str(path)


def test_wrapped_last_digit_uses_only_visible_source_tokens(tmp_path):
    path = _pdf(tmp_path)
    lines = EC._fitz_wrapped_digit_page_lines(path, 0)
    assert sum('2.071.477' in line for line in lines) == 2
    assert sum('2.073.887' in line for line in lines) == 1
    rows = EC._parse_equity_page(path, 1, 'current', 16)
    assert len(rows) == 4
    assert rows[0].oci_not_reclassified_1 == 2071477
    assert rows[-1].oci_not_reclassified_1 == 2073887
    assert rows[-1].total_equity == 2173887
    assert rows[-1].minority_interest == 1000
    assert rows[-1].total_equity_incl_minority == 2174887
    assert EC._eq_candidate_score(rows)[0] == 1


@pytest.mark.parametrize('options', [
    {'tail_shift': 3}, {'tail_gap': 12}, {'duplicate': True},
])
def test_wrapped_digits_require_unique_touching_aligned_boxes(tmp_path, options):
    assert not EC._fitz_wrapped_digit_page_lines(_pdf(tmp_path, **options), 0)


def test_wrapped_candidate_cannot_override_a_broken_source_identity(tmp_path):
    path = _pdf(tmp_path, wrong_total=True)
    assert EC._fitz_wrapped_digit_page_lines(path, 0)
    rows = EC._parse_equity_page(path, 1, 'current', 16)
    assert EC._eq_candidate_score(rows)[0] == 0
    assert all(row.oci_not_reclassified_1 != 2071477 for row in rows)
