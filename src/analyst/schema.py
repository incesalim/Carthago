"""Staging DDL for the analyst tables — the local mirror of
`web/migrations/0037_analyst_signals.sql`.

The migration file is the schema source of truth (hand-authored, per
docs/SCHEMA_CONVENTIONS.md); this mirror exists so the staging SQLite can be
built and tested locally, and so `push_to_d1.py` has a local table to read
WHEN the D1-write freeze lifts. Keep the two in lockstep — the pytest gate
diffs the CREATE TABLE column lists.
"""
from __future__ import annotations

import sqlite3

ANALYST_TABLES = ["analyst_signals", "analyst_notes", "analyst_basis_metadata"]

DDL = """
CREATE TABLE IF NOT EXISTS analyst_signals (
    signal_id     TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    severity      TEXT NOT NULL,
    fired_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload       TEXT NOT NULL,
    PRIMARY KEY (signal_id)
);
CREATE INDEX IF NOT EXISTS idx_signals_bank_period ON analyst_signals(bank_ticker, period);

CREATE TABLE IF NOT EXISTS analyst_notes (
    note_id       TEXT NOT NULL,
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    signal_ids    TEXT NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model         TEXT,
    fact_check_passed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (note_id)
);
CREATE INDEX IF NOT EXISTS idx_notes_bank_period ON analyst_notes(bank_ticker, period);

CREATE TABLE IF NOT EXISTS analyst_basis_metadata (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    reporting_unit   TEXT,
    unit_source      TEXT NOT NULL,
    assurance_level  TEXT NOT NULL,
    assurance_source TEXT NOT NULL,
    consolidation_basis TEXT NOT NULL,
    PRIMARY KEY (bank_ticker, period, kind)
);
CREATE INDEX IF NOT EXISTS idx_basis_bank_period ON analyst_basis_metadata(bank_ticker, period);
"""


def init_analyst_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()
