"""SQLite + D1 schema for the Faaliyet Raporları (annual-report) franchise lane.

Two pushed tables — a tall ``faaliyet_franchise`` fact table (one row per
disclosed statistic) and a ``faaliyet_extractions`` provenance/coverage log
(mirrors ``bank_audit_extractions``). A tall shape keeps the franchise metric
set open-ended (new metric = new ``metric_key`` value, no migration) and gives
every captured value its own provenance columns — the audit-extractor debug
discipline.

``faaliyet_fetch_log`` is staging-side only (backfill resume bookkeeping) and is
NOT pushed to D1; the D1 migration ``web/migrations/0014_faaliyet_franchise.sql``
mirrors the two pushed tables exactly (same column order + PK) so push_to_d1's
INSERT OR REPLACE conflict-detection behaves identically.

Annual cadence: keyed by ``fiscal_year`` (FY ending 31 Dec). A single report
routinely prints a prior-year comparative, so one PDF can seed both
``period_type='current'`` and ``period_type='prior'`` and a multi-year series
accretes across reports via INSERT OR REPLACE.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS faaliyet_franchise (
    bank_ticker  TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,                 -- FY ending 31 Dec
    metric_key   TEXT NOT NULL,                    -- see extractor.METRIC_KEYS
    period_type  TEXT NOT NULL DEFAULT 'current',  -- 'current' | 'prior'
    value        REAL,                             -- numeric value in `unit`
    unit         TEXT NOT NULL,                    -- 'count' | 'count_th' | 'count_mn'
    source_page  INTEGER,                          -- 1-based PDF page the anchor matched
    source_lang  TEXT,                             -- 'tr' | 'en'
    anchor       TEXT,                             -- anchor keyword matched
    raw_snippet  TEXT,                             -- ±chars around the match, for audit
    confidence   TEXT,                             -- 'high' | 'medium' | 'low'
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, fiscal_year, metric_key, period_type)
);
CREATE INDEX IF NOT EXISTS idx_faaliyet_metric
  ON faaliyet_franchise(metric_key, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_faaliyet_bank
  ON faaliyet_franchise(bank_ticker, fiscal_year);

-- One row per (bank, fiscal_year) extraction run — provenance + coverage log.
-- is_ocr flags an image-only PDF (no text layer): deterministically skipped,
-- not a failure (no OCR — honors the no-LLM/deterministic constraint).
CREATE TABLE IF NOT EXISTS faaliyet_extractions (
    bank_ticker   TEXT NOT NULL,
    fiscal_year   INTEGER NOT NULL,
    source_url    TEXT,
    r2_key        TEXT,
    n_pages       INTEGER,
    report_lang   TEXT,                            -- 'tr' | 'en'
    is_ocr        INTEGER NOT NULL DEFAULT 0,
    metrics_found INTEGER NOT NULL DEFAULT 0,
    success       INTEGER NOT NULL DEFAULT 0,
    note          TEXT,                            -- cross-check warnings, parse notes
    extracted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, fiscal_year)
);

-- Staging-side ONLY (backfill resume bookkeeping) — NOT pushed to D1.
CREATE TABLE IF NOT EXISTS faaliyet_fetch_log (
    bank_ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    status      TEXT NOT NULL,                     -- 'done' | 'no_pdf' | 'ocr' | 'error'
    fetched_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, fiscal_year)
);

-- Shared staging-side outbox (created by the KAP/TEFAS lanes too; IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS d1_pending_deletes (
    sql        TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/bddk_data.db")
    with sqlite3.connect(db) as conn:
        init_schema(conn)
    print(f"Initialized faaliyet_* schema in {db}")
