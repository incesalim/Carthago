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
    rows_credit_quality  INTEGER,
    success              INTEGER NOT NULL DEFAULT 1,
    note                 TEXT,
    PRIMARY KEY (bank_ticker, period, kind)
);


-- IFRS 9 staging extracts: every Stage 1/2/3/Total movement table found in
-- the audit-report footnotes, plus the GARAN-style stage-amount summary.
-- One row per (bank, period, kind, section, period_type).
--
-- `section` taxonomy (best-effort label from the heading above the table):
--   loans_ecl              — Expected credit loss provisions for loans
--   loans_amounts          — Actual loan balances by stage (TL+FC sum)
--   cash_ecl               — ECL for cash & cash equivalents
--   amortised_cost_ecl     — ECL for financial assets at amortized cost
--   non_cash_ecl           — ECL for non-cash loans / commitments / guarantees
--   other_ecl              — Any other Stage 1/2/3 movement table we can't classify
--
-- `period_type` distinguishes "Current Period" tables from "Prior Period"
-- comparatives that often sit immediately below in the same footnote.
CREATE TABLE IF NOT EXISTS bank_audit_credit_quality (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    section          TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,
    heading_snippet  TEXT,                    -- raw heading we matched on, for debug
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, section, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_cq_bank_period
  ON bank_audit_credit_quality(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_cq_section
  ON bank_audit_credit_quality(section);


-- Bank-profile metadata extracted from the qualitative section of the
-- audit report: branch counts (domestic / foreign / total) and personnel.
-- One row per (bank, period, kind). Any field may be NULL if the bank's
-- report didn't disclose it in a recognized format.
CREATE TABLE IF NOT EXISTS bank_audit_profile (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    branches_domestic  INTEGER,
    branches_foreign   INTEGER,
    branches_total     INTEGER,
    personnel          INTEGER,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);


-- Sector-level loan exposure with TFRS 9 stage breakdown. Sourced from
-- the "Information by major sectors and type of counterparties" /
-- "Önemli Sektörlere veya Karşı Taraf Türüne Göre" footnote table.
--
-- One row per (bank, period, kind, sector, period_type). The `sector`
-- key is a canonical short code mapped from bilingual labels:
--   agri_total, agri_farming, agri_forestry, agri_fishery,
--   mfg_total, mfg_mining, mfg_production, mfg_utilities,
--   construction,
--   svc_total, svc_trade, svc_hospitality, svc_transport,
--   svc_financial, svc_realestate, svc_professional,
--   svc_education, svc_health,
--   other, total.
--
-- *_total keys are the group parent (sum of sub-sectors). `total` is the
-- grand total across all groups.
CREATE TABLE IF NOT EXISTS bank_audit_loans_by_sector (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    sector           TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    stage2_amount    REAL,                    -- loans with significant increase in credit risk
    stage3_amount    REAL,                    -- defaulted / impaired loans (sector NPL gross)
    ecl_amount       REAL,                    -- expected credit loss provisions
    raw_label        TEXT,                    -- original row label, for debug
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_lbs_bank_period
  ON bank_audit_loans_by_sector(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_lbs_sector
  ON bank_audit_loans_by_sector(sector);


-- NPL gross-amount roll-forward by BRSA severity group (III / IV / V).
-- Sourced from the "Information on the movement of non-performing loans"
-- / "Toplam donuk alacak hareketlerine ilişkin bilgiler" footnote.
--
-- For each (bank, period, kind, group_code, period_type) row:
--   opening_balance     prior-period-end NPL balance
--   additions           new NPL inflows during the period
--   transfers_in        loans migrating INTO this group from another NPL group
--   transfers_out       loans migrating OUT of this group to another NPL group
--   collections         recoveries during the period
--   write_offs          write-downs against the balance sheet
--   sold                NPL portfolio sales
--   fx_diff             FX revaluation (rare; GARAN-style banks only)
--   closing_balance     period-end NPL balance
--   provision           cumulative loss provision against the group
--   net_balance         closing_balance − provision (carrying amount)
CREATE TABLE IF NOT EXISTS bank_audit_npl_movement (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    group_code         TEXT NOT NULL,         -- 'III' | 'IV' | 'V'
    period_type        TEXT NOT NULL,         -- 'current' | 'prior'
    source_page        INTEGER,
    opening_balance    REAL,
    additions          REAL,
    transfers_in       REAL,
    transfers_out      REAL,
    collections        REAL,
    write_offs         REAL,
    sold               REAL,
    fx_diff            REAL,
    closing_balance    REAL,
    provision          REAL,
    net_balance        REAL,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, group_code, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_npl_bank_period
  ON bank_audit_npl_movement(bank_ticker, period);


-- Consolidated TFRS 9 stage view per (bank, period, kind, period_type).
-- Derived from bank_audit_credit_quality by combining the four sources
-- that publish Stage 1/2/3 figures:
--   amounts:
--     1st choice  bank_audit_credit_quality.section='loans_amounts'
--                 (single row holds S1/S2/S3 inline — AKBNK-style banks)
--     2nd choice  section='loans_by_stage' for S1+S2 +
--                 section='npl_brsa_gross'.total_amount for S3
--   provisions:
--     1st choice  section='loans_ecl'      (full S1/S2/S3)
--     2nd choice  section='loans_ecl_brsa' for S1+S2 +
--                 section='npl_brsa_provision'.total_amount for S3
--
-- Coverage ratio = ecl / amount per stage. Stored as REAL fractions
-- (0.0083 = 0.83%) so the consumer chooses formatting.
--
-- Populated by scripts/build_bank_audit_stages.py — re-run whenever
-- credit_quality data changes.
CREATE TABLE IF NOT EXISTS bank_audit_stages (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,                    -- stage1 + stage2 + stage3
    stage1_ecl       REAL,
    stage2_ecl       REAL,
    stage3_ecl       REAL,
    total_ecl        REAL,                    -- stage1 + stage2 + stage3 ECL
    stage1_coverage  REAL,                    -- stage1_ecl / stage1_amount
    stage2_coverage  REAL,
    stage3_coverage  REAL,
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_stages_bank_period
  ON bank_audit_stages(bank_ticker, period);
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
