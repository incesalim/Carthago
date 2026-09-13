"""Source-only repairs select missing evidence and publish only changed metadata."""
import json
import sqlite3
import sys

import pytest

from scripts import backfill_audit_source_capture as backfill
from src.audit_reports.schema import init_schema
from src.audit_reports.source_capture import CaptureWriteResult
from src.audit_reports.validator import ValidationResult, upsert_validation


def verdict(check=None):
    result = ValidationResult()
    if check:
        result.add_fail(check, 'source', 1, 0)
    else:
        result.add_pass()
    return result


@pytest.mark.parametrize(('lane', 'check', 'selected'), [
    ('npl_movement', 'npl_source_cells_missing', True),
    ('npl_movement', 'npl_source_cell_reference', True),
    ('npl_movement', 'capture_unmapped_rows', True),
    ('npl_movement', 'npl_source_cell', False),
    ('npl_movement', 'npl_source_cell_missing', False),
    ('npl_movement', 'npl_movement', False),
    ('npl_movement', None, False),
    ('liquidity', 'npl_source_cells_missing', False),
])
def test_only_failing_distinguishes_missing_evidence_from_missing_figures(lane, check, selected):
    with sqlite3.connect(':memory:') as conn:
        init_schema(conn)
        upsert_validation(conn, 'TEST', '2026Q2', 'unconsolidated', {lane: verdict(check)})
        pending = backfill._pending_lanes(conn, 'TEST', '2026Q2', 'unconsolidated',
                                         (lane,), refresh_existing=True, only_failing=True)
        assert pending == ((lane,) if selected else ())
        assert not backfill._pending_lanes(conn, 'OTHER', '2026Q2', 'unconsolidated',
                                           (lane,), refresh_existing=True, only_failing=True)


@pytest.mark.parametrize(('remaining_failure', 'dry_run'), [(None, False), ('npl_source_cell_missing', True)])
def test_selected_revalidation_runs_with_unchanged_capture_and_preserves_facts(
        tmp_path, monkeypatch, capsys, remaining_failure, dry_run):
    db = tmp_path/'audit.db'
    with sqlite3.connect(db) as conn:
        init_schema(conn)
        conn.execute("INSERT INTO bank_audit_npl_movement "
                     "(bank_ticker,period,kind,group_code,period_type,closing_balance,other_movement,extracted_at) "
                     "VALUES ('TEST','2026Q2','unconsolidated','III','current',123,NULL,'original')")
        before = conn.execute('SELECT * FROM bank_audit_npl_movement').fetchall()
        upsert_validation(conn, 'TEST', '2026Q2', 'unconsolidated',
                          {'npl_movement': verdict('npl_source_cells_missing')})
    monkeypatch.setattr(sys, 'argv', ['backfill', '--db', str(db), '--no-pull',
                                     '--lanes', 'npl_movement', '--only-failing',
                                     *(['--dry-run'] if dry_run else [])])
    monkeypatch.setattr(backfill, 'list_r2_pdfs', lambda: [('TEST', '2026Q2', 'unconsolidated', 'source.pdf')])
    monkeypatch.setattr(backfill.r2_storage, 'download_to', lambda _, dest: dest.write_bytes(b'retained-source'))
    monkeypatch.setattr(backfill, 'capture_and_upsert', lambda *a, **kw: CaptureWriteResult())
    monkeypatch.setattr(backfill, 'revalidate_partition',
                        lambda *a: {'npl_movement': verdict(remaining_failure)})
    pushed, snapshots = [], []
    monkeypatch.setattr(backfill, 'push_partitions', lambda parts, **kw: pushed.append((parts, kw['tables'])))
    monkeypatch.setattr(backfill, 'push_snapshot', lambda path: snapshots.append(path))
    assert backfill.main() == 0
    log = capsys.readouterr().out
    report = json.loads(next(line.split('[CAPTURE_VALIDATION] ', 1)[1]
                             for line in log.splitlines() if '[CAPTURE_VALIDATION] ' in line))
    assert report['native_cell_rows'] == 0
    assert report['validation']['failed'] == int(remaining_failure is not None)
    if remaining_failure:
        assert report['validation']['failures'][0]['check'] == remaining_failure
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM bank_audit_npl_movement').fetchall() == before
    assert pushed == ([] if dry_run else [([('TEST', '2026Q2', 'unconsolidated')], ['bank_audit_validation'])])
    assert snapshots == ([] if dry_run else [db])
