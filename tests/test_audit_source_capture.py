"""Source completeness is lossless, idempotent and validator-enforced."""
import sqlite3
from types import SimpleNamespace

from src.audit_reports.schema import init_schema
from src.audit_reports.source_capture import (
    _capture_lane,
    load_manifest,
    upsert_lane_capture,
)
from src.audit_reports.validator import check_source_capture


class _FakePage:
    def __init__(self, lines: list[str]):
        self.words = []
        for line_no, line in enumerate(lines):
            y = float(line_no * 10)
            x = 0.0
            for token in line.split():
                self.words.append((x, y, x + len(token), y + 5, token, 0, 0, 0))
                x += len(token) + 2

    def get_text(self, mode: str):
        if mode == "words":
            return self.words
        return ""


class _FakeDoc:
    def __init__(self, lines: list[str]):
        self.page = _FakePage(lines)

    def __getitem__(self, index: int):
        assert index == 0
        return self.page


def _equity_capture():
    report = SimpleNamespace(equity_change=SimpleNamespace(rows=[
        SimpleNamespace(name="Opening balance", hierarchy="I", order=1),
    ]))
    return _capture_lane(
        _FakeDoc([
            "Paid-in capital Share premium Other capital reserves",
            "Opening balance 1 2 3 4 5 6 7 8 9 10",
            "Previously unknown reserve row 6 7 8 9 10 11 12 13 14 15",
        ]),
        [""],
        "equity_change",
        (1,),
        report,
    )


def test_capture_preserves_and_classifies_unknown_numeric_source_rows():
    capture = _equity_capture()
    assert capture.capture_status == "captured"
    assert len(capture.lines) == 3
    assert len(capture.data_rows) == 2
    assert capture.data_rows[0].mapped_key == "I"
    assert capture.data_rows[1].mapped_key is None
    assert len(capture.content_hash) == len(capture.shape_hash) == 64


def test_npl_capture_uses_the_production_parsers_full_label_taxonomy():
    capture = _capture_lane(
        _FakeDoc([
            "Group III Group IV Group V",
            "Balance at the Beginning of the Period 1 2 3",
            "Additions in the current period 1 1 1",
            "Ending Balance of the Current Period 4 5 6",
            "Net balance at balance sheet 4 5 6",
        ]),
        [""],
        "npl_movement",
        (1,),
        None,
    )
    assert [row.mapped_key for row in capture.data_rows] == [
        "opening_balance",
        "additions",
        "closing_balance",
        "net_balance",
    ]


def test_credit_quality_date_close_has_source_traceability():
    """ALNTF's closing date is evidence even without a verbal balance label."""
    capture = _capture_lane(
        _FakeDoc([
            "III. Grup IV. Grup V. Grup",
            "31 Aralık 2025 249 27 397",
            "Dönem İçinde İntikal (+) 28 51 20",
            "30 Haziran 2026 40 290 337",
            "Karşılık (-) 32 196 166",
            "Bilançodaki Net Bakiyesi 8 94 171",
        ]),
        [""], "credit_quality", (1,), None,
    )
    mapped = [row for row in capture.data_rows if row.mapped_key]
    assert [(row.line_text, row.mapped_key) for row in mapped] == [
        ("30 Haziran 2026 40 290 337", "ending_balance"),
    ]
    sqlite_conn = sqlite3.connect(":memory:")
    init_schema(sqlite_conn)
    upsert_lane_capture(
        sqlite_conn, "ALNTF", "2026Q2", "unconsolidated", capture,
        normalized_count=1,
    )
    manifest = load_manifest(
        sqlite_conn, "ALNTF", "2026Q2", "unconsolidated", "credit_quality")
    assert check_source_capture(manifest, actual_row_count=1).failed == 0


def test_credit_quality_date_mapping_requires_complete_npl_table_context():
    cases = [
        # A date in another table is not a traceable NPL closing balance.
        ["30 Haziran 2026 40 290 337", "Karşılık (-) 32 196 166"],
        # Neither a page date nor an incomplete balance supplies three groups.
        ["III. Grup IV. Grup V. Grup", "30 Haziran 2026 40 290",
         "Karşılık (-) 32 196 166"],
        # A date-labelled opening balance is not adjacent to the provision.
        ["III. Grup IV. Grup V. Grup", "31 Aralık 2025 249 27 397",
         "Dönem İçinde İntikal (+) 28 51 20", "Karşılık (-) 32 196 166"],
        # The foreign-currency subset cannot attest to the full NPL balance.
        ["(iii) Yabancı para olarak kullandırılan krediler",
         "III. Grup IV. Grup V. Grup", "30 Haziran 2026 40 290 337",
         "Karşılık (-) 32 196 166"],
    ]
    for lines in cases:
        capture = _capture_lane(
            _FakeDoc(lines), [""], "credit_quality", (1,), None)
        assert all(row.mapped_key is None for row in capture.data_rows)


def test_capture_upsert_is_content_idempotent():
    sqlite_conn = sqlite3.connect(":memory:")
    init_schema(sqlite_conn)
    capture = _equity_capture()
    assert upsert_lane_capture(
        sqlite_conn, "AKBNK", "2026Q2", "consolidated", capture,
        normalized_count=2,
    ) == (True, True)
    sqlite_conn.execute(
        "UPDATE bank_audit_capture_manifest SET extracted_at='2000-01-01'"
    )
    sqlite_conn.execute(
        "UPDATE bank_audit_source_lines SET captured_at='2000-01-01'"
    )

    assert upsert_lane_capture(
        sqlite_conn, "AKBNK", "2026Q2", "consolidated", capture,
        normalized_count=2,
    ) == (False, False)
    assert sqlite_conn.execute(
        "SELECT extracted_at FROM bank_audit_capture_manifest"
    ).fetchone()[0] == "2000-01-01"
    assert sqlite_conn.execute(
        "SELECT DISTINCT captured_at FROM bank_audit_source_lines"
    ).fetchall() == [("2000-01-01",)]


def test_near_full_unknown_row_fails_the_existing_lane_gate():
    sqlite_conn = sqlite3.connect(":memory:")
    init_schema(sqlite_conn)
    capture = _equity_capture()
    upsert_lane_capture(
        sqlite_conn, "AKBNK", "2026Q2", "consolidated", capture,
        normalized_count=2,
    )
    manifest = load_manifest(
        sqlite_conn, "AKBNK", "2026Q2", "consolidated", "equity_change")
    result = check_source_capture(
        manifest,
        actual_row_count=2,
        ledger_line_count=3,
        ledger_data_row_count=2,
    )
    assert result.failed == 1
    assert result.failures[0]["check"] == "capture_unmapped_rows"


def test_capture_does_not_confuse_numeric_prose_with_sector_rows():
    capture = _capture_lane(_FakeDoc([
        "30 Haziran 2026 Tarihli Finansal Rapor 14",
        "- 90 günden az, 30 günden fazla gecikme olması",
        "New undisclosed sector 1 2 3",
    ]), [""], "loans_by_sector", (1,), None)
    assert len(capture.lines) == 3  # evidence remains lossless
    assert [r.line_text for r in capture.data_rows] == ["New undisclosed sector 1 2 3"]
    assert capture.data_rows[0].mapped_key is None


def test_npl_capture_bounds_movements_but_keeps_unknown_movement_rows():
    capture = _capture_lane(_FakeDoc([
        "Cash flows 1 2 3",
        "Group III Group IV Group V",
        "Opening balance 10 20 30",
        "Additions in the current period 1 2 3",
        "Previously unknown flow 4 5 6",
        "Collections in the current period 1 1 1",
        "Closing balance 14 26 38",
        "Net balance at balance sheet 10 20 30",
        "Official Gazette dated November 27, 2019 numbered 30961",
        "Group III Group IV Group V",
        "Loans to individuals and corporates (gross) 10 20 30",
        "Provisions 1 2 3",
        "Loans to individuals and corporates (net) 9 18 27",
    ]), [""], "npl_movement", (1,), None)
    assert len(capture.lines) == 13
    assert [r.mapped_key for r in capture.data_rows] == [
        "opening_balance", "additions", None, "collections",
        "closing_balance", "net_balance",
    ]


def test_npl_unknown_taxonomy_is_still_a_completeness_failure():
    capture = _capture_lane(_FakeDoc([
        "Movements of total non-performing loans",
        "Group III Group IV Group V",
        "New initial-stock label 10 20 30",
        "New movement label 1 2 3",
        "New final-stock label 11 22 33",
    ]), [""], "npl_movement", (1,), None)
    assert len(capture.data_rows) == 3
    assert all(row.mapped_key is None for row in capture.data_rows)


def test_npl_sold_breakdown_requires_known_categories_and_reconciled_columns():
    def capture(retail: str):
        return _capture_lane(_FakeDoc([
            "Group III Group IV Group V",
            "Opening balance 200 700 300",
            "Satılan (-) 106 591 286",
            "Kurumsal ve Ticari Krediler -- 331 177",
            retail,
            "Kredi Kartları 99 -- --",
            "Diğer -- -- --",
            "Closing balance 94 109 14",
            "Net balance at balance sheet 94 109 14",
        ]), [""], "npl_movement", (1,), None)

    good = capture("Bireysel Krediler 7 260 109")
    assert all(row.mapped_key for row in good.data_rows)
    bad = capture("Bireysel Krediler 70 260 109")
    assert len([row for row in bad.data_rows if row.mapped_key is None]) == 3
    unknown = capture("Unexpected new category 7 260 109")
    assert len([row for row in unknown.data_rows if row.mapped_key is None]) == 3


def test_npl_category_traceability_includes_sparse_reconciled_balance_detail():
    # ISCTR 2026Q2 consolidated p.85 omits blank zero cells, including Other's
    # first two columns. Only its position in the column sum makes the trace safe.
    capture = _capture_lane(_FakeDoc([
        "Group III Group IV Group V",
        "Önceki Dönem Sonu Bakiyesi 29.807 23.587 32.263",
        "Kurumsal ve Ticari Krediler 17.765 8.696 22.756",
        "Bireysel Krediler 4.227 5.326 4.701",
        "Kredi Kartları 7.815 9.565 4.655",
        "Diğer 151",
        "Additions 1 2 3",
        "Net balance at balance sheet 29.808 23.589 32.266",
    ]), [""], "npl_movement", (1,), None)
    assert all(row.mapped_key for row in capture.data_rows)
    assert [row.mapped_key for row in capture.data_rows[1:4]] == ["opening_balance"] * 3
    assert capture.lines[5].line_text == "Diğer 151"  # original evidence preserved


def test_npl_category_traceability_rejects_ambiguous_blank_columns():
    from src.audit_reports.source_capture import _npl_breakdown_ties

    assert not _npl_breakdown_ties("Opening balance 10 10 10", [
        "Corporate and commercial loans 5 5 5", "Retail loans 5", "Other 5 5",
    ])
    assert not _npl_breakdown_ties("Opening balance 100 200 300", [
        "Corporate and commercial loans 100 200 299", "Other 1",
    ])  # rounding tolerance alone cannot choose Other's column


def test_npl_wrapped_transfer_keeps_original_cells_and_maps_continuation():
    capture = _capture_lane(_FakeDoc([
        "Group III Group IV Group V", "Opening balance 100 200 300",
        "Transfers from other categories of loans under non-performing",
        "(+) - 21.332 20.291",
        "Transfers to Other Categories of Non-Performing",
        "Loans (-) 21.332 20.291 -",
        "Net balance on balance sheet 100 200 300",
    ]), [""], "npl_movement", (1,), None)
    assert [row.mapped_key for row in capture.data_rows] == [
        "opening_balance", "transfers_in", "transfers_out", "net_balance",
    ]
    assert capture.data_rows[1].line_text == "(+) - 21.332 20.291"


def test_npl_stock_header_does_not_capture_neighboring_ecl_movements():
    capture = _capture_lane(_FakeDoc([
        "Group III Group IV Group V",
        "Current Period Net 1 2 3", "Previous Period Net 2 3 4",
        "TFRS 9'a göre karşılık değişimleri:",
        "Cari Dönem 1. Aşama 2. Aşama 3. Aşama Toplam",
        "Önceki Dönem Sonu Bakiyesi 1.342 1.466 2.390 5.198",
        "Dönem İçi İlave 314 220 953 1.487",
        "Satılan - - - -",
        "Aktiften Silinen - - - -",
        "Dönem Sonu Bakiyesi 1.656 1.686 3.343 6.685",
    ]), [""], "npl_movement", (1,), None)
    assert not capture.data_rows
    assert len(capture.lines) == 10


def test_credit_quality_closing_word_orders_and_ecl_have_traceability():
    capture = _capture_lane(_FakeDoc([
        "Prior Period Ending Balance 1 2 3",
        "Current Period Ending Balance 4 5 6",
        "Balance at the end of period 7 8 9",
        "12 aylık beklenen zarar karşılığı 12 - 2 -",
    ]), [""], "credit_quality", (1,), None)
    assert [row.mapped_key for row in capture.data_rows] == [
        None, "ending_balance", "ending_balance", "loans_ecl_brsa.stage1",
    ]


def test_equity_capture_ignores_header_ordinals_and_unrelated_pages():
    capture = _capture_lane(_FakeDoc([
        "Changes in shareholders equity appear on page 17",
        "Telephone 00 90 216 666 01 01",
        "Cash and cash equivalents 1 2 3 4 5 6",
        "Financial assets 7 8 9 10 11 12",
    ]), [""], "equity_change", (1,), None)
    assert not capture.data_rows
    assert len(capture.lines) == 4


def test_equity_wrapped_label_is_traced_to_the_stored_row():
    report = SimpleNamespace(equity_change=SimpleNamespace(rows=[
        SimpleNamespace(name="Adjusted Balances at Beginning Of Period (I+II)", hierarchy="III.", order=3),
        SimpleNamespace(name="Closing balance", hierarchy="17", order=17),
    ]))
    capture = _capture_lane(_FakeDoc([
        "Paid-in Capital Premium Profits Reserves 1 2 3 4 5 6 Reserves Profit/Loss Equity",
        "III. Adjusted Balances at Beginning",
        "Of Period (I+II) 1 2 3 4 5 6 7 8 9 10",
        "Closing balance 1 2 3 4 5 6 7 8 9 10",
    ]), [""], "equity_change", (1,), report)
    assert [r.mapped_key for r in capture.data_rows] == ["III.", "17"]


def test_capture_rotated_equity_page_uses_visual_rows():
    import fitz
    from src.audit_reports.source_capture import _word_lines

    doc = fitz.open()
    page = doc.new_page(width=300, height=500)
    page.insert_text((40, 450), "Opening balance 1 2 3 4 5", rotate=90)
    page.insert_text((60, 450), "Closing balance 6 7 8 9 10", rotate=90)
    page.set_rotation(90)
    assert _word_lines(page) == [
        "Opening balance 1 2 3 4 5", "Closing balance 6 7 8 9 10",
    ]
    doc.close()


def test_selected_summary_retains_unmapped_detail_without_false_failure():
    manifest = {
        "capture_status": "captured",
        "capture_scope": "selected_summary",
        "source_page_count": 2,
        "source_line_count": 40,
        "source_numeric_line_count": 20,
        "source_data_row_count": 12,
        "mapped_data_row_count": 4,
        "unmapped_data_row_count": 8,
        "normalized_row_count": 2,
        "content_hash": "a" * 64,
        "shape_hash": "b" * 64,
        "mapping_hash": "c" * 64,
    }
    result = check_source_capture(manifest, actual_row_count=2)
    assert result.failed == 0
    assert result.passed > 0


def test_detected_source_rows_with_no_normalized_rows_fail():
    manifest = {
        "capture_status": "captured",
        "capture_scope": "selected_summary",
        "source_page_count": 1,
        "source_line_count": 10,
        "source_numeric_line_count": 4,
        "source_data_row_count": 2,
        "mapped_data_row_count": 0,
        "unmapped_data_row_count": 2,
        "normalized_row_count": 0,
        "content_hash": "a" * 64,
        "shape_hash": "b" * 64,
        "mapping_hash": "c" * 64,
    }
    result = check_source_capture(manifest, actual_row_count=0)
    assert any(failure["check"] == "capture_rows_missed"
               for failure in result.failures)
