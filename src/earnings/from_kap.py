"""Project classified KAP disclosures into bank_earnings events.

Reads the KAP rows already ingested into ``news_items`` (``source='kap'``) by
``src.news.sources.kap`` — no new network. Each row is classified
(``classify_kind``) and dated (``derive_period``); non-earnings rows are
dropped.

A bank files its quarterly ``Finansal Rapor`` more than once per quarter
(consolidated + unconsolidated, each a distinct KAP disclosure), so
``results_filing`` events are **deduped to one per (ticker, period)** — keyed
``'<TICKER>-<period>-results'`` and dated to the earliest filing — to give a
clean results calendar. Any other (future) kind is emitted per-filing, keyed on
the KAP disclosure index.
"""
from __future__ import annotations

import json
import sqlite3

from src.earnings.classify import RESULTS_FILING, classify_kind, derive_period
from src.earnings.loader import EarningsEvent


def events_from_kap(conn: sqlite3.Connection, days_back: int | None = None) -> list[EarningsEvent]:
    """Build earnings events from stored KAP disclosures.

    ``days_back`` bounds the scan to recently-published rows; ``None`` scans all
    (cheap — the KAP corpus is small). Re-running is idempotent.
    """
    where = "WHERE source='kap'"
    params: tuple = ()
    if days_back is not None:
        where += " AND published_at >= datetime('now', ?)"
        params = (f"-{int(days_back)} days",)

    rows = conn.execute(
        f"""SELECT external_id, ticker, category, title, summary,
                   url, published_at, language, raw_json
            FROM news_items {where}""",
        params,
    ).fetchall()

    # Dedup key -> chosen event (results_filing collapses per ticker+period).
    chosen: dict[str, EarningsEvent] = {}

    for ext_id, ticker, _cat, title, summary, url, published_at, language, raw in rows:
        if not ticker:
            continue
        try:
            raw_d = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            raw_d = {}
        kind = classify_kind(title, raw_d.get("disclosureType"), summary)
        if kind is None:
            continue
        period = derive_period(raw_d, title, summary, published_at)

        evidence = json.dumps(
            {
                "kap_index": ext_id,
                "disclosureType": raw_d.get("disclosureType"),
                "ruleType": raw_d.get("ruleType"),
                "kapTitle": raw_d.get("kapTitle"),
            },
            ensure_ascii=False,
        )

        if kind == RESULTS_FILING and period:
            key = f"{ticker}-{period}-results"
            prev = chosen.get(key)
            # Keep the earliest filing of the quarter.
            if prev is None or (published_at or "") < (prev.event_date or ""):
                chosen[key] = EarningsEvent(
                    source="kap", external_id=key, ticker=ticker, kind=kind,
                    event_date=published_at, url=url, period=period,
                    title=title, language=language or "tr", raw_json=evidence,
                )
        else:
            # Per-filing event (other kinds, or results with no derivable period).
            key = f"kap-{ext_id}"
            chosen[key] = EarningsEvent(
                source="kap", external_id=str(ext_id), ticker=ticker, kind=kind,
                event_date=published_at, url=url, period=period,
                title=title, language=language or "tr", raw_json=evidence,
            )

    return list(chosen.values())
