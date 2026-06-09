"""Regression tests for the §4 capital/liquidity data-quality cross-checks.

These exercise scripts/check_audit_quality.py against a synthetic in-memory DB —
no PDF parsing, so they run under CI's minimal dependency set (sqlite + stdlib).
"""
import sqlite3

import check_audit_quality as q  # scripts/ is on pythonpath (see pyproject.toml)
from src.audit_reports.schema import init_schema


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _ins_capital(c, **kw):
    cols = ["bank_ticker", "period", "kind", "period_type", "cet1_capital",
            "tier1_capital", "total_capital", "total_rwa", "capital_adequacy_ratio"]
    vals = [kw.get(k) for k in cols]
    c.execute(f"INSERT INTO bank_audit_capital ({','.join(cols)}) "
              f"VALUES ({','.join('?' for _ in cols)})", vals)
    c.commit()


def _ins_liquidity(c, **kw):
    cols = ["bank_ticker", "period", "kind", "period_type",
            "leverage_ratio", "lcr_total", "nsfr"]
    vals = [kw.get(k) for k in cols]
    c.execute(f"INSERT INTO bank_audit_liquidity ({','.join(cols)}) "
              f"VALUES ({','.join('?' for _ in cols)})", vals)
    c.commit()


def test_capital_clean_passes():
    c = _conn()
    # GARAN-like: CAR = 520/2500*100 = 20.8, tier ordering holds.
    _ins_capital(c, bank_ticker="X", period="2026Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=400, tier1_capital=420,
                 total_capital=520, total_rwa=2500, capital_adequacy_ratio=20.8)
    assert q._capital_consistency(c) == []


def test_capital_flags_tier_order_and_car_mismatch():
    c = _conn()
    _ins_capital(c, bank_ticker="Y", period="2026Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=500, tier1_capital=400,
                 total_capital=520, total_rwa=2500, capital_adequacy_ratio=30.0)
    issues = q._capital_consistency(c)
    assert any("CET1" in i for i in issues)   # 500 > 400
    assert any("CAR" in i for i in issues)    # 30.0 != 20.8


def test_liquidity_clean_passes():
    c = _conn()
    _ins_liquidity(c, bank_ticker="W", period="2026Q1", kind="unconsolidated",
                   period_type="current", leverage_ratio=5.5, lcr_total=140.0, nsfr=120.0)
    assert q._liquidity_bands(c) == []


def test_liquidity_flags_low_lcr_and_bad_leverage():
    c = _conn()
    _ins_liquidity(c, bank_ticker="Z", period="2026Q1", kind="unconsolidated",
                   period_type="current", leverage_ratio=99.0, lcr_total=30.0, nsfr=120.0)
    issues = q._liquidity_bands(c)
    assert any("LCR" in i for i in issues)        # 30 < 50
    assert any("leverage" in i for i in issues)   # 99 out of band


def test_checks_skip_when_tables_absent():
    # A freshly-seeded DB without the §4 tables must not raise.
    c = sqlite3.connect(":memory:")
    assert q._capital_consistency(c) == []
    assert q._liquidity_bands(c) == []


def _ins_bs(c, bank, period, rows, kind="unconsolidated", statement="assets"):
    """rows = list of (item_name, amount_total); item_order auto-assigned."""
    start = c.execute(
        "SELECT COALESCE(MAX(item_order),0) FROM bank_audit_balance_sheet "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
        (bank, period, kind, statement)).fetchone()[0]
    for i, (name, amt) in enumerate(rows, start + 1):
        c.execute(
            "INSERT INTO bank_audit_balance_sheet (bank_ticker, period, kind, "
            "statement, item_order, item_name, amount_total) VALUES (?,?,?,?,?,?,?)",
            (bank, period, kind, statement, i, name, amt))
    c.commit()


def _big_bank_quarter(c, bank, period, ecl_rows):
    """A large-bank quarter: enough asset rows + a grand total + the ECL rows."""
    filler = [(f"Line {i}", 1_000_000) for i in range(20)]
    _ins_bs(c, bank, period, filler + [("TOTAL ASSETS", 500_000_000)] + ecl_rows)


def test_ecl_clean_passes():
    c = _conn()
    _big_bank_quarter(c, "A", "2025Q4", [("Expected Credit Losses (-) (6)", 6_057_750)])
    _big_bank_quarter(c, "A", "2026Q1", [("Expected Credit Losses (-) (6)", 6_540_511)])
    assert q._ecl_sanity(c) == []


def test_ecl_flags_truncated_negative_and_tiny():
    c = _conn()
    _big_bank_quarter(c, "B", "2025Q4", [("ExpectedCreditLosses(", -6)])
    _big_bank_quarter(c, "C", "2025Q4", [("Expected Credit Losses (", 63)])
    issues = q._ecl_sanity(c)
    assert any("B 2025Q4" in i and "truncated" in i for i in issues)
    assert any("C 2025Q4" in i and "truncated" in i for i in issues)
    # tiny |amounts| on intact labels also flag (covers the -6 class)
    _big_bank_quarter(c, "D", "2025Q4", [("Expected Credit Losses (-)", -6)])
    _big_bank_quarter(c, "E", "2025Q4", [("Beklenen Zarar Karşılıkları (-)", 41)])
    issues = q._ecl_sanity(c)
    assert any("D 2025Q4" in i and "tiny" in i for i in issues)
    assert any("E 2025Q4" in i and "tiny" in i for i in issues)


def test_ecl_paren_negative_value_not_flagged():
    c = _conn()
    # ING/KLNMA-style: the bank prints the value itself in parens → a large
    # negative ECL is the faithful reading, not a parse error.
    _big_bank_quarter(c, "N", "2025Q4", [("Beklenen zarar karşılıkları (-) (I-5)", -2_034_323)])
    assert q._ecl_sanity(c) == []


def test_ecl_small_bank_tiny_not_flagged():
    c = _conn()
    # A small bank (total assets below the gate) may legitimately carry tiny ECL.
    _ins_bs(c, "S", "2025Q4",
            [(f"Line {i}", 1_000) for i in range(20)]
            + [("TOTAL ASSETS", 80_000), ("Expected Credit Losses (-)", 12)])
    assert q._ecl_sanity(c) == []


def test_ecl_flags_vanished_rows():
    c = _conn()
    _big_bank_quarter(c, "F", "2025Q4", [("Expected Credit Losses (-) (6)", 6_000_000)])
    _big_bank_quarter(c, "F", "2026Q1", [])  # rows dropped by the parser
    issues = q._ecl_sanity(c)
    assert any("F 2026Q1" in i and "missing" in i for i in issues)
