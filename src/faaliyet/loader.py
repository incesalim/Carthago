"""Idempotent upserts for the faaliyet_* tables.

``upsert_report`` replaces a bank's ``(bank_ticker, fiscal_year)`` partition in
``faaliyet_franchise`` and writes one ``faaliyet_extractions`` provenance row,
both with a fresh ``extracted_at`` so the incremental D1 push picks them up.

This lane sources only the metrics the audit reports don't carry (ATM / POS /
merchant / customer / card counts), so there is nothing here to cross-check
against ``bank_audit_profile`` — branches and employees stay in the audit lane.
"""
from __future__ import annotations

import sqlite3

from .extractor import FranchiseReport

_INSERT = (
    "INSERT OR REPLACE INTO faaliyet_franchise"
    " (bank_ticker, fiscal_year, metric_key, period_type, value, unit,"
    "  source_page, source_lang, anchor, raw_snippet, confidence, extracted_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
)


def upsert_report(conn: sqlite3.Connection, ticker: str, year: int,
                  rep: FranchiseReport, source_url: str | None = None,
                  r2_key: str | None = None) -> int:
    """Replace the (ticker, year) partition and log the extraction. Returns rows."""
    conn.execute(
        "DELETE FROM faaliyet_franchise WHERE bank_ticker = ? AND fiscal_year = ?",
        (ticker, year),
    )
    rows = [(
        ticker, year, s.metric_key, s.period_type, s.value, s.unit,
        s.source_page, s.source_lang, s.anchor, s.raw_snippet, s.confidence,
    ) for s in rep.stats]
    if rows:
        conn.executemany(_INSERT, rows)
    n_current = sum(1 for s in rep.stats if s.period_type == "current")
    conn.execute(
        "INSERT OR REPLACE INTO faaliyet_extractions"
        " (bank_ticker, fiscal_year, source_url, r2_key, n_pages, report_lang,"
        "  is_ocr, metrics_found, success, note, extracted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (ticker, year, source_url, r2_key, rep.n_pages, rep.report_lang,
         int(rep.is_ocr), n_current, int(n_current > 0 and not rep.is_ocr), None),
    )
    conn.commit()
    return len(rows)


def mark_fetch(conn: sqlite3.Connection, ticker: str, year: int, status: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO faaliyet_fetch_log (bank_ticker, fiscal_year, status,"
        " fetched_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (ticker, year, status),
    )
    conn.commit()


def fetch_done(conn: sqlite3.Connection, ticker: str, year: int) -> bool:
    row = conn.execute(
        "SELECT status FROM faaliyet_fetch_log WHERE bank_ticker = ? AND fiscal_year = ?",
        (ticker, year),
    ).fetchone()
    return bool(row) and row[0] in ("done", "ocr", "no_pdf")
