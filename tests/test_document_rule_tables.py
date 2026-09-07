import fitz
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.audit_reports.document_evidence import page_evidence
from src.audit_reports.document_rule_tables import underline_candidates
from src.audit_reports.document_structure import _ruled_candidates
from src.audit_reports.document_table_context import _grid


def test_one_row_table_from_cell_underlines_preserves_zero_dash_and_repeated_values():
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_rect((40, 100, 450, 100.5), fill=(0, 0, 0))
        columns = (40, 190, 280, 365, 450)
        for left, right in zip(columns, columns[1:]):
            page.draw_rect((left, 120, right, 120.5), fill=(0, 0, 0))
        for x, value in ((45, "Shareholder"), (200, "Paid"), (290, "Unpaid"), (375, "Other")):
            page.insert_text((x, 95), value)
        for x, value in ((45, "Example Bank"), (200, "1,000"), (290, "0"), (375, "-")):
            page.insert_text((x, 116), value)
        source = page_evidence(page)
        tables = underline_candidates(source, [])
        assert len(tables) == 1
        table = tables[0]
        assert [[cell["text"] for cell in row["cells"]] for row in table["rows"]] == [
            ["Shareholder", "Paid", "Unpaid", "Other"], ["Example Bank", "1,000", "0", "-"]]
        assert table["header_association_verified"] is False
        assert len(table["source_drawing_ids"]) == 5
        assert underline_candidates(source, [table]) == []


def test_separate_underlined_phrases_do_not_become_a_table():
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_line((40, 100), (450, 100))
        for left, right in ((40, 140), (190, 270), (350, 450)):
            page.draw_line((left, 120), (right, 120))
            page.insert_text((left, 115), "100")
        assert underline_candidates(page_evidence(page), []) == []


def test_logo_paths_cannot_pull_the_table_border_through_its_words():
    with fitz.open() as doc:
        page = doc.new_page()
        # A dense ornamental outline above the table, similar to outlined logo
        # lettering. Its x coordinates must not join the grid's snap clusters.
        points = [fitz.Point(x, 30 if i % 2 else 60) for i, x in enumerate(range(40, 102, 2))]
        page.draw_polyline(points)
        for x in (40, 250, 480):
            page.draw_rect((x, 140, x + .5, 240), fill=(0, 0, 0))
        for y in (140, 170, 240):
            page.draw_rect((40, y, 480, y + .5), fill=(0, 0, 0))
        for x, y, value in ((44, 160, "Pension Fund Obligations"), (254, 160, "Audit response"),
                            (44, 190, "The full opening words must remain."), (254, 190, "Independent review.")):
            page.insert_text((x, y), value)
        tables = _ruled_candidates(page, page_evidence(page))
        assert len(tables) == 1
        assert tables[0]["rows"][0]["cells"][0]["text"] == "Pension Fund Obligations"
        assert tables[0]["rows"][1]["cells"][0]["text"].startswith("The full opening")
        assert all(c["source_text_matches"] for r in tables[0]["rows"] for c in r["cells"])


def daily_source():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_risk_tomk.json').read_text(encoding='utf-8'))
    return next(p for p in fixture['source_pages'] if p['page'] == 30)


def test_multiline_underlines_keep_both_currencies_all_rates_and_existing_alternatives():
    source = daily_source()
    tables = underline_candidates(source, [])
    assert len(tables) == 2
    # Preserve the existing one-row prior table's identity as new patterns arrive.
    assert tables[0]['id'] == 'p30:underline0'
    assert tables[0]['rows'][1]['cells'][1]['text'] == '18,6983 TL'
    daily = tables[1]
    assert daily['row_count'] == 2  # Only two printed bands, not invented rules.
    assert daily['n_cols'] == 3
    assert [c['text'] for c in daily['rows'][0]['cells']] == ['', 'USD', 'EURO']
    assert daily['source_drawing_ids'] == [1, 3, 5, 6, 8, 10]
    assert daily['rows'][1]['cells'][1]['text'].splitlines() == [
        '27,3767 TL', '27,3767 TL', '27,3752 TL', '27,2640 TL', '27,2108 TL', '27,1751 TL']
    assert daily['rows'][1]['cells'][2]['text'].splitlines() == [
        '29,0305 TL', '29,0305 TL', '28,8083 TL', '28,7853 TL', '28,8183 TL', '28,9027 TL']
    assert daily['header_association_verified'] is False
    ids = [i for r in daily['rows'] for c in r['cells'] for i in c['word_ids']]
    assert ids and len(ids) == len(set(ids)) == 59
    assert set(ids) == set(range(148, 207))
    assert _grid(daily) is not None
    numeric = {'method': 'legacy_numeric_geometry', 'bbox': [125, 272, 539, 340]}
    assert underline_candidates(source, [numeric]) == tables
    assert len(underline_candidates(source, [daily])) == 1


@pytest.mark.parametrize('change', ['missing_heading', 'cross_column_word', 'row_gap', 'missing_cell', 'rule_mismatch', 'intermediate_rule'])
def test_multiline_underlines_abstain_on_ambiguous_source(change):
    source = deepcopy(daily_source())
    if change == 'missing_heading':
        source['words'] = [w for w in source['words'] if w['id'] != 149]
    elif change == 'cross_column_word':
        next(w for w in source['words'] if w['id'] == 153)['bbox'][0] = 295
    elif change == 'row_gap':
        source['words'] = [w for w in source['words'] if w['id'] not in range(157, 187)]
    elif change == 'missing_cell':
        source['words'] = [w for w in source['words'] if w['id'] not in (163, 164)]
    elif change == 'rule_mismatch':
        next(d for d in source['drawings'] if d['id'] == 3)['bbox'][0] += 5
    else:
        source['drawings'].append({'id': 9999, 'bbox': [126, 308, 539, 308.5], 'path_items': 1, 'type': 'f'})
    assert not any(t.get('body_source_line_count') for t in underline_candidates(source, []))


def test_compound_tax_header_cannot_be_reduced_to_its_last_dated_line():
    fixture = json.loads((Path(__file__).parent / 'fixtures/document_underline_compound_header.json').read_text(encoding='utf-8'))
    assert not any(t.get('body_source_line_count') for t in underline_candidates(fixture['source_page'], []))
