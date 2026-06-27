-- 0014_faaliyet_franchise
-- Faaliyet Raporları (bank annual / activity reports) franchise lane — deterministic
-- pdfplumber/fitz extraction of the operational statistics the audited statements
-- do NOT carry (ATM / POS / merchant / customer / card counts) for the audited-bank
-- universe. Branches & employees stay in bank_audit_profile (the audit lane), not
-- here. Separate lane from bank_audit_* (BS/P&L are frozen). Mirrors
-- src/faaliyet/schema.py exactly (minus the staging-only faaliyet_fetch_log);
-- composite PRIMARY KEYs match the SQLite staging tables so push_to_d1's
-- INSERT OR REPLACE conflict-detection behaves identically. Idempotent.

CREATE TABLE IF NOT EXISTS faaliyet_franchise (
    bank_ticker  TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,                 -- FY ending 31 Dec
    metric_key   TEXT NOT NULL,                    -- atm_count, pos_count, merchant_count,
                                                   -- customer_total/_active/_digital,
                                                   -- cards_credit/_debit/_total
    period_type  TEXT NOT NULL DEFAULT 'current',  -- 'current' | 'prior'
    value        REAL,                             -- numeric value in `unit`
    unit         TEXT NOT NULL,                    -- 'count' | 'count_th' | 'count_mn'
    source_page  INTEGER,
    source_lang  TEXT,                             -- 'tr' | 'en'
    anchor       TEXT,
    raw_snippet  TEXT,
    confidence   TEXT,                             -- 'high' | 'medium' | 'low'
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, fiscal_year, metric_key, period_type)
);

CREATE INDEX IF NOT EXISTS idx_faaliyet_metric
  ON faaliyet_franchise(metric_key, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_faaliyet_bank
  ON faaliyet_franchise(bank_ticker, fiscal_year);

CREATE TABLE IF NOT EXISTS faaliyet_extractions (
    bank_ticker   TEXT NOT NULL,
    fiscal_year   INTEGER NOT NULL,
    source_url    TEXT,
    r2_key        TEXT,
    n_pages       INTEGER,
    report_lang   TEXT,                            -- 'tr' | 'en'
    is_ocr        INTEGER NOT NULL DEFAULT 0,      -- 1 = image-only PDF (skipped, not a failure)
    metrics_found INTEGER NOT NULL DEFAULT 0,
    success       INTEGER NOT NULL DEFAULT 0,
    note          TEXT,
    extracted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, fiscal_year)
);
