-- §4 risk-management tables (deterministic extraction; see
-- src/audit_reports/capital_adequacy.py + liquidity.py). Mirrors the CREATE
-- statements in src/audit_reports/schema.py so the local SQLite and D1 agree.
-- IF NOT EXISTS → safe to re-apply.

CREATE TABLE IF NOT EXISTS bank_audit_capital (
    bank_ticker              TEXT NOT NULL,
    period                   TEXT NOT NULL,
    kind                     TEXT NOT NULL,
    period_type              TEXT NOT NULL,        -- 'current' | 'prior'
    cet1_capital             REAL,                 -- Common Equity Tier 1 capital
    additional_tier1_capital REAL,
    tier1_capital            REAL,
    tier2_capital            REAL,
    total_capital            REAL,                 -- own funds (Tier 1 + Tier 2)
    total_rwa                REAL,                 -- total risk-weighted assets
    cet1_ratio               REAL,                 -- percent
    tier1_ratio              REAL,                 -- percent
    capital_adequacy_ratio   REAL,                 -- CAR, percent
    source_page              INTEGER,
    extracted_at             TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_capital_bank_period
  ON bank_audit_capital(bank_ticker, period);

CREATE TABLE IF NOT EXISTS bank_audit_liquidity (
    bank_ticker     TEXT NOT NULL,
    period          TEXT NOT NULL,
    kind            TEXT NOT NULL,
    period_type     TEXT NOT NULL,        -- 'current' | 'prior'
    leverage_ratio  REAL,                 -- percent (3-month average)
    lcr_total       REAL,                 -- Liquidity Coverage Ratio, total, percent
    lcr_fc          REAL,                 -- LCR, foreign currency, percent
    nsfr            REAL,                 -- Net Stable Funding Ratio, percent
    source_page     INTEGER,
    extracted_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_liquidity_bank_period
  ON bank_audit_liquidity(bank_ticker, period);
