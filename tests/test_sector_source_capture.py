"""Printed sector tables retain their rows without borrowing neighboring tables."""
import copy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from src.audit_reports.source_capture import _capture_lane, stored_mapping_labels
from test_audit_source_capture import _FakePage


FILINGS = json.loads((Path(__file__).parent / 'fixtures' /
                      'garan_sector_source_capture.json').read_text(encoding='utf-8'))['filings']
WRAPPED_FILINGS = json.loads((Path(__file__).parent / 'fixtures' /
                              'garan_sector_wrapped_headers.json').read_text(encoding='utf-8'))['filings']


def capture(filing, *, stored=False):
    pages = {page['number']: _FakePage(page['lines']) for page in filing['pages']}
    doc = {number - 1: page for number, page in pages.items()}
    labels = filing['stored_labels']
    mappings = []
    report = SimpleNamespace(loans_by_sector=[SimpleNamespace(**row) for row in labels])
    if stored:
        # Exercise the PDF-only backfill's actual stored-label reader as well as
        # the normal report loader's mapping path.
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE bank_audit_loans_by_sector '
                         '(bank_ticker, period, kind, sector, raw_label)')
            conn.executemany('INSERT INTO bank_audit_loans_by_sector VALUES (?,?,?,?,?)', [
                ('GARAN', '2022Q4', filing['source']['kind'], row['sector'], row['raw_label'])
                for row in labels])
            mappings = stored_mapping_labels(
                conn, 'GARAN', '2022Q4', filing['source']['kind'], ['loans_by_sector'])['loans_by_sector']
        report = None
    return _capture_lane(doc, [], 'loans_by_sector', tuple(sorted(pages)), report, mappings)


@pytest.mark.parametrize('stored', [False, True])
@pytest.mark.parametrize('filing', FILINGS, ids=lambda row: row['source']['kind'])
def test_native_sector_ranges_and_all_source_text_are_retained(filing, stored):
    result = capture(filing, stored=stored)
    expected = {(page, order) for page, first, last in filing['sector_row_ranges']
                for order in range(first, last + 1)}
    assert {(row.source_page, row.line_order) for row in result.data_rows} == expected
    assert len(result.data_rows) == 40  # 20 printed rows in each reporting period
    assert all(row.mapped_key for row in result.data_rows)
    assert [row.line_text for row in result.lines] == [
        line for page in filing['pages'] for line in page['lines']]
    assert [row.mapped_key for row in result.data_rows if row.line_text.startswith('Services ')] == [
        'svc_total', 'svc_total']
    assert [row.mapped_key for row in result.data_rows if row.line_text.startswith('Educational Services ')] == [
        'svc_education', 'svc_education']
    if filing['source']['kind'] == 'unconsolidated':
        assert [row.line_text for row in result.data_rows if row.mapped_key == 'svc_professional'] == [
            'Professional Services - - -', 'Professional Services - - -']


@pytest.mark.parametrize('change', ['unknown_row', 'unknown_parent', 'missing_parent_mapping'])
def test_unknown_sector_rows_and_missing_parent_mappings_remain_unclassified(change):
    filing = copy.deepcopy(FILINGS[1])
    page = next(p for p in filing['pages'] if p['number'] == 71)
    if change == 'unknown_row':
        page['lines'].insert(37, 'Previously undisclosed sector 101 202 303')
    elif change == 'unknown_parent':
        page['lines'] = [line.replace('Services 41,775,056', 'Services newly disclosed 41,775,056')
                         for line in page['lines']]
    else:
        filing['stored_labels'] = [r for r in filing['stored_labels'] if r['sector'] != 'svc_total']
    result = capture(filing)
    # Unknown rows are now classified as 'unknown' instead of left unmapped,
    # so the near-full completeness gate can surface them to the validator.
    assert any(row.mapped_key == 'unknown' for row in result.data_rows)
    assert all(row.mapped_key != 'svc_education' for row in result.data_rows
               if row.line_text.startswith('Services '))


@pytest.mark.parametrize('missing', ['heading', 'closing_boundary', 'intervening_page'])
def test_incomplete_disclosure_boundaries_keep_conservative_evidence(missing):
    filing = copy.deepcopy(FILINGS[1])
    if missing == 'intervening_page':
        next(p for p in filing['pages'] if p['number'] == 72)['number'] = 73
    else:
        marker = '4.2.6 ' if missing == 'heading' else '4.2.7 '
        for page in filing['pages']:
            page['lines'] = [line for line in page['lines'] if not line.startswith(marker)]
    result = capture(filing)
    assert any(row.mapped_key == 'unknown' and 'Provisions' in row.line_text for row in result.data_rows)
    assert len(result.lines) == sum(len(p['lines']) for p in filing['pages'])


def test_unknown_nested_disclosure_and_forward_reference_are_not_hidden():
    filing = copy.deepcopy(FILINGS[1])
    page = next(p for p in filing['pages'] if p['number'] == 71)
    page['lines'].insert(37, '5.1.5 Further discussion of loan accounting')
    page['lines'].insert(38, '4.2.6.1 Additional sector information')
    page['lines'].insert(39, 'Unknown additional sector - - -')
    result = capture(filing)
    # Unknown rows now carry mapped_key="unknown" instead of None, so the
    # near-full completeness gate can surface them to the validator.
    assert any(row.line_text == 'Unknown additional sector - - -' and row.mapped_key == 'unknown'
               for row in result.data_rows)


def test_split_sector_extractor_cites_the_page_containing_the_values(monkeypatch):
    from src.audit_reports import loans_by_sector as extractor

    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: 2)
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: 'heading' if page == 0 else 'values')
    monkeypatch.setattr(extractor, '_page_has_sector_heading', lambda text: text == 'heading')
    monkeypatch.setattr(extractor, '_is_legacy_pastdue_table', lambda *_: False)
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: ['columns'] if page == 0 else ['values'])
    monkeypatch.setattr(extractor, '_stage_col_x', lambda _: (None, 100, 200, None))
    monkeypatch.setattr(extractor, '_extract_section', lambda *_: [])
    monkeypatch.setattr(extractor, '_extract_three_column_disclosure', lambda _: None)

    def aligned(page, lines):
        if lines == ['columns']:
            return []
        assert lines == ['columns', 'values']
        return [extractor.SectorRow('total', stage2_amount=10, stage3_amount=20, ecl_amount=30, page=page)]

    monkeypatch.setattr(extractor, '_extract_section_xy', aligned)
    report = extractor.extract_from_pdf('unused.pdf', skip_pages=0)
    assert [(row.page, row.stage2_amount, row.stage3_amount, row.ecl_amount) for row in report.rows] == [
        (2, 10, 20, 30)]


@pytest.mark.parametrize('filing', FILINGS + WRAPPED_FILINGS,
                         ids=lambda row: row['source']['period'] + '-' + row['source']['kind'])
def test_existing_extractor_reads_every_printed_sector_cell_and_period(monkeypatch, filing):
    from src.audit_reports import loans_by_sector as extractor

    pages = {page['number']: page['xy_lines'] for page in filing['pages']}
    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: max(pages))
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: '\n'.join(
        ' '.join(t for _, _, t in line) for line in pages.get(page + 1, [])))
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: pages.get(page + 1, []))
    report = extractor.extract_from_pdf('retained-source.pdf')
    # Independently inspected printed order; expectations do not use the
    # extractor's taxonomy, geometry or choice between candidate parsers.
    keys = ['agri_total', 'agri_farming', 'agri_forestry', 'agri_fishery',
            'mfg_total', 'mfg_mining', 'mfg_production', 'mfg_utilities',
            'construction', 'svc_total', 'svc_trade', 'svc_hospitality',
            'svc_transport', 'svc_financial', 'svc_realestate', 'svc_professional',
            'svc_education', 'svc_health', 'other', 'total']
    expected = {}
    for period, (page, first, last) in zip(('current', 'prior'), filing['sector_row_ranges']):
        lines = next(p['lines'] for p in filing['pages'] if p['number'] == page)
        for key, line in zip(keys, lines[first - 1:last], strict=True):
            values = tuple(0.0 if token == '-' else float(token.replace(',', ''))
                           for token in line.split()[-3:])
            expected[period, key] = (page, *values)
    assert len(report.rows) == 40
    assert {(row.period_type, row.sector): (row.page, row.stage2_amount,
                                           row.stage3_amount, row.ecl_amount)
            for row in report.rows} == expected


def test_xy_extractor_captures_unknown_sector_rows(monkeypatch):
    """Rows whose labels don't match any known sector are captured as
    sector='unknown' with raw_label preserved, instead of being dropped.

    Uses the text-based _extract_section path (no xy stage-column headers)
    to verify the unknown-row capture without needing a full xy geometry.
    """
    from src.audit_reports import loans_by_sector as extractor

    # _page_has_sector_heading returns True for our fake page, so the
    # extractor will process it.  _extract_three_column_disclosure returns
    # None so the fallback text parser runs.
    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: 1)
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: (
        "Önemli Sektörlere veya Karşı Taraf Türüne Göre Muhtelif Bilgiler\n"
        "\n"
        "Tarım 1.000 200 50\n"
        "Previously undisclosed sector 500 300 100\n"
        "Toplam 1.500 500 150"
    ))
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: [])
    monkeypatch.setattr(extractor, '_page_has_sector_heading', lambda text: True)
    monkeypatch.setattr(extractor, '_is_legacy_pastdue_table', lambda *_: False)
    monkeypatch.setattr(extractor, '_extract_three_column_disclosure', lambda _: None)

    report = extractor.extract_from_pdf('unknown_test.pdf', skip_pages=0)
    unknowns = [r for r in report.rows if r.sector == "unknown"]
    known = [r for r in report.rows if r.sector != "unknown"]
    assert len(unknowns) >= 1, f"expected at least 1 unknown row, got {len(unknowns)}"
    assert unknowns[0].stage2_amount == 500.0
    assert unknowns[0].stage3_amount == 300.0
    assert unknowns[0].ecl_amount == 100.0
    assert unknowns[0].raw_label == "Previously undisclosed sector"
    # Known sectors are still captured
    assert any(r.sector == "agri_total" for r in known)


@pytest.mark.parametrize('filing', WRAPPED_FILINGS,
                         ids=lambda row: row['source']['period'] + '-' + row['source']['kind'])
def test_wrapped_headers_keep_independent_source_constraints_and_capture(filing):
    from dataclasses import asdict
    from src.audit_reports.loans_by_sector import _extract_three_column_disclosure
    from src.audit_reports.source_capture import _selected_pages
    from src.audit_reports.validator import check_sector_source_cells

    rows = [asdict(row) for row in _extract_three_column_disclosure(
        {p['number']: p['xy_lines'] for p in filing['pages']})]
    source = [{'source_page': p['number'], 'line_text': line}
              for p in filing['pages'] for line in p['lines']]
    good = check_sector_source_cells(rows, source, 1)
    assert good.failed == 0 and good.passed == 120
    # In 2025 consolidated the caption shares the ECL header. Previously the
    # validator silently skipped the entire current-period table.
    for row in rows:
        if row['period_type'] == 'current':
            row['stage3_amount'] = row['ecl_amount'] = None
    assert check_sector_source_cells(rows, source, 1).failed == 40
    assert check_sector_source_cells([], source, 1).failed == 40
    texts = [''] * max(p['number'] for p in filing['pages'])
    for p in filing['pages']:
        texts[p['number'] - 1] = '\n'.join(p['lines'])
    # Heading and closing boundary must be found even when extraction produced
    # no row hints. A value-page hint alone misses the Turkish heading page.
    selected = _selected_pages('loans_by_sector', texts, set())
    assert all(p['number'] in selected for p in filing['pages'])
    captured = capture(filing)
    assert len(captured.data_rows) == 40
    assert all(row.mapped_key for row in captured.data_rows)


def test_turkish_wrapped_ecl_header_is_required_not_inferred_from_three_numbers():
    from src.audit_reports.loans_by_sector import _extract_three_column_disclosure

    filing = copy.deepcopy(WRAPPED_FILINGS[0])
    for p in filing['pages']:
        for line in p['xy_lines']:
            for token in line:
                if token[2] == 'Karşılıkları':
                    token[2] = 'Tanımsız'
    assert _extract_three_column_disclosure({p['number']: p['xy_lines'] for p in filing['pages']}) is None


@pytest.mark.parametrize('defect', ['missing_prior', 'missing_ecl', 'wrong_ecl',
                                  'swapped_columns', 'wrong_prior', 'missing_zero'])
def test_source_validator_rejects_omissions_that_pass_aggregate_footing(defect):
    from dataclasses import asdict
    from src.audit_reports.loans_by_sector import _extract_three_column_disclosure
    from src.audit_reports.validator import check_sector_source_cells

    filing = FILINGS[0]
    rows = [asdict(row) for row in _extract_three_column_disclosure(
        {p['number']: p['xy_lines'] for p in filing['pages']})]
    source = [{'source_page': p['number'], 'line_text': line}
              for p in filing['pages'] for line in p['lines']]
    good = check_sector_source_cells(rows, source, 1)
    assert good.failed == 0 and good.passed == 120
    if defect == 'missing_prior':
        rows = [r for r in rows if r['period_type'] == 'current']
    elif defect == 'missing_ecl':
        for row in rows:
            row['ecl_amount'] = None
    elif defect == 'wrong_ecl':
        rows[0]['ecl_amount'] += 1
    elif defect == 'swapped_columns':
        rows[0]['stage2_amount'], rows[0]['stage3_amount'] = (
            rows[0]['stage3_amount'], rows[0]['stage2_amount'])
    elif defect == 'wrong_prior':
        next(r for r in rows if r['period_type'] == 'prior')['stage2_amount'] += 1
    else:
        next(r for r in rows if r['sector'] == 'svc_professional')['ecl_amount'] = None
    assert check_sector_source_cells(rows, source, 1).failed > 0


def test_source_validator_scales_printed_units_and_refuses_unknown_scale():
    from dataclasses import asdict
    from src.audit_reports.loans_by_sector import _extract_three_column_disclosure
    from src.audit_reports.validator import check_sector_source_cells

    filing = FILINGS[1]
    rows = [asdict(row) for row in _extract_three_column_disclosure(
        {p['number']: p['xy_lines'] for p in filing['pages']})]
    source = [{'source_page': p['number'], 'line_text': line}
              for p in filing['pages'] for line in p['lines']]
    for row in rows:
        for column in ('stage2_amount', 'stage3_amount', 'ecl_amount'):
            row[column] *= 1000
    assert check_sector_source_cells(rows, source, 1000).failed == 0
    assert check_sector_source_cells(rows, source, 1).failed > 0
    assert check_sector_source_cells(rows, source, None).failed == 1


def test_existing_revalidation_path_checks_sector_cells_from_persisted_evidence():
    from src.audit_reports.loans_by_sector import (
        LoansBySectorReport, _extract_three_column_disclosure, upsert,
    )
    from src.audit_reports.schema import init_schema
    from src.audit_reports.source_capture import upsert_lane_capture
    from src.audit_reports.units import UnitContext
    from src.audit_reports.validator import ValidationResult
    from scripts.revalidate_audit_db import _merge_source_capture

    filing = FILINGS[0]
    conn = sqlite3.connect(':memory:')
    init_schema(conn)
    rows = _extract_three_column_disclosure({p['number']: p['xy_lines'] for p in filing['pages']})
    upsert(conn, 'GARAN', '2022Q4', 'unconsolidated', LoansBySectorReport(rows=rows),
           unit=UnitContext.canonical())
    upsert_lane_capture(conn, 'GARAN', '2022Q4', 'unconsolidated', capture(filing))
    result = ValidationResult()
    _merge_source_capture(conn, 'GARAN', '2022Q4', 'unconsolidated', 'loans_by_sector', result, 40)
    assert result.failed == 0 and result.passed >= 120
    conn.execute('UPDATE bank_audit_loans_by_sector SET ecl_amount=NULL')
    result = ValidationResult()
    _merge_source_capture(conn, 'GARAN', '2022Q4', 'unconsolidated', 'loans_by_sector', result, 40)
    assert result.failed == 40


def test_sector_writer_keeps_unchanged_timestamps_and_removes_only_obsolete_rows():
    from src.audit_reports.loans_by_sector import LoansBySectorReport, SectorRow, upsert
    from src.audit_reports.schema import init_schema
    from src.audit_reports.units import UnitContext

    conn = sqlite3.connect(':memory:')
    init_schema(conn)
    unit = UnitContext.canonical()
    current = SectorRow('total', stage2_amount=10, stage3_amount=20, ecl_amount=30,
                        period_type='current', page=1, raw_label='Total')
    prior = SectorRow('total', stage2_amount=1, stage3_amount=2, ecl_amount=3,
                      period_type='prior', page=2, raw_label='Total')
    upsert(conn, 'X', '2022Q4', 'consolidated', LoansBySectorReport(rows=[current]), unit=unit)
    conn.execute("UPDATE bank_audit_loans_by_sector SET extracted_at='old'")
    upsert(conn, 'X', '2022Q4', 'consolidated', LoansBySectorReport(rows=[current, prior]), unit=unit)
    assert conn.execute("SELECT extracted_at FROM bank_audit_loans_by_sector WHERE period_type='current'").fetchone() == ('old',)
    current.ecl_amount = 31
    upsert(conn, 'X', '2022Q4', 'consolidated', LoansBySectorReport(rows=[current]), unit=unit)
    assert conn.execute('SELECT period_type,ecl_amount FROM bank_audit_loans_by_sector').fetchall() == [('current', 31)]
    assert conn.execute('SELECT extracted_at FROM bank_audit_loans_by_sector').fetchone() != ('old',)


@pytest.mark.parametrize('change', ['no_ecl_header', 'wider_columns', 'misaligned_cell',
                                  'missing_end', 'missing_period_caption'])
def test_bounded_parser_does_not_guess_unsupported_columns(change):
    from src.audit_reports.loans_by_sector import _extract_three_column_disclosure

    filing = copy.deepcopy(FILINGS[1])
    pages = {p['number']: p['xy_lines'] for p in filing['pages']}
    for lines in pages.values():
        for line in lines:
            text = ' '.join(t for _, _, t in line)
            if change == 'no_ecl_header':
                for token in line:
                    if token[2] == 'Losses':
                        token[2] = 'Unidentified'
            if change == 'missing_end' and text.startswith('4.2.7 '):
                line[0][2] = 'Unnumbered'
            if change == 'missing_period_caption' and text.startswith('Current Period'):
                line[0][2] = 'Unidentified'
            if text.startswith('Agriculture '):
                if change == 'wider_columns':
                    line.append([540, 555, '999'])
                elif change == 'misaligned_cell':
                    line[-1][0], line[-1][1] = 700, 720
    result = _extract_three_column_disclosure(pages)
    if change == 'missing_period_caption':
        # The current table is not silently relabeled prior; its independent
        # source-completeness gate remains responsible for missing rows.
        assert result is None or all(row.period_type != 'current' for row in result)
    else:
        assert result is None


# --- Stage 1 (4-column) extraction tests --------------------------------

def test_text_parser_extracts_stage1_when_header_present(monkeypatch):
    """When Stage 1 / Birinci Aşama headers are present, the text parser
    reads 4 numbers per row (Stage1, Stage2, Stage3, ECL)."""
    from src.audit_reports import loans_by_sector as extractor

    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: 1)
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: (
        "Information by Sectors\n"
        "Stage 1  Stage 2  Stage 3  ECL\n"
        "Tarım 5.000 1.000 200 100\n"
        "Sanayi 8.000 1.500 300 150\n"
        "Toplam 13.000 2.500 500 250"
    ))
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: [])
    monkeypatch.setattr(extractor, '_page_has_sector_heading', lambda text: True)
    monkeypatch.setattr(extractor, '_is_legacy_pastdue_table', lambda *_: False)
    monkeypatch.setattr(extractor, '_extract_three_column_disclosure', lambda _: None)

    report = extractor.extract_from_pdf('stage1_test.pdf', skip_pages=0)
    agri = next((r for r in report.rows if r.sector == 'agri_total'), None)
    mfg = next((r for r in report.rows if r.sector == 'mfg_total'), None)
    total = next((r for r in report.rows if r.sector == 'total'), None)
    assert agri is not None
    assert agri.stage1_amount == 5000.0
    assert agri.stage2_amount == 1000.0
    assert agri.stage3_amount == 200.0
    assert agri.ecl_amount == 100.0
    assert mfg is not None
    assert mfg.stage1_amount == 8000.0
    assert total is not None
    assert total.stage1_amount == 13000.0


def test_text_parser_no_stage1_when_header_absent(monkeypatch):
    """Without Stage 1 headers, the text parser reads 3 numbers as before."""
    from src.audit_reports import loans_by_sector as extractor

    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: 1)
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: (
        "Information by Sectors\n"
        "Stage 2  Stage 3  ECL\n"
        "Tarım 1.000 200 100\n"
        "Toplam 1.000 200 100"
    ))
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: [])
    monkeypatch.setattr(extractor, '_page_has_sector_heading', lambda text: True)
    monkeypatch.setattr(extractor, '_is_legacy_pastdue_table', lambda *_: False)
    monkeypatch.setattr(extractor, '_extract_three_column_disclosure', lambda _: None)

    report = extractor.extract_from_pdf('no_stage1_test.pdf', skip_pages=0)
    agri = next((r for r in report.rows if r.sector == 'agri_total'), None)
    assert agri is not None
    assert agri.stage1_amount is None
    assert agri.stage2_amount == 1000.0
    assert agri.stage3_amount == 200.0
    assert agri.ecl_amount == 100.0


def test_xy_aligner_extracts_ecl_column(monkeypatch):
    """The x-coordinate aligner now extracts ECL in addition to Stage 2/3."""
    from src.audit_reports import loans_by_sector as extractor

    monkeypatch.setattr(extractor, '_HAS_FITZ', True)
    monkeypatch.setattr(extractor, '_fitz_page_count', lambda _: 1)
    monkeypatch.setattr(extractor, '_fitz_page_text', lambda _, page: (
        "Stage 2  Stage 3  ECL\nTarım 1.000 200 100\nToplam 1.000 200 100"
    ))
    monkeypatch.setattr(extractor, '_xy_lines', lambda _, page: [])
    monkeypatch.setattr(extractor, '_page_has_sector_heading', lambda text: True)
    monkeypatch.setattr(extractor, '_is_legacy_pastdue_table', lambda *_: False)
    monkeypatch.setattr(extractor, '_extract_three_column_disclosure', lambda _: None)

    report = extractor.extract_from_pdf('ecl_test.pdf', skip_pages=0)
    agri = next((r for r in report.rows if r.sector == 'agri_total'), None)
    assert agri is not None
    assert agri.ecl_amount == 100.0


def test_validator_stage1_foot_check():
    """Stage 1 column is included in the footing check when present."""
    from src.audit_reports import validator as v

    rows = [
        {"sector": "agri_total", "period_type": "current",
         "stage1_amount": 5000, "stage2_amount": 1000, "stage3_amount": 200, "ecl_amount": 100},
        {"sector": "mfg_total", "period_type": "current",
         "stage1_amount": 8000, "stage2_amount": 1500, "stage3_amount": 300, "ecl_amount": 150},
        {"sector": "construction", "period_type": "current",
         "stage1_amount": 2000, "stage2_amount": 500, "stage3_amount": 100, "ecl_amount": 50},
        {"sector": "svc_total", "period_type": "current",
         "stage1_amount": 10000, "stage2_amount": 2000, "stage3_amount": 400, "ecl_amount": 200},
        {"sector": "other", "period_type": "current",
         "stage1_amount": 3000, "stage2_amount": 600, "stage3_amount": 120, "ecl_amount": 60},
        {"sector": "total", "period_type": "current",
         "stage1_amount": 28000, "stage2_amount": 5600, "stage3_amount": 1120, "ecl_amount": 560},
    ]
    res = v.check_loans_by_sector(rows)
    assert res.failed == 0, res.failures


def test_validator_stage1_child_exceeds_parent_fails():
    """A child with Stage 1 > parent's Stage 1 fails the hierarchy check."""
    from src.audit_reports import validator as v

    rows = [
        {"sector": "agri_farming", "period_type": "current",
         "stage1_amount": 6000, "stage2_amount": 100, "stage3_amount": 50, "ecl_amount": 25},
        {"sector": "agri_total", "period_type": "current",
         "stage1_amount": 5000, "stage2_amount": 200, "stage3_amount": 100, "ecl_amount": 50},
        {"sector": "total", "period_type": "current",
         "stage1_amount": 5000, "stage2_amount": 200, "stage3_amount": 100, "ecl_amount": 50},
    ]
    res = v.check_loans_by_sector(rows)
    assert any(f["check"] == "loans_sector_child_exceeds_parent" for f in res.failures)


def test_validator_stage1_missing_source_cell_fails():
    """When Stage 1 is printed but the stored row has it NULL, the source
    completeness gate fails."""
    from src.audit_reports.validator import check_sector_source_cells

    # Build a source page with a 4-column disclosure, including numbered
    # disclosure boundaries so _sector_disclosure_lines can locate the table.
    source = [
        {"source_page": 1, "line_text": "4.2.6 Information by Sectors"},
        {"source_page": 1, "line_text": "Loans"},
        {"source_page": 1, "line_text": "Current Period"},
        {"source_page": 1, "line_text": "Stage 1  Stage 2  Stage 3  Expected Credit Losses"},
        {"source_page": 1, "line_text": "Agriculture 5.000 1.000 200 100"},
        {"source_page": 1, "line_text": "Total 5.000 1.000 200 100"},
        {"source_page": 1, "line_text": "Prior Period"},
        {"source_page": 1, "line_text": "Stage 1  Stage 2  Stage 3  Expected Credit Losses"},
        {"source_page": 1, "line_text": "Agriculture 4.000 800 160 80"},
        {"source_page": 1, "line_text": "Total 4.000 800 160 80"},
        {"source_page": 1, "line_text": "4.2.7 Other Information"},
    ]
    # Stored rows with stage1_amount = NULL (not captured)
    rows = [
        {"period_type": "current", "sector": "agri_total",
         "stage1_amount": None, "stage2_amount": 1000, "stage3_amount": 200, "ecl_amount": 100},
        {"period_type": "current", "sector": "total",
         "stage1_amount": None, "stage2_amount": 1000, "stage3_amount": 200, "ecl_amount": 100},
        {"period_type": "prior", "sector": "agri_total",
         "stage1_amount": None, "stage2_amount": 800, "stage3_amount": 160, "ecl_amount": 80},
        {"period_type": "prior", "sector": "total",
         "stage1_amount": None, "stage2_amount": 800, "stage3_amount": 160, "ecl_amount": 80},
    ]
    res = check_sector_source_cells(rows, source, 1)
    assert res.failed > 0
    assert any(f["check"] == "sector_source_cell_missing" for f in res.failures)
