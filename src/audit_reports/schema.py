"""SQLite schema for per-bank quarterly BRSA audit-report data.

Three tables coexist with the existing BDDK aggregate tables in data/bddk_data.db:

  bank_audit_balance_sheet  — Assets, Liabilities, Off-Balance (6-column format)
  bank_audit_profit_loss    — P&L line items (single amount column)
  bank_audit_extractions    — One row per (bank, period, kind) extraction run
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_balance_sheet (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    statement   TEXT NOT NULL,           -- 'assets' | 'liabilities' | 'off_balance'
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount_tl    REAL,
    amount_fc    REAL,
    amount_total REAL,
    PRIMARY KEY (bank_ticker, period, kind, statement, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_bs_bank_period
  ON bank_audit_balance_sheet(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_bs_item_name
  ON bank_audit_balance_sheet(item_name);


CREATE TABLE IF NOT EXISTS bank_audit_profit_loss (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount      REAL,
    PRIMARY KEY (bank_ticker, period, kind, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_pl_bank_period
  ON bank_audit_profit_loss(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_pl_item_name
  ON bank_audit_profit_loss(item_name);


CREATE TABLE IF NOT EXISTS bank_audit_extractions (
    bank_ticker          TEXT NOT NULL,
    period               TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    pdf_path             TEXT NOT NULL,
    extracted_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rows_bs_assets       INTEGER,
    rows_bs_liabilities  INTEGER,
    rows_off_balance     INTEGER,
    rows_profit_loss     INTEGER,
    success              INTEGER NOT NULL DEFAULT 1,
    note                 TEXT,
    PRIMARY KEY (bank_ticker, period, kind)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


if __name__ == '__main__':
    import sys
    from pathlib import Path
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('data/bddk_data.db')
    with sqlite3.connect(db) as conn:
        init_schema(conn)
    print(f'schema initialized at {db}')
