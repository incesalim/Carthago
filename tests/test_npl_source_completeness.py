"""Source-backed NPL periods, signed flows, nil fragments and category detail."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from src.audit_reports import npl_movement as npl
from src.audit_reports.npl_source_validation import check_source_cells
from src.audit_reports.source_capture import _capture_lane, upsert_lane_capture
from src.audit_reports.schema import init_schema
from src.audit_reports.units import UnitContext
from scripts.revalidate_audit_db import _merge_source_capture, _npl_movement_rows
from src.audit_reports.validator import ValidationResult, check_npl_movement


FILINGS = json.loads((Path(__file__).parent / 'fixtures/garan_npl_source.json').read_text(encoding='utf-8'))['filings']
KEYS = ['opening_balance', 'additions', 'transfers_in', 'transfers_out', 'collections',
        'write_offs', 'sold', 'other_movement', 'fx_diff', 'closing_balance', 'provision', 'net_balance']
SOURCE_ROWS = {
    'unconsolidated': [(131, [9, 10, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23]),
                       (131, [27, 28, 29, 30, 31, 33, 35, 41, 42, 43, 44, 45])],
    'consolidated': [(135, [27, 28, 29, 30, 31, 32, 33, 37, 38, 39, 40, 41]),
                     (136, [9, 10, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23])],
}


def expected(filing):
    pages = {p['number']: p['lines'] for p in filing['pages']}
    out = {}
    for period, (page, orders) in zip(('current', 'prior'), SOURCE_ROWS[filing['source']['kind']]):
        for field, order in zip(KEYS, orders, strict=True):
            tokens = pages[page][order - 1].split()[-3:]
            if page == 131 and order == 33:
                # Two actual III dash glyphs bracket the label baseline.
                assert pages[page][31] == pages[page][33] == '-'
                tokens = ['--', *pages[page][order - 1].split()[-2:]]
            for group, token in zip(('III', 'IV', 'V'), tokens, strict=True):
                value = 0 if token in {'-', '--'} else int(token.replace(',', '').strip('()'))
                if token.startswith('('):
                    value = -value
                out.setdefault((period, group), {'page': page})[field] = value
    return out


def source_capture(filing):
    doc = {p['number'] - 1: p['capture_xy_lines'] for p in filing['pages']}
    with patch('src.audit_reports.source_capture._word_token_lines', side_effect=lambda lines: lines):
        return _capture_lane(doc, [], 'npl_movement', tuple(sorted(n + 1 for n in doc)), None)


def normalized(filing):
    return npl._extract_bounded_disclosure({p['number']: p['xy_lines'] for p in filing['pages']})


@pytest.mark.parametrize('filing', FILINGS, ids=lambda f: f['source']['kind'])
def test_existing_extractor_reads_both_periods_and_all_main_cells(monkeypatch, filing):
    pages = {p['number']: p['xy_lines'] for p in filing['pages']}
    monkeypatch.setattr(npl, '_HAS_FITZ', True)
    monkeypatch.setattr(npl, '_fitz_page_count', lambda _: max(pages))
    monkeypatch.setattr(npl, '_fitz_page_line_tokens', lambda _, page: pages.get(page + 1, []))
    monkeypatch.setattr(npl, '_fitz_page_text', lambda _, page: '\n'.join(
        ' '.join(t for _, _, t in row) for row in pages.get(page + 1, [])))
    rows = npl.extract_from_pdf('retained-source.pdf').rows
    assert len(rows) == 6
    assert {(r.period_type, r.group_code): {field: getattr(r, field) for field in ['page', *KEYS]}
            for r in rows} == expected(filing)
    assert all(r.accrual_movement is None for r in rows)
    result = check_npl_movement([asdict(r) for r in rows])
    assert result.failed == 0


@pytest.mark.parametrize('filing', FILINGS, ids=lambda f: f['source']['kind'])
def test_source_cells_include_categories_and_do_not_fold_other_into_sales(filing):
    capture = source_capture(filing)
    assert len(capture.data_rows) == 30 and all(r.mapped_key for r in capture.data_rows)
    assert [r.line_text for r in capture.lines] == [l for p in filing['pages'] for l in p['lines']]
    assert all(r.mapped_key == 'other_movement' for r in capture.data_rows if r.line_text.startswith('Other'))
    result = check_source_cells([asdict(r) for r in normalized(filing)], [asdict(r) for r in capture.lines], 1)
    assert (result.passed, result.failed, result.skipped) == (84, 0, 0)
    if filing['source']['kind'] == 'unconsolidated':
        writeoff = next(r for r in capture.data_rows if r.line_order == 33)
        cell = json.loads(writeoff.cell_sources_json)['cells'][0]
        assert cell['text'] == '--' and cell['state'] == 'dash'
        assert [r['line_order'] for r in cell['fragments']] == [32, 34]


@pytest.mark.parametrize('defect', ['missing_prior', 'missing_zero', 'wrong_other', 'wrong_writeoff',
                                  'wrong_period', 'forged_fragment', 'missing_cell_evidence'])
def test_source_gate_rejects_missing_or_wrong_values_and_provenance(defect):
    filing = FILINGS[0]
    rows = [asdict(r) for r in normalized(filing)]
    source = [asdict(r) for r in source_capture(filing).lines]
    if defect == 'missing_prior':
        rows = [r for r in rows if r['period_type'] == 'current']
    elif defect == 'missing_zero':
        rows[0]['other_movement'] = None
    elif defect in {'wrong_other', 'wrong_writeoff'}:
        rows[-1]['other_movement' if defect == 'wrong_other' else 'write_offs'] += 1
    elif defect == 'missing_cell_evidence':
        for line in source:
            line['cell_sources_json'] = None
    else:
        row = next(r for r in source if r['cell_sources_json'])
        data = json.loads(row['cell_sources_json'])
        if defect == 'wrong_period':
            data['period_type'] = 'prior'
        else:
            data['cells'][0]['fragments'][0]['token_order'] = 0
        row['cell_sources_json'] = json.dumps(data)
    assert check_source_cells(rows, source, 1).failed > 0


def test_native_npl_checks_reach_persisted_revalidation_and_scale_units():
    filing = FILINGS[0]
    with sqlite3.connect(':memory:') as conn:
        init_schema(conn)
        report = npl.NplMovementReport(rows=normalized(filing))
        npl.upsert(conn, 'GARAN', '2022Q4', 'unconsolidated', report, unit=UnitContext('bin', 1))
        upsert_lane_capture(conn, 'GARAN', '2022Q4', 'unconsolidated', source_capture(filing))
        conn.execute("UPDATE bank_audit_npl_movement SET other_movement=NULL WHERE group_code='V'")
        result = ValidationResult()
        _merge_source_capture(conn, 'GARAN', '2022Q4', 'unconsolidated', 'npl_movement', result, 6)
        assert any(f['check'] == 'npl_source_cell_missing' for f in result.failures)
        rows = _npl_movement_rows(conn, 'GARAN', '2022Q4', 'unconsolidated')
        assert rows[0]['other_movement'] == 0


def test_source_cell_checks_apply_declared_units_and_refuse_unknown_units():
    filing = FILINGS[0]
    source = [asdict(r) for r in source_capture(filing).lines]
    rows = [asdict(r) for r in normalized(filing)]
    for row in rows:
        for key in KEYS:
            row[key] *= 1000
    assert check_source_cells(rows, source, 1000).failed == 0
    assert check_source_cells(rows, source, 1).failed > 0
    assert check_source_cells(rows, source, None).failed == 1


def test_additive_other_migration_preserves_old_snapshots_and_nulls():
    from src.audit_reports.schema import DDL

    with sqlite3.connect(':memory:') as conn:
        legacy = DDL.replace('    other_movement     REAL,\n', '')
        assert legacy != DDL
        conn.executescript(legacy)
        conn.execute("INSERT INTO bank_audit_npl_movement (bank_ticker,period,kind,group_code,period_type,closing_balance) VALUES ('X','2022Q4','consolidated','III','current',100)")
        assert _npl_movement_rows(conn, 'X', '2022Q4', 'consolidated')[0]['other_movement'] is None
        migration = Path(__file__).resolve().parents[1] / 'web/migrations/0051_npl_other_movement.sql'
        conn.executescript(migration.read_text(encoding='utf-8'))
        init_schema(conn)
        assert conn.execute('SELECT closing_balance,other_movement FROM bank_audit_npl_movement').fetchone() == (100, None)


def test_other_is_exact_and_never_a_subsequent_other_loans_stock_label():
    assert npl._match_row_label('Other (***) - - (254,928)') == 'other_movement'
    assert npl._match_row_label('Other loans (gross) - - 254,928') is None
    assert npl._match_row_label('Write down /Write-offs (-)(*) 1,860 5,134 8,248,127') == 'write_offs'


def test_other_category_is_not_double_counted_as_a_movement():
    text = '''Balances at end of prior period 100 200 300
Debt sale (-) 100 200 300
Corporate and commercial loans 50 100 150
Retail loans 30 60 90
Credit Cards 10 20 30
Other 10 20 30
Balances at end of period - - -
Provisions (-) - - -
Net balances - - -'''
    rows = npl._extract_from_block(1, text)
    assert len(rows) == 3
    assert all(row.other_movement is None for row in rows)
    assert [row.sold for row in rows] == [100, 200, 300]


def test_dipnotes_preserve_source_wording_and_conflicting_printed_markers():
    filing = next(f for f in FILINGS if f['source']['kind'] == 'consolidated')
    source = [asdict(r) for r in source_capture(filing).lines]
    others = [json.loads(r['cell_sources_json']) for r in source
              if r['mapped_key'] == 'other_movement']
    current, prior = others
    assert current['note_links'][0]['marker'] == '(***)'
    assert current['note_links'][0]['status'] == 'ambiguous'
    assert 'sale of non-performing loans' in current['note_links'][0]['targets'][0]['text']
    candidate = current['note_links'][1]
    assert (candidate['marker'], candidate['status']) == ('(****)', 'candidate')
    assert '254,928' in candidate['targets'][0]['text']
    assert prior['note_links'][0]['status'] == 'resolved'
    assert prior['note_links'][0]['targets'][0]['text'] == candidate['targets'][0]['text']
    corrupted = next(r for r in source if r['mapped_key'] == 'other_movement')
    data = json.loads(corrupted['cell_sources_json'])
    data['note_links'][0]['targets'][0]['text'] = 'Invented explanation'
    corrupted['cell_sources_json'] = json.dumps(data)
    assert check_source_cells([asdict(r) for r in normalized(filing)], source, 1).failed > 0


@pytest.mark.parametrize('defect', ['removed', 'misaligned', 'ambiguous'])
def test_nil_fragment_recovery_does_not_invent_or_guess_a_cell(defect):
    from src.audit_reports.npl_disclosure import recover_nil_fragments

    filing = next(f for f in FILINGS if f['source']['kind'] == 'unconsolidated')
    lines = copy.deepcopy(filing['pages'][0]['capture_xy_lines'])
    if defect == 'removed':
        lines[31] = lines[33] = []
    elif defect == 'misaligned':
        for i in (31, 33):
            lines[i] = [(x0 + 20, x1 + 20, t) for x0, x1, t in lines[i]]
    else:
        # Each dash lies between two plausible incomplete rows in the same
        # column. Neither can be assigned exclusively to the write-off row.
        lines[30] = copy.deepcopy(lines[32])
        lines[34] = copy.deepcopy(lines[32])
    corrected, fragments = recover_nil_fragments(lines)
    assert 32 not in fragments
    assert corrected[32] == lines[32]


def test_npl_changed_fact_upsert_preserves_timestamps_and_missing_is_not_zero():
    with sqlite3.connect(':memory:') as conn:
        init_schema(conn)
        row = npl.NplGroupRow('III', opening_balance=100, other_movement=None)
        report = npl.NplMovementReport(rows=[row])
        unit = UnitContext('bin', 1)
        npl.upsert(conn, 'X', '2022Q4', 'consolidated', report, unit=unit)
        conn.execute("UPDATE bank_audit_npl_movement SET extracted_at='old'")
        npl.upsert(conn, 'X', '2022Q4', 'consolidated', copy.deepcopy(report), unit=unit)
        assert conn.execute('SELECT extracted_at,other_movement FROM bank_audit_npl_movement').fetchone() == ('old', None)
        row.other_movement = 0
        npl.upsert(conn, 'X', '2022Q4', 'consolidated', report, unit=unit)
        assert conn.execute('SELECT extracted_at,other_movement FROM bank_audit_npl_movement').fetchone() != ('old', None)
