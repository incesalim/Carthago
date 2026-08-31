"""Targeted repair writes use the same denomination as the regular loader."""
import sqlite3
from types import SimpleNamespace

import pytest

pytest.importorskip("fitz")

from reextract_statement import _unit_change_requires_refresh, _upsert  # noqa: E402
from src.audit_reports.extractor import StatementRow  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.units import UnitContext  # noqa: E402
from src.audit_reports.validator import check_pl_bottomline  # noqa: E402


@pytest.mark.parametrize("previous,incoming,blocked", [
    ("bin", "milyon", True), ("milyon", "bin", True),
    ("milyon", "milyon", False), ("bin", "bin", False), (None, "bin", False),
])
def test_single_lane_cannot_hide_a_whole_filing_unit_change(previous, incoming, blocked):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO bank_audit_extractions "
                 "(bank_ticker, period, kind, pdf_path, source_unit) "
                 "VALUES ('TEST','2026Q2','consolidated','test.pdf',?)", (previous,))
    unit = UnitContext(source_unit=incoming, factor=1000 if incoming == "milyon" else 1)
    assert _unit_change_requires_refresh(conn, "TEST", "2026Q2", "consolidated", unit) is blocked
    assert not _unit_change_requires_refresh(conn, "TEST", "2026Q2", "unconsolidated", unit)
    assert conn.execute("SELECT source_unit FROM bank_audit_extractions").fetchone() == (previous,)


@pytest.mark.parametrize("lane,table,statement", [
    ("bs_assets", "bank_audit_balance_sheet", "assets"),
    ("bs_liabilities", "bank_audit_balance_sheet", "liabilities"),
    ("off_balance", "bank_audit_balance_sheet", "off_balance"),
    ("profit_loss", "bank_audit_profit_loss", None),
    ("cash_flow", "bank_audit_cash_flow", None),
])
@pytest.mark.parametrize("source_unit,factor", [("bin", 1), ("milyon", 1000)])
def test_targeted_money_writes_keep_units_signs_null_and_zero(lane, table, statement,
                                                           source_unit, factor):
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    rows = [
        StatementRow(order=7, hierarchy="1.2", name="Signed amount", footnote="3",
                     cur_tl=-32, cur_fc=0, cur_total=-32, cur_amount=-32),
        StatementRow(order=8, hierarchy="1.3", name="Undisclosed", footnote=None,
                     cur_tl=None, cur_fc=0, cur_total=None, cur_amount=None),
        StatementRow(order=9, hierarchy="1.4", name="Disclosed zero", footnote=None,
                     cur_tl=0, cur_fc=0, cur_total=0, cur_amount=0),
    ]
    report = SimpleNamespace(**{lane: rows})
    conn.execute("SAVEPOINT repair")
    assert _upsert(conn, lane, "TEST", "2026Q2", "consolidated", report,
                   unit=UnitContext(source_unit=source_unit, factor=factor)) == 3
    fields = "amount_tl, amount_fc, amount_total" if statement else "amount"
    stored = conn.execute(
        f"SELECT item_order, hierarchy, item_name, footnote, {fields} "
        f"FROM {table} ORDER BY item_order").fetchall()
    amounts = [(-32 * factor, 0, -32 * factor), (None, 0, None), (0, 0, 0)] if statement else [
        (-32 * factor,), (None,), (0,)]
    assert stored == [
        (7, "1.2", "Signed amount", "3", *amounts[0]),
        (8, "1.3", "Undisclosed", None, *amounts[1]),
        (9, "1.4", "Disclosed zero", None, *amounts[2]),
    ]
    if statement:
        assert conn.execute(f"SELECT DISTINCT statement FROM {table}").fetchall() == [(statement,)]
    # A rejected repair must still roll back instead of committing scaled rows.
    conn.execute("ROLLBACK TO repair")
    conn.execute("RELEASE repair")
    assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("net", [32, 748])
def test_million_pl_repair_reconciles_with_existing_canonical_balance_sheet(net):
    """ODEA/BURGAN Q2 repair used to compare 32/748 with 32,000/748,000."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    row = StatementRow(order=1, hierarchy="XXV.", name="NET PROFIT", footnote=None,
                       cur_amount=net)
    _upsert(conn, "profit_loss", "TEST", "2026Q2", "consolidated",
            SimpleNamespace(profit_loss=[row]),
            unit=UnitContext(source_unit="milyon", factor=1000))
    conn.row_factory = sqlite3.Row
    pl = [dict(r) for r in conn.execute("SELECT * FROM bank_audit_profit_loss")]
    existing_bs = [{"hierarchy": "16.6.2", "item_name": "Current profit",
                    "amount_total": net * 1000}]
    result = check_pl_bottomline(pl, existing_bs)
    assert result.passed == 1 and result.failed == 0
