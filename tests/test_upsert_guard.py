"""loader.upsert_report is NON-DESTRUCTIVE by default: a re-extract must never
overwrite a statement whose stored data already passes validation. It may still
fix failing/missing statements, and force=True overrides the guard entirely."""
import sqlite3

import pytest

pytest.importorskip("pdfplumber")  # CI installs minimal deps; extractor/loader need pdfplumber

from src.audit_reports.extractor import BankReport  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

B, P, K = "TEST", "2025Q1", "consolidated"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _seed_equity(c: sqlite3.Connection, n_rows: int, *, passed: int, failed: int) -> None:
    """Seed an equity_change partition plus its recorded validation verdict."""
    c.executemany(
        "INSERT INTO bank_audit_equity_change "
        "(bank_ticker, period, kind, period_type, item_order, item_name) "
        "VALUES (?,?,?,?,?,?)",
        [(B, P, K, "current", i, f"row {i}") for i in range(n_rows)])
    c.execute(
        "INSERT INTO bank_audit_validation "
        "(bank_ticker, period, kind, statement, checks_passed, checks_failed) "
        "VALUES (?,?,?,?,?,?)", (B, P, K, "equity_change", passed, failed))
    c.commit()


def _eq_rows(c: sqlite3.Connection) -> int:
    return c.execute(
        "SELECT COUNT(*) FROM bank_audit_equity_change "
        "WHERE bank_ticker=? AND period=? AND kind=?", (B, P, K)).fetchone()[0]


def _empty() -> BankReport:
    """A degraded re-extraction that found nothing (the worst-case overwrite)."""
    return BankReport(pdf_path="x.pdf")


def test_passing_statement_is_protected():
    c = _conn()
    _seed_equity(c, 34, passed=5, failed=0)          # validated-correct
    upsert_report(c, B, P, K, _empty(), "x.pdf")     # empty re-extract, guard ON
    assert _eq_rows(c) == 34                          # left untouched


def test_force_overwrites_passing_statement():
    c = _conn()
    _seed_equity(c, 34, passed=5, failed=0)
    upsert_report(c, B, P, K, _empty(), "x.pdf", force=True)
    assert _eq_rows(c) == 0                           # force ignores the guard


def test_failing_statement_is_not_protected():
    c = _conn()
    _seed_equity(c, 34, passed=3, failed=2)          # currently FAILING
    upsert_report(c, B, P, K, _empty(), "x.pdf")     # guard ON
    assert _eq_rows(c) == 0                           # re-extract still replaces it


def test_unvalidated_statement_is_not_protected():
    c = _conn()
    # rows present but NO validation row → not proven correct → re-extractable
    c.executemany(
        "INSERT INTO bank_audit_equity_change "
        "(bank_ticker, period, kind, period_type, item_order, item_name) "
        "VALUES (?,?,?,?,?,?)",
        [(B, P, K, "current", i, f"row {i}") for i in range(10)])
    c.commit()
    upsert_report(c, B, P, K, _empty(), "x.pdf")
    assert _eq_rows(c) == 0
