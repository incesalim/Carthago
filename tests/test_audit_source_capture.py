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
            "Opening balance 1 2 3 4 5",
            "Previously unknown reserve row 6 7 8 9 10",
        ]),
        [""],
        "equity_change",
        (1,),
        report,
    )


def test_capture_preserves_and_classifies_unknown_numeric_source_rows():
    capture = _equity_capture()
    assert capture.capture_status == "captured"
    assert len(capture.lines) == 2
    assert len(capture.data_rows) == 2
    assert capture.data_rows[0].mapped_key == "I"
    assert capture.data_rows[1].mapped_key is None
    assert len(capture.content_hash) == len(capture.shape_hash) == 64


def test_npl_capture_uses_the_production_parsers_full_label_taxonomy():
    capture = _capture_lane(
        _FakeDoc([
            "Balance at the Beginning of the Period 1 2 3",
            "Ending Balance of the Current Period 4 5 6",
        ]),
        [""],
        "npl_movement",
        (1,),
        None,
    )
    assert [row.mapped_key for row in capture.data_rows] == [
        "opening_balance",
        "closing_balance",
    ]


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
        ledger_line_count=2,
        ledger_data_row_count=2,
    )
    assert result.failed == 1
    assert result.failures[0]["check"] == "capture_unmapped_rows"


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
