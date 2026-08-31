"""Image-only P&L transcription is bound to reviewed source bytes and page."""
import hashlib
import json
from pathlib import Path

import pytest

from src.audit_reports import extractor as ex
from src.audit_reports.validator import check_profit_loss


NAME = "FIBA_2023Q3_consolidated.pdf"


@pytest.fixture
def source():
    path = Path(__file__).resolve().parents[1] / "data" / "audit_pl_overrides.json"
    return json.loads(path.read_text(encoding="utf-8"))["reports"][NAME]


@pytest.mark.parametrize("col", [0, 1, 2, 3])
def test_every_transcribed_source_column_reconciles(source, col):
    assert source["sha256"] == "56f822de7ad410c01f0f7343efdcfa8337fd4f7702f460d3b1b986ae0c062689"
    assert source["source_page"] == 13 and source["source_unit"] == "bin"
    assert len(source["rows"]) == 64
    rows = [{"hierarchy": r["hierarchy"], "item_name": r["item_name"],
             "amount": r["values"][col]} for r in source["rows"]]
    # Independently read from BS p11; the prior BS date is not a comparable
    # prior-YTD income period, so do not cross-check the other three columns.
    bs = [{"hierarchy": "16.6.2", "amount_total": 3339500}] if col == 0 else None
    result = check_profit_loss(rows, bs)
    assert result.failed == 0 and result.skipped == 0
    assert result.passed == (12 if col == 0 else 11)
    if col == 0:
        by_hierarchy = {r["hierarchy"]: r["amount"] for r in rows}
        assert by_hierarchy["XXV."] == 3340008
        assert by_hierarchy["25.1"] == 3339500
        assert by_hierarchy["25.2"] == 508


def test_override_requires_filename_hash_and_page_and_maps_named_ytd_columns(tmp_path, monkeypatch,
                                                                          source):
    path = tmp_path / NAME
    path.write_bytes(b"reviewed test PDF")
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(ex, "_pl_source_overrides", lambda: {NAME: source})
    monkeypatch.setattr(ex, "_locate_pages", lambda p: {})
    seen_pages = []

    def page_text(p, index):
        seen_pages.append(index)
        return "KONSOLİDE KAR VEYA ZARAR TABLOSU" if index == 12 else "CASH FLOW"

    monkeypatch.setattr(ex, "_fitz_page_text", page_text)
    report = ex.extract(path, only={"profit_loss"})
    assert len(report.profit_loss) == 64 and seen_pages == [12]
    for row, fact in zip(report.profit_loss, source["rows"], strict=True):
        assert (row.cur_amount, row.pri_amount) == tuple(fact["values"][:2])
        assert (row.hierarchy, row.name, row.footnote) == (
            fact["hierarchy"], fact["item_name"], fact["footnote"])

    source["source_page"] = 12
    assert not ex.extract(path, only={"profit_loss"}).profit_loss
    source["source_page"] = 13
    path.write_bytes(b"different filing under the same filename")
    assert not ex.extract(path, only={"profit_loss"}).profit_loss
    other = tmp_path / "FIBA_2023Q3_unconsolidated.pdf"
    other.write_bytes(b"reviewed test PDF")
    assert ex._verified_pl_override(str(other)) is None


def test_inconsistent_transcription_fails_closed(tmp_path, monkeypatch, source):
    path = tmp_path / NAME
    path.write_bytes(b"reviewed test PDF")
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    source["rows"][0]["values"][3] += 1000  # a non-current column must be checked too
    monkeypatch.setattr(ex, "_pl_source_overrides", lambda: {NAME: source})
    monkeypatch.setattr(ex, "_fitz_page_text", lambda *args: "KONSOLİDE KAR VEYA ZARAR TABLOSU")
    assert ex._verified_pl_override(str(path)) is None
