-- Loans by sector — currency split (TL / FC by sector).
-- Additive, new table: does not touch the settled loans_by_sector stage columns.
-- Captures the TL/FC/[%] columns printed alongside the Stage 2/3/ECL columns
-- in the BRSA "Information by major sectors" footnote.
CREATE TABLE IF NOT EXISTS bank_audit_loans_currency (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    sector           TEXT NOT NULL,       -- same taxonomy as loans_by_sector
    period_type      TEXT NOT NULL,       -- 'current' | 'prior'
    source_page      INTEGER,
    tl_amount        REAL,               -- TL (local currency) amount, thousands
    fc_amount        REAL,               -- FC (foreign currency) amount, thousands
    tl_pct           REAL,               -- percentage of TL (nullable; not all banks disclose)
    fc_pct           REAL,               -- percentage of FC (nullable)
    raw_label        TEXT,
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);
CREATE INDEX IF NOT EXISTS idx_bank_lc_bank_period
  ON bank_audit_loans_currency(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_lc_sector
  ON bank_audit_loans_currency(sector);
