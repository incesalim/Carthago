"""Stocks independently reconciled to the exact source PDFs on 2026-08-31.

The two main traps were reading historical opinions / reversal flows as current
balances, and treating an unreadable disclosure as zero. These expectations come
from the current auditor qualification or liability note, not the parser output.
"""
import sqlite3

import pytest

from src.audit_reports.free_provision import _override_for, upsert_free_provision
from src.audit_reports.schema import init_schema
from src.audit_reports.units import UnitContext


# Canonical thousand-TL values, independently read from the source. Both filing
# kinds were checked; Burgan's consolidated reserve is materially different.
VERIFIED = [
    ("BURGAN", "2022Q4", "consolidated", 694_311, 138_622),
    ("BURGAN", "2023Q2", "consolidated", 1_585_959, 694_311),
    ("BURGAN", "2023Q2", "unconsolidated", 1_368_015, 654_441),
    ("BURGAN", "2023Q3", "consolidated", 1_816_973, 694_311),
    ("BURGAN", "2023Q3", "unconsolidated", 1_391_411, 654_441),
    ("BURGAN", "2023Q4", "consolidated", 1_872_098, 694_311),
    ("BURGAN", "2023Q4", "unconsolidated", 1_308_970, 654_441),
    ("BURGAN", "2024Q1", "consolidated", 1_791_057, 1_872_098),
    ("BURGAN", "2024Q1", "unconsolidated", 1_220_789, 1_308_970),
    ("BURGAN", "2026Q1", "consolidated", 394_183, 165_000),
    ("BURGAN", "2026Q1", "unconsolidated", 234_183, 20_000),
    ("AKTIF", "2026Q2", "unconsolidated", 490_000, 490_000),
    ("ZIRAATD", "2026Q2", "unconsolidated", 790_000, 835_000),
    ("ODEA", "2023Q3", "unconsolidated", 250_000, 650_000),
] + [
    (bank, period, kind, stock, prior)
    for kind in ("consolidated", "unconsolidated")
    for bank, period, stock, prior in [
        ("EMLAK", "2026Q2", 13_000_000, 9_850_000),
        ("FIBA", "2026Q1", 1_210_000, 1_092_000),
        ("FIBA", "2026Q2", 1_210_000, 1_092_000),
        ("QNBFB", "2026Q2", 3_500_000, 4_000_000),
        ("TSKB", "2026Q2", 400_000, 1_100_000),
        ("TFKB", "2024Q4", 0, 1_155_000),
        ("TEB", "2024Q1", 850_000, 2_050_000),
        ("TEB", "2024Q2", 850_000, 2_050_000),
        ("TEB", "2024Q3", 850_000, 2_050_000),
        ("TEB", "2024Q4", 1_500_000, 2_050_000),
        ("TEB", "2025Q1", 1_500_000, 1_500_000),
    ]
]


@pytest.mark.parametrize("bank,period,kind,stock,prior", VERIFIED)
def test_verified_stock_survives_the_filing_unit_conversion(bank, period, kind, stock, prior):
    result = _override_for(bank, period, kind)
    assert result is not None and result.disclosed
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    filing = UnitContext("milyon", 1_000) if period >= "2026Q2" else UnitContext("bin", 1)
    upsert_free_provision(conn, bank, period, kind, result, unit=filing)
    assert conn.execute(
        "SELECT free_provision,free_provision_prior FROM bank_audit_free_provision"
    ).fetchone() == (stock, prior)
    conn.close()


def test_corrected_teb_prior_chain_uses_year_end_not_the_old_auditor_paragraph():
    for kind in ("consolidated", "unconsolidated"):
        q4 = _override_for("TEB", "2024Q4", kind)
        q1 = _override_for("TEB", "2025Q1", kind)
        assert q4.free_provision == q1.free_provision_prior == 1_500_000
        assert q1.free_provision == 1_500_000  # no current-quarter reversal


@pytest.mark.parametrize("stock", [None, 0])
def test_manual_unknown_and_explicit_zero_remain_distinct(monkeypatch, stock):
    from src.audit_reports import free_provision

    monkeypatch.setattr(free_provision, "_overrides", lambda: {
        "SAMPLE": {"2026Q2": {"unconsolidated": {
            "unit": "milyon", "free_provision": stock, "source": "test disclosure",
        }}},
    })
    result = _override_for("SAMPLE", "2026Q2", "unconsolidated")
    assert result.disclosed
    assert result.free_provision is stock
