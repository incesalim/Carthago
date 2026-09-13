"""The production loader cannot publish a partial report after a crash."""
import sqlite3

import pytest

from scripts import revalidate_audit_db
from src.audit_reports import capital_adequacy, source_capture, validator
from src.audit_reports.extractor import BankReport, StatementRow
from src.audit_reports.loader import upsert_report
from src.audit_reports.schema import init_schema
from src.audit_reports.units import UnitContext


B, P, K = "TEST", "2025Q1", "consolidated"


def _report(amount):
    return BankReport(pdf_path="incoming.pdf", profit_loss=[StatementRow(
        order=1, hierarchy="XXV.", name="DÖNEM NET KARI", footnote="5.4",
        cur_amount=amount)])


def _snapshot(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()
            for t in tables}


def _seed(conn):
    init_schema(conn)
    upsert_report(conn, B, P, K, _report(42), "original.pdf",
                  unit=UnitContext.canonical())
    # Keep this P&L eligible for replacement, while a manually settled equity
    # statement stays protected by the ordinary production guard.
    conn.execute("UPDATE bank_audit_validation SET checks_failed=1 "
                 "WHERE statement='profit_loss'")
    conn.execute("INSERT INTO bank_audit_equity_change "
                 "(bank_ticker,period,kind,period_type,item_order,item_name) "
                 "VALUES (?,?,?,'current',1,'Settled equity row')", (B, P, K))
    conn.execute("UPDATE bank_audit_validation SET checks_passed=1,checks_failed=0 "
                 "WHERE statement='equity_change'")
    conn.execute("INSERT INTO bank_audit_source_lines "
                 "(bank_ticker,period,kind,statement_type,source_page,line_order,"
                 "line_text,line_hash,shape_hash) "
                 "VALUES (?,?,?,'equity_change',20,1,'Original words','old','old')",
                 (B, P, K))
    conn.execute("INSERT INTO bank_audit_capture_manifest "
                 "(bank_ticker,period,kind,statement_type,capture_scope,content_hash,"
                 "shape_hash,mapping_hash,capture_status) "
                 "VALUES (?,?,?,'equity_change','near_full','old','old','old','captured')",
                 (B, P, K))
    for table, field in [("bank_audit_extractions", "extracted_at"),
                         ("bank_audit_equity_change", "extracted_at"),
                         ("bank_audit_pl_roles", "derived_at"),
                         ("bank_audit_validation", "validated_at"),
                         ("bank_audit_source_lines", "captured_at"),
                         ("bank_audit_capture_manifest", "extracted_at")]:
        conn.execute(f"UPDATE {table} SET {field}='2000-01-01'")
    conn.execute("CREATE TABLE caller_work (value TEXT)")
    conn.commit()


@pytest.mark.parametrize("pending_work", [False, True])
@pytest.mark.parametrize("failure", ["roles", "statement", "source", "validation", "verdict_write", "log"])
def test_failed_load_restores_all_report_rows_even_if_caller_later_commits(
        tmp_path, monkeypatch, pending_work, failure):
    db = tmp_path / "audit.db"
    conn = sqlite3.connect(db)
    _seed(conn)
    if pending_work:
        conn.execute("INSERT INTO caller_work VALUES ('keep this preceding work')")

    def crash(*args, **kwargs):
        raise RuntimeError("injected load failure")

    def write_source(c, *args, **kwargs):
        c.execute("UPDATE bank_audit_source_lines SET line_text='Candidate words'")
        c.execute("UPDATE bank_audit_capture_manifest SET content_hash='candidate'")
        if failure == "source":
            crash()

    monkeypatch.setattr(source_capture, "capture_and_upsert", write_source)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"Source acquisition is outside this transaction regression")
    if failure == "roles":
        monkeypatch.setattr(validator, "upsert_pl_roles", crash)
    elif failure == "statement":
        monkeypatch.setattr(capital_adequacy, "upsert", crash)
    elif failure == "validation":
        monkeypatch.setattr(revalidate_audit_db, "revalidate_partition", crash)
    elif failure == "verdict_write":
        def partial_verdict(c, *args, **kwargs):
            c.execute("DELETE FROM bank_audit_validation")
            crash()
        monkeypatch.setattr(validator, "upsert_validation", partial_verdict)
    elif failure == "log":
        conn.execute("CREATE TEMP TRIGGER reject_log BEFORE INSERT ON bank_audit_extractions "
                     "BEGIN SELECT RAISE(ABORT, 'injected load failure'); END")

    before = _snapshot(conn)
    with pytest.raises((RuntimeError, sqlite3.IntegrityError), match="injected load failure") as caught:
        upsert_report(conn, B, P, K, _report(-900), "candidate.pdf",
                      unit=UnitContext.canonical(), source_pdf_path=pdf)
    assert "Audit load rolled back" in caught.value.__notes__[0]
    assert _snapshot(conn) == before
    assert conn.in_transaction is pending_work
    # Catching the error must not let a later commit leak candidate data.
    conn.commit()
    with sqlite3.connect(db) as reopened:
        assert _snapshot(reopened) == before
    conn.close()


def test_successful_load_keeps_failed_check_results_for_existing_publication_gates(tmp_path):
    conn = sqlite3.connect(tmp_path / "audit.db")
    _seed(conn)
    counts = upsert_report(conn, B, P, K, _report(-900), "candidate.pdf",
                           unit=UnitContext.canonical())
    assert counts["profit_loss"] == 1 and counts["equity_change"] == 1
    assert not conn.in_transaction
    assert conn.execute("SELECT amount,footnote FROM bank_audit_profit_loss").fetchone() == (-900, "5.4")
    assert conn.execute("SELECT item_name,extracted_at FROM bank_audit_equity_change").fetchone() == (
        "Settled equity row", "2000-01-01")
    # A failed financial check is a recorded finding, not a validator crash.
    assert conn.execute("SELECT COUNT(*) FROM bank_audit_validation WHERE checks_failed>0").fetchone()[0] > 0
    assert conn.execute("SELECT pdf_path FROM bank_audit_extractions").fetchone() == ("candidate.pdf",)
    conn.close()
