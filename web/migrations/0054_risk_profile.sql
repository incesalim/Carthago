-- Pillar 3 risk profile by sector — 17 standardised-approach exposure
-- classes + TL/FC/Total, per sector row.
-- Sourced from the "Sektöre Göre Risk Profili" / "Risk Profile by
-- Sectors" table in the Pillar 3 footnote section. Same taxonomy and
-- shape as loans_by_currency's sector rows; additive, new table.
CREATE TABLE IF NOT EXISTS bank_audit_risk_profile (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    sector           TEXT NOT NULL,       -- same taxonomy as loans_by_sector
    period_type      TEXT NOT NULL,       -- 'current' | 'prior'
    source_page      INTEGER,
    raw_label        TEXT,
    class_1          REAL,               -- Central Government / Sovereign
    class_2          REAL,               -- Regional / Local Government
    class_3          REAL,               -- Administrative / Non-commercial
    class_4          REAL,               -- Multilateral Development Banks
    class_5          REAL,               -- International Organisations
    class_6          REAL,               -- Banks and Brokers / Financial
    class_7          REAL,               -- Corporate
    class_8          REAL,               -- Retail
    class_9          REAL,               -- Residential Mortgage-secured
    class_10         REAL,               -- Commercial Real Estate / Mortgage
    class_11         REAL,               -- Past-due / Overdue
    class_12         REAL,               -- High(er)-risk
    class_13         REAL,               -- Covered Bond / Mortgage-backed
    class_14         REAL,               -- Securitisation / Short-term
    class_15         REAL,               -- Collective Investment / Mutual Fund
    class_16         REAL,               -- Equity / Share
    class_17         REAL,               -- Other Receivables / Exposure
    tl_amount        REAL,               -- TL (local currency) total, thousands
    fc_amount        REAL,               -- FC (foreign currency) total, thousands
    total            REAL,               -- grand total, thousands
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);
CREATE INDEX IF NOT EXISTS idx_bank_rp_bank_period
  ON bank_audit_risk_profile(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_rp_sector
  ON bank_audit_risk_profile(sector);
