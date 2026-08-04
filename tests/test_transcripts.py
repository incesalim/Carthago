"""Tests for the earnings-call transcript lane (src/transcripts).

Network is stubbed throughout — the fixtures under tests/fixtures/ are trimmed
copies of real AlphaSpread pages, so these run under the CI job's minimal
dependency set with no live source.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from src.transcripts import alphaspread
from src.transcripts.loader import existing_periods, upsert_calls
from src.transcripts.schema import DDL, init_schema

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "web" / "migrations" / "0036_bank_call_transcripts.sql"


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


@pytest.fixture
def call_page() -> str:
    return (FIXTURES / "alphaspread_call.html").read_text(encoding="utf-8")


@pytest.fixture
def index_page() -> str:
    return (FIXTURES / "alphaspread_index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def test_discover_quarters_reads_the_archive(monkeypatch, index_page):
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(index_page))
    assert alphaspread.discover_quarters("test.e") == [
        "2018Q1", "2025Q4", "2026Q1", "2026Q2",
    ]


def test_discover_quarters_drops_pre_min_period(monkeypatch, index_page):
    """q4-2017 is in the archive; MIN_PERIOD keeps it out."""
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(index_page))
    assert "2017Q4" not in alphaspread.discover_quarters("test.e")


def test_discover_quarters_empty_for_a_bank_with_no_calls(monkeypatch):
    """Three listed banks hold no call. That is an answer, not an error."""
    monkeypatch.setattr(
        alphaspread, "_get",
        lambda url, **kw: _Resp("<html><body>No Earnings Calls Available</body></html>"),
    )
    assert alphaspread.discover_quarters("skbnk.e") == []


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_parse_call_splits_turns(monkeypatch, call_page):
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(call_page))
    call = alphaspread.parse_call("TEST", "test.e", "2026Q1")

    assert [t.speaker for t in call.turns] == [
        "Cenk Gur", "Operator", "David Taranto",
    ]
    assert [t.role for t in call.turns] == ["executive", None, "analyst"]
    assert call.turns[0].seq == 1
    # Both <p> of the first turn join into one text body.
    assert "Good afternoon" in call.turns[0].text
    assert "TRY 19.1 billion" in call.turns[0].text


def test_parse_call_ignores_blocks_above_the_anchor(monkeypatch, call_page):
    """The AI-summary comment block sits before #earnings-call-transcript."""
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(call_page))
    call = alphaspread.parse_call("TEST", "test.e", "2026Q1")
    assert all(t.speaker != "Summary Bot" for t in call.turns)
    assert all("must be ignored" not in t.text for t in call.turns)


def test_parse_call_drops_empty_turns(monkeypatch, call_page):
    """A comment block with an empty body is not a turn."""
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(call_page))
    call = alphaspread.parse_call("TEST", "test.e", "2026Q1")
    assert all(t.speaker != "Empty Speaker" for t in call.turns)


def test_parse_call_reads_the_date(monkeypatch, call_page):
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(call_page))
    assert alphaspread.parse_call("TEST", "test.e", "2026Q1").call_date == "2026-04-28"


def test_counters(monkeypatch, call_page):
    """The quality counters are the point of the lane, not decoration."""
    monkeypatch.setattr(alphaspread, "_get", lambda url, **kw: _Resp(call_page))
    call = alphaspread.parse_call("TEST", "test.e", "2026Q1")
    assert call.speaker_count == 3
    assert call.analyst_turn_count == 1
    # Two '[indiscernible]' markers across two different turns.
    assert call.indiscernible_count == 2
    assert call.word_count == sum(len(t.text.split()) for t in call.turns)


def test_parse_call_builds_the_right_url(monkeypatch, call_page):
    seen: list[str] = []

    def _spy(url, **kw):
        seen.append(url)
        return _Resp(call_page)

    monkeypatch.setattr(alphaspread, "_get", _spy)
    alphaspread.parse_call("TEST", "test.e", "2026Q3")
    assert seen == [
        "https://www.alphaspread.com/security/ist/test.e"
        "/investor-relations/earnings-call/q3-2026"
    ]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def _call(period="2026Q1", turns=None):
    return alphaspread.Call(
        bank_ticker="TEST", period=period, call_date="2026-04-28",
        source_url="https://example.invalid/x",
        turns=turns if turns is not None
        else [alphaspread.Turn(1, "A", "executive", "hello world")],
    )


def test_upsert_is_idempotent(conn):
    assert upsert_calls(conn, [_call()]) == 1
    upsert_calls(conn, [_call()])
    n = conn.execute("SELECT COUNT(*) FROM bank_call_transcripts").fetchone()[0]
    assert n == 1


def test_upsert_skips_a_call_with_no_turns(conn):
    """An empty transcript_json would render as 'the bank said nothing'."""
    assert upsert_calls(conn, [_call(turns=[])]) == 0
    assert conn.execute("SELECT COUNT(*) FROM bank_call_transcripts").fetchone()[0] == 0


def test_existing_periods_round_trips(conn):
    upsert_calls(conn, [_call("2026Q1"), _call("2025Q4")])
    assert existing_periods(conn, "TEST") == {"2026Q1", "2025Q4"}
    assert existing_periods(conn, "OTHER") == set()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_ddl_matches_the_migration():
    """The Python DDL and the D1 migration must not drift apart — push_to_d1
    stages into the local SQLite and assumes the two agree."""
    def norm(s: str) -> str:
        body = s[s.index("CREATE TABLE"):]
        return re.sub(r"\s+", " ", body).strip()

    assert norm(DDL) == norm(MIGRATION.read_text(encoding="utf-8"))


def test_table_is_pushed_to_d1():
    """A table missing from SYNC_TABLES is NEVER pushed — silently."""
    push = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    assert '"bank_call_transcripts",' in push
    # …and it must window on its own timestamp, or every run re-pushes the corpus.
    sync_block = push[push.index("elif table in (\"news_items\""):]
    assert "bank_call_transcripts" in sync_block[:300]
