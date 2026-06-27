"""Refresh the investor-presentation deck rows in bank_earnings (tier 2).

For each bank in data/banks/investor_presentation_urls.json, emit one
``presentation_deck`` event per quarter from the static config, augmented by any
newer quarters auto-discovered from the IR page (banks in
src.earnings.presentations.PRESENTATION_BANKS). Idempotent: rows are keyed
``<TICKER>-<period>-presentation`` so re-runs overwrite in place.

Decks have no natural publish timestamp, so ``event_date`` is set to the
quarter-end date the deck covers (stable, meaningful for the calendar).

Usage:
  python scripts/update_presentations.py
  python scripts/update_presentations.py --db data/bddk_data.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.earnings.loader import EarningsEvent, upsert_events  # noqa: E402
from src.earnings.presentations import discover_presentation_targets  # noqa: E402
from src.earnings.schema import init_schema  # noqa: E402

CONFIG = REPO / "data" / "banks" / "investor_presentation_urls.json"
DB_PATH = REPO / "data" / "bddk_data.db"

_QEND = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}


def _quarter_end_iso(period: str) -> str:
    """'2026Q1' -> '2026-03-31T00:00:00+00:00' (the period the deck covers)."""
    year, q = period[:4], period[4:].upper()
    return f"{year}-{_QEND.get(q, '12-31')}T00:00:00+00:00"


def _label(period: str) -> str:
    """'2026Q1' -> 'Q1 2026 earnings presentation'."""
    return f"{period[4:].upper()} {period[:4]} earnings presentation"


def _events_for_bank(ticker: str, cfg: dict) -> list[EarningsEvent]:
    # Static config first, then discovery overrides/augments by period.
    pm: dict[str, str] = dict((cfg.get("urls", {}).get("presentation") or {}))
    for period, url in discover_presentation_targets(ticker, cfg):
        pm[period.upper()] = url

    events = []
    for period, url in pm.items():
        period = period.upper()
        events.append(EarningsEvent(
            source="ir",
            external_id=f"{ticker}-{period}-presentation",
            ticker=ticker,
            kind="presentation_deck",
            event_date=_quarter_end_iso(period),
            url=url,
            period=period,
            title=_label(period),
            language="en",
            raw_json=json.dumps({"ir_page": cfg.get("ir_page")}, ensure_ascii=False),
        ))
    return events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    banks = cfg.get("banks", {})

    all_events: list[EarningsEvent] = []
    for ticker, bank_cfg in banks.items():
        evs = _events_for_bank(ticker, bank_cfg)
        all_events.extend(evs)
        print(f"[present] {ticker}: {len(evs)} deck(s)")

    with sqlite3.connect(args.db) as conn:
        init_schema(conn)
        n = upsert_events(conn, all_events)
    print(f"[present] upserted {n} presentation rows for {len(banks)} bank(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
