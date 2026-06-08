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
