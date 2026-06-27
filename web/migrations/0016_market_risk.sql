-- §4 market-risk (CAMELS "S") per-bank audit tables: FX net open position and
-- interest-rate repricing/maturity gap. Mirrors src/audit_reports/schema.py.
-- Deterministic pdfplumber/fitz extraction (no LLM), same lane as
-- bank_audit_capital / bank_audit_liquidity.

CREATE TABLE IF NOT EXISTS bank_audit_fx_position (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    period_type        TEXT NOT NULL,        -- 'current' | 'prior'
    currency           TEXT NOT NULL,        -- 'EUR' | 'USD' | 'GBP' | 'OTHER' | 'TOTAL'
    on_bs_assets       REAL,
    on_bs_liab         REAL,
    net_on_balance     REAL,
    net_off_balance    REAL,
    off_bs_receivable  REAL,
    off_bs_payable     REAL,
    net_position       REAL,
    source_page        INTEGER,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, currency)
);

CREATE INDEX IF NOT EXISTS idx_bank_fx_bank_period
  ON bank_audit_fx_position(bank_ticker, period);

CREATE TABLE IF NOT EXISTS bank_audit_repricing (
    bank_ticker            TEXT NOT NULL,
    period                 TEXT NOT NULL,
    kind                   TEXT NOT NULL,
    period_type            TEXT NOT NULL,    -- 'current' | 'prior'
    bucket                 TEXT NOT NULL,    -- lt_1m|1_3m|3_12m|1_5y|gt_5y|non_sensitive|total
    rate_sensitive_assets  REAL,
    rate_sensitive_liab    REAL,
    gap                    REAL,
    cumulative_gap         REAL,
    source_page            INTEGER,
    extracted_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, bucket)
);

CREATE INDEX IF NOT EXISTS idx_bank_repricing_bank_period
  ON bank_audit_repricing(bank_ticker, period);
