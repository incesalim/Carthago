"""loader.upsert_report is NON-DESTRUCTIVE by default: a re-extract must never
overwrite a statement whose stored data already passes validation. It may still
fix failing/missing statements, and force=True overrides the guard entirely."""
import sqlite3

import pytest

pytest.importorskip("fitz")  # CI installs minimal deps; extractor/loader need fitz (PyMuPDF)

from src.audit_reports.extractor import BankReport, StatementRow  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
# Pre-2026Q2 (`bin`) fixtures, so the canonical context is the honest one:
# factor 1, applied as a real multiply. The argument is REQUIRED with no
# default — a caller that forgets must fail loudly rather than silently
# store a Milyon filing unscaled.
from src.audit_reports.units import UnitContext  # noqa: E402

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
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())     # empty re-extract, guard ON
    assert _eq_rows(c) == 34                          # left untouched


def test_force_overwrites_passing_statement():
    c = _conn()
    _seed_equity(c, 34, passed=5, failed=0)
    upsert_report(c, B, P, K, _empty(), "x.pdf", force=True, unit=UnitContext.canonical())
    assert _eq_rows(c) == 0                           # force ignores the guard


def test_failing_statement_is_not_protected():
    c = _conn()
    _seed_equity(c, 34, passed=3, failed=2)          # currently FAILING
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())     # guard ON
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
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert _eq_rows(c) == 0


def _seed_balance_sheet(c: sqlite3.Connection, *, cross_failed: int) -> None:
    c.executemany(
        "INSERT INTO bank_audit_balance_sheet "
        "(bank_ticker, period, kind, statement, item_order, item_name, amount_total) "
        "VALUES (?,?,?,?,?,?,?)",
        [(B, P, K, "assets", 1, "asset", 100),
         (B, P, K, "liabilities", 1, "liability", 100)],
    )
    c.executemany(
        "INSERT INTO bank_audit_validation "
        "(bank_ticker, period, kind, statement, checks_passed, checks_failed) "
        "VALUES (?,?,?,?,?,?)",
        [(B, P, K, "assets", 1, 0),
         (B, P, K, "liabilities", 1, 0),
         (B, P, K, "cross", 1, cross_failed)],
    )
    c.commit()


def test_balance_sheet_is_not_protected_when_cross_identity_fails():
    c = _conn()
    _seed_balance_sheet(c, cross_failed=1)
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert c.execute(
        "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
        (B,)).fetchone()[0] == 0


def test_balance_sheet_pair_is_protected_only_when_full_gate_passes():
    c = _conn()
    _seed_balance_sheet(c, cross_failed=0)
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert c.execute(
        "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
        (B,)).fetchone()[0] == 2


# --- the guard cannot protect a partition whose UNIT moved --------------------

def _seed_extraction_unit(c: sqlite3.Connection, unit: str) -> None:
    c.execute(
        "INSERT OR REPLACE INTO bank_audit_extractions "
        "(bank_ticker, period, kind, pdf_path, source_unit, success) "
        "VALUES (?,?,?,?,?,1)", (B, P, K, "x.pdf", unit))
    c.commit()


def test_a_changed_unit_defeats_the_passes_validation_guard():
    """ANADOLU 2026Q2 unconsolidated, 2026-08-13. Stored under a misdetected
    `bin` while the filing prints Milyon, so every amount was 1000x small and
    every identity still passed — a uniform scale change divides both sides.
    After the detector was fixed, the re-extraction rewrote `source_unit` to
    `milyon` and this guard protected all the wrong figures on the strength of
    the validation the error is invisible to. The partition came out MORE
    inconsistent: metadata claiming a scale the figures did not have."""
    c = _conn()
    _seed_balance_sheet(c, cross_failed=0)     # passing — normally protected
    _seed_extraction_unit(c, "bin")
    upsert_report(c, B, P, K, _empty(), "x.pdf",
                  unit=UnitContext(source_unit="milyon", factor=1_000))
    assert c.execute(
        "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
        (B,)).fetchone()[0] == 0, "stale-scale rows must not survive a unit change"


def test_the_same_unit_still_protects_a_passing_statement():
    """The override is narrow: only a MOVED unit defeats the guard. A routine
    re-extract of a partition whose unit is unchanged stays non-destructive."""
    c = _conn()
    _seed_balance_sheet(c, cross_failed=0)
    _seed_extraction_unit(c, "bin")
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert c.execute(
        "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
        (B,)).fetchone()[0] == 2


def test_a_first_extraction_is_not_treated_as_a_unit_change():
    """No prior extractions row means nothing to contradict — the guard applies
    as usual rather than being skipped by a None != 'milyon' comparison."""
    c = _conn()
    _seed_balance_sheet(c, cross_failed=0)     # passing, and no extractions row
    upsert_report(c, B, P, K, _empty(), "x.pdf",
                  unit=UnitContext(source_unit="milyon", factor=1_000))
    assert c.execute(
        "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
        (B,)).fetchone()[0] == 2


def test_roles_follow_retained_pl_even_when_an_unrelated_validator_crashes(monkeypatch):
    """A standalone partition load must not erase the map used by TTM ROE.

    The incoming report is empty, but the protected stored P&L remains. Roles
    must come from that P&L, independently of best-effort validation, and a
    repeated refresh must not create a new D1 write timestamp.
    """
    from scripts import revalidate_audit_db

    def broken_validator(*args, **kwargs):
        raise RuntimeError("unrelated lane failed")

    monkeypatch.setattr(revalidate_audit_db, "revalidate_partition", broken_validator)
    c = _conn()
    c.execute(
        "INSERT INTO bank_audit_profit_loss "
        "(bank_ticker, period, kind, item_order, hierarchy, item_name, amount) "
        "VALUES (?,?,?,?,?,?,?)", (B, P, K, 1, "XXV.", "DÖNEM NET KARI", 42))
    c.execute(
        "INSERT INTO bank_audit_validation "
        "(bank_ticker, period, kind, statement, checks_passed, checks_failed) "
        "VALUES (?,?,?,?,?,?)", (B, P, K, "profit_loss", 1, 0))

    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert c.execute(
        "SELECT p.amount FROM bank_audit_profit_loss p JOIN bank_audit_pl_roles r "
        "ON r.bank_ticker=p.bank_ticker AND r.period=p.period AND r.kind=p.kind "
        "AND r.hierarchy=p.hierarchy WHERE r.role='period_net'").fetchone() == (42,)

    c.execute("UPDATE bank_audit_pl_roles SET derived_at='2026-01-01 00:00:00'")
    upsert_report(c, B, P, K, _empty(), "x.pdf", unit=UnitContext.canonical())
    assert c.execute("SELECT derived_at FROM bank_audit_pl_roles").fetchone() == (
        "2026-01-01 00:00:00",)


def test_roles_follow_a_fresh_pl_and_are_removed_with_its_source():
    c = _conn()
    rep = BankReport(pdf_path="x.pdf", profit_loss=[StatementRow(
        order=1, hierarchy="XXV.", name="DÖNEM NET KARI", footnote=None,
        cur_amount=42)])
    upsert_report(c, B, P, K, rep, "x.pdf", unit=UnitContext.canonical())
    assert c.execute("SELECT hierarchy, role FROM bank_audit_pl_roles").fetchall() == [
        ("XXV.", "period_net")]

    upsert_report(c, B, P, K, _empty(), "x.pdf", force=True,
                  unit=UnitContext.canonical())
    assert c.execute("SELECT COUNT(*) FROM bank_audit_pl_roles").fetchone() == (0,)
