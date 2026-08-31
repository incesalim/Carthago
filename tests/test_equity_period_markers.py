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


def test_adjusted_label_does_not_override_an_explicit_fourth_roman():
    # TSKB 2025Q1 prior block has displaced labels: IV carries the printed
    # comprehensive-income values beside an adjusted-balance label. The clipped
    # II -> III repair must not rewrite other explicit source markers.
    assert EC._eq_split("IV. Adjusted Beginning Balance (I+II) - 1,854,709")[0] == 'IV.'


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


@pytest.mark.parametrize(('values', 'expected'), [
    (
        '2,500 6 - 18 1,714 (231) - - (6) - 4,684 2,017 - 10,702',
        [2500, 6, 0, 18, 1714, -231, 0, 0, -6, 0, 4684, 2017, 0, 10702],
    ),
    (
        '2,500 6 - 18 2,386 (248) - - (11) - 6,576 2,071 - 13,298',
        [2500, 6, 0, 18, 2386, -248, 0, 0, -11, 0, 6576, 2071, 0, 13298],
    ),
    (
        '2,500 7 - (4) 4,709 (244) - 260 (6) - 5,104 3,663 - 15,989 2,191 18,180',
        [2500, 7, 0, -4, 4709, -244, 0, 260, -6, 0, 5104, 3663, 0, 15989, 2191, 18180],
    ),
    (
        '2,500 7 - (2) 5,773 (259) - 327 (10) - 7,410 3,617 - 19,363 2,408 21,771',
        [2500, 7, 0, -2, 5773, -259, 0, 327, -10, 0, 7410, 3617, 0, 19363, 2408, 21771],
    ),
])
def test_adjusted_opening_note_preserves_short_losses_and_column_positions(values, expected):
    # SKBNK 2026Q2, p15 in both filings: III repeats I with a (13) note.
    # Both rows must retain the SAME components, not merely the same total.
    n_cols = len(expected)
    opening = EC._parse_row_tokens('I. Balances at Beginning of Period ' + values, n_cols)
    adjusted = EC._parse_row_tokens('III. Adjusted Balances (I+II) (13) ' + values, n_cols)
    assert opening == adjusted == expected
    assert EC._try_fit(adjusted, n_cols) == expected


def test_note_and_short_loss_resolution_does_not_use_rounding_slack():
    # One changed unit prevents the exact-identity disambiguation, even though
    # the usual row gate's rounding tolerance would accept it.
    line = ('III. Adjusted Balances (I+II) (13) '
            '2,500 6 - 18 1,714 (231) - - (6) - 4,684 2,017 - 10,703')
    tokens = EC._parse_row_tokens(line, 14)
    assert len(tokens) == 13
    assert -6 not in tokens


def test_note_and_short_losses_also_require_the_minority_identity():
    line = ('III. Adjusted Balances (I+II) (13) '
            '2,500 7 - (4) 4,709 (244) - 260 (6) - 5,104 3,663 - 15,989 2,191 18,181')
    tokens = EC._parse_row_tokens(line, 16)
    assert len(tokens) == 14
    assert -4 not in tokens
    assert -6 not in tokens


def test_both_period_blocks_keep_their_separate_label_and_dated_closing(monkeypatch):
    def amounts(capital, profit=0):
        vals = [capital] + [0] * 11 + [profit, capital + profit, 0, capital + profit]
        return ' '.join(f'{v:,}' if v else '-' for v in vals)

    def block(heading, capital, profit, year):
        lines = [heading]
        for marker in EC._EQ_ROW_SEQ:
            values = (amounts(capital) if marker in ('I.', 'III.')
                      else amounts(0, profit) if marker == 'IV.' else amounts(0))
            lines.append(marker + ' Movement ' + values)
        lines.extend([
            'Dönem Sonu Bakiyesi (III+IV+…+X+XI)',
            f'30 Haziran {year} ' + amounts(capital, profit),
        ])
        return lines

    lines = block('Önceki Dönem', 1000, 100, 2025) + block('Cari Dönem', 2000, 200, 2026)
    monkeypatch.setattr(EC, '_fitz_page_lines', lambda *_: lines)
    monkeypatch.setattr(EC, '_fitz_page_text', lambda *_: '\n'.join(lines))
    monkeypatch.setattr(EC, '_fitz_dense_page_lines', lambda *_: lines)
    rows = EC._parse_equity_page('unused.pdf', 14, 'current', 16)
    closing = [r for r in rows if not r.hierarchy]
    assert [(r.period_type, r.total_equity) for r in closing] == [
        ('prior', 1100), ('current', 2200),
    ]
    assert all('Dönem Sonu Bakiyesi' in r.name for r in closing)


@pytest.mark.parametrize(('label', 'marker'), [
    ('II Yeni Bakiye (I+II)', 'III.'),
    ('2. Hataların Düzeltilmesinin Etkisi', '2.1'),
    ('2. Muhasebe Politikasında Yapılan Değişikliklerin Etkisi', '2.2'),
    ('V İç Kaynaklardan Gerçekleştirilen Sermaye Artırımı', 'VI.'),
    ('VI Ödenmiş Sermaye Enflasyon Düzeltme Farkı', 'VII.'),
    ('VI Hisse Senedine Dönüştürülebilir Tahviller', 'VIII.'),
    ('X Kar Dağıtımı', 'XI.'),
    ('11 Dağıtılan Temettü', '11.1'),
    ('11 Yedeklere Aktarılan Tutarlar', '11.2'),
    ('11 Diğer', '11.3'),
])
def test_clipped_equity_markers_follow_their_unambiguous_source_labels(label, marker):
    # ZIRAATK 2023Q1's narrow marker column clips both roman and subrow digits.
    assert EC._eq_split(label + ' ' + '- ' * 14)[0] == marker


def test_clipped_marker_recovery_does_not_relabel_unknown_or_different_rows():
    assert EC._eq_split('II TMS 8 Uyarınca Yapılan Düzeltmeler ' + '- ' * 14)[0] == 'II.'
    assert EC._eq_split('2. Unknown disclosure ' + '- ' * 14) == (None, '')
    assert EC._eq_split('V Nakden Gerçekleştirilen Sermaye Artırımı ' + '- ' * 14)[0] == 'V.'


@pytest.mark.parametrize('case', [
    'faithful', 'header_mismatch', 'nonzero_adjustment', 'not_adjacent', 'missing_closing',
])
def test_displaced_opening_requires_all_independent_source_checks(monkeypatch, case):
    # TAKAS 2026Q2 p15: these figures print on the date range immediately above
    # the all-dash I row, and III independently repeats every figure.
    opening = '600 33 - 3 - (23) - - - - 8.956 11.711 - 21.280 - 21.280'
    header = opening
    if case == 'header_mismatch':
        header = header.replace('600', '601').replace('21.280', '21.281')
    zeros = '- ' * 16
    adjustment = ('1 ' + '- ' * 12 + '1 - 1') if case == 'nonzero_adjustment' else zeros
    lines = ['Cari Dönem', '1 Ocak 2026-30 Haziran 2026 ' + header]
    if case == 'not_adjacent':
        lines.append('Unrelated source line')
    lines += [
        'I. Önceki dönem sonu bakiyesi ' + zeros,
        'II. TMS 8 uyarınca yapılan düzeltmeler ' + adjustment,
        '2.1 Hataların düzeltilmesinin etkisi ' + zeros,
        '2.2 Muhasebe politikasındaki değişikliklerin etkisi ' + zeros,
        'III. Yeni bakiye (I+II) ' + opening,
        'IV. Toplam kapsamlı gelir ' + '- ' * 12 + '8.300 8.300 - 8.300',
    ]
    lines += [marker + ' Movement ' + zeros for marker in EC._EQ_ROW_SEQ[4:10]]
    lines.append('XI. Kar dağıtımı ' + '- ' * 10 + '5.844 (11.688) - (5.844) - (5.844)')
    if case != 'missing_closing':
        lines.append('Dönem sonu bakiyesi (III+IV+…+X+XI) '
                     '600 33 - 3 - (23) - - - - 14.800 23 8.300 23.736 - 23.736')
    monkeypatch.setattr(EC, '_fitz_page_lines', lambda *_: lines)
    monkeypatch.setattr(EC, '_fitz_page_text', lambda *_: '\n'.join(lines))
    monkeypatch.setattr(EC, '_fitz_dense_page_lines', lambda *_: lines)
    rows = EC._parse_equity_page('unused.pdf', 15, 'current', 16)
    first = next(row for row in rows if row.hierarchy == 'I.')
    assert first.total_equity == (21280 if case == 'faithful' else 0)
    if case == 'faithful':
        assert first.paid_in_capital == 600
        assert first.oci_not_reclassified_2 == -23
        assert EC._eq_chain_closes(EC._eq_score_dicts(rows))


@pytest.mark.parametrize('date', ['30/06/2026', '30.06.2026', '30-06-2026'])
def test_closing_date_is_metadata_and_small_losses_keep_their_columns(date):
    # ICBC 2026Q2 consolidated p15: the source prints the date and all 16
    # values on one closing line. A date is not four extra amount columns.
    line = (f'Dönem Sonu Bakiyesi (III+IV+…+X+XI) {date} '
            '860 (1) - - 100 (49) - - (1) - 3,688 112 1,834 6,543 - 6,543')
    expected = [860, -1, 0, 0, 100, -49, 0, 0, -1, 0, 3688, 112, 1834, 6543, 0, 6543]
    assert EC._parse_row_tokens(line, 16) == expected
    assert EC._try_fit(expected, 16) == expected
    assert date not in EC._eq_split(line)[1]


def test_date_metadata_rule_does_not_mask_monetary_thousands_groups():
    amounts = '1.234.567 30.006.026 30,006,026 (54)'
    assert EC._mask_label_refs(amounts) == amounts
