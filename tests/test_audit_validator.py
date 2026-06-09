"""Unit tests for the structural (internal-sum) validator.

Pure-stdlib fixtures so this runs under CI's minimal dependency set — the
shapes mirror real corpus cases: ALBRK clean, the pre-fix corrupted ALBRK
rows (must FAIL), ING paren-negative storage (must PASS), dropped-child and
multi-period EXIM shapes.
"""
import sqlite3

from src.audit_reports import validator as v
from src.audit_reports.schema import init_schema


def _row(h, name, tl, fc, total, scale=1000):
    """Amounts ×1000 by default — corpus magnitudes are TL thousands, and the
    validator tolerances assume real-world scale."""
    return {"hierarchy": h, "item_name": name,
            "amount_tl": tl * scale, "amount_fc": fc * scale,
            "amount_total": total * scale}


def _clean_assets():
    """ALBRK-shaped minimal assets statement: contra child, two romans, total."""
    return [
        _row("I.", "FINANCIAL ASSETS (Net)", 60, 40, 100),
        _row("1.1", "Cash and Cash Equivalents", 36, 24, 60),
        _row("1.1.1", "Cash and Central Bank", 20, 20, 40),
        _row("1.1.2", "Banks", 18, 7, 25),
        _row("1.1.4", "Expected Credit Losses (-)", 2, 3, 5),
        _row("1.2", "Financial Assets at FVTPL", 24, 16, 40),
        _row("II.", "AMORTISED COST (Net)", 120, 80, 200),
        _row("2.1", "Loans", 130, 80, 210),
        _row("2.4", "Expected Credit Losses (-) (6)", 10, 0, 10),
        _row("", "TOTAL ASSETS", 180, 120, 300),
    ]


def test_clean_statement_all_pass():
    res = v.validate_statement(_clean_assets())
    assert res.failed == 0, res.failures
    # V1 on every full row, V2 on I./1.1/II., V3 once
    assert res.passed >= 10


def test_corrupted_ecl_fails_triplet_and_hierarchy():
    rows = _clean_assets()
    # The pre-fix ALBRK corruption: dipnot "(6)" stored as the value.
    rows[8] = _row("2.4", "ExpectedCreditLosses(", 2.4, 0, -6, scale=1)
    res = v.validate_statement(rows)
    checks = {f["check"] for f in res.failures}
    assert "row_triplet" in checks
    assert "hierarchy_sum" in checks  # II. != 2.1 - 2.4


def test_dropped_child_fails_parent_sum():
    rows = [r for r in _clean_assets() if r["item_name"] != "Expected Credit Losses (-) (6)"]
    res = v.validate_statement(rows)
    assert any(f["check"] == "hierarchy_sum" and "AMORTISED" in f["node"]
               for f in res.failures)


def test_paren_negative_storage_passes():
    """ING-style: contra value stored negative — contribution is -|x| either way."""
    rows = [
        _row("I.", "FINANSAL VARLIKLAR", 60, 40, 100),
        _row("1.1", "Nakit Değerler", 60, 40, 100),
        _row("II.", "İTFA EDİLMİŞ MALİYET", 100, 100, 200),
        _row("2.1", "Krediler", 110, 105, 215),
        _row("2.4", "Beklenen zarar karşılıkları (-) (I-5)", -10, -5, -15),
        _row("", "VARLIKLAR TOPLAMI", 160, 140, 300),
    ]
    res = v.validate_statement(rows)
    assert res.failed == 0, res.failures


def test_missing_children_skip_not_fail():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 100),  # no children captured
        _row("", "TOTAL ASSETS", 60, 40, 100),
    ]
    res = v.validate_statement(rows)
    assert res.failed == 0


def test_statement_total_mismatch_fails():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 100),
        _row("II.", "AMORTISED COST", 100, 100, 200),
        _row("", "TOTAL ASSETS", 200, 150, 350),  # romans sum to 300
    ]
    res = v.validate_statement(rows)
    assert any(f["check"] == "statement_total" for f in res.failures)


def test_cross_statement():
    a = [_row("", "TOTAL ASSETS", 60, 40, 100)]
    li_ok = [_row("", "TOTAL LIABILITIES AND EQUITY", 60, 40, 100)]
    li_bad = [_row("", "TOTAL LIABILITIES AND EQUITY", 60, 30, 90)]
    assert v.check_cross_statement(a, li_ok).failed == 0
    assert v.check_cross_statement(a, li_bad).failed == 1


def test_rounding_tolerance():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 101, scale=1),   # ±1 rounding
        _row("1.1", "Cash", 36, 24, 61, scale=1),
        _row("1.2", "FVTPL", 24, 16, 41, scale=1),
    ]
    res = v.validate_statement(rows)
    assert all(f["check"] != "hierarchy_sum" for f in res.failures)


def test_upsert_validation_roundtrip():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    res = v.validate_statement(_clean_assets())
    v.upsert_validation(conn, "X", "2025Q4", "unconsolidated",
                        {"assets": res, "cross": v.ValidationResult()})
    got = conn.execute(
        "SELECT statement, checks_passed, checks_failed FROM bank_audit_validation "
        "WHERE bank_ticker='X' ORDER BY statement").fetchall()
    assert ("assets", res.passed, 0) in got
    # idempotent replace
    v.upsert_validation(conn, "X", "2025Q4", "unconsolidated", {"assets": res})
    n = conn.execute("SELECT COUNT(*) FROM bank_audit_validation").fetchone()[0]
    assert n == 1


def test_structure_check_reads_validation_table():
    import check_audit_quality as q
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    bad = v.ValidationResult()
    bad.add_fail("hierarchy_sum", "II. AMORTISED", 200, 194)
    v.upsert_validation(conn, "Y", "2026Q1", "unconsolidated", {"assets": bad})
    issues = q._structure(conn)
    assert len(issues) == 1 and "Y 2026Q1" in issues[0]
    # absent table degrades gracefully
    assert q._structure(sqlite3.connect(":memory:")) == []
