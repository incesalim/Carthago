"""Offline tests for the earnings loader + KAP projection (no network)."""
from __future__ import annotations

import json
import sqlite3

from src.earnings.from_kap import events_from_kap
from src.earnings.loader import EarningsEvent, upsert_events
from src.earnings.schema import init_schema
from src.news.loader import NewsItem, upsert_items
from src.news.schema import init_schema as init_news_schema


def _mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    init_news_schema(conn)
    return conn


def test_upsert_idempotent_and_overwrites_in_place():
    conn = _mem_db()
    ev = EarningsEvent(
        source="ir", external_id="AKBNK-2026Q1-presentation", ticker="AKBNK",
        kind="presentation_deck", event_date="2026-03-31T00:00:00+00:00",
        url="https://example.com/v1.pdf", period="2026Q1", title="Q1 2026",
    )
    upsert_events(conn, [ev])
    # Re-running with a new URL for the same key overwrites, not duplicates.
    ev2 = EarningsEvent(**{**ev.__dict__, "url": "https://example.com/v2.pdf"})
    upsert_events(conn, [ev2])
    rows = conn.execute("SELECT url FROM bank_earnings WHERE external_id=?",
                        (ev.external_id,)).fetchall()
    assert rows == [("https://example.com/v2.pdf",)]


def _kap_item(ext_id: str, ticker: str, subject: str, raw: dict, published: str) -> NewsItem:
    return NewsItem(
        source="kap", external_id=ext_id, published_at=published, ticker=ticker,
        category=raw.get("disclosureCategory"), title=subject, summary=raw.get("summary"),
        url=f"https://www.kap.org.tr/tr/Bildirim/{ext_id}", language="tr",
        raw_json=json.dumps(raw, ensure_ascii=False),
    )


def test_from_kap_dedups_results_per_quarter():
    conn = _mem_db()
    base = {"disclosureType": "FR", "disclosureCategory": "FR",
            "year": 2026, "period": 1, "ruleType": "3 Aylık", "kapTitle": "AKBANK"}
    upsert_items(conn, [
        # Two Finansal Rapor filings (consolidated + unconsolidated) same quarter.
        _kap_item("200", "AKBNK", "Finansal Rapor", base, "2026-05-08T16:16:00+00:00"),
        _kap_item("201", "AKBNK", "Finansal Rapor", base, "2026-05-08T16:14:00+00:00"),
        # A non-earnings disclosure that must be ignored.
        _kap_item("202", "AKBNK", "Özel Durum Açıklaması (Genel)",
                  {"disclosureType": "ODA", "disclosureCategory": "ODA"},
                  "2026-05-09T10:00:00+00:00"),
    ])
    events = events_from_kap(conn)
    assert len(events) == 1
    e = events[0]
    assert e.kind == "results_filing"
    assert e.external_id == "AKBNK-2026Q1-results"
    assert e.period == "2026Q1"
    # Keeps the EARLIEST filing of the quarter (16:14, disclosure 201).
    assert e.event_date == "2026-05-08T16:14:00+00:00"
    assert e.url.endswith("/201")
