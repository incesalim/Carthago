-- Cash flow statement table.
-- Single-column format (like OCI): current period amount only.
-- Rows: A./B./C. section headers (no values), numeric sub-items, I.–VII. roman subtotals.
-- Identity chain: V = I+II+III+IV; VII = V+VI.
CREATE TABLE IF NOT EXISTS bank_audit_cash_flow (
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

CREATE INDEX IF NOT EXISTS idx_bank_cash_flow_bank_period
  ON bank_audit_cash_flow(bank_ticker, period);

-- Statement of changes in equity (wide fixed-column table).
-- 14 value columns (unconsolidated) or 16 (consolidated + minority interest).
-- Two pages per partition: period_type = 'current' | 'prior'.
CREATE TABLE IF NOT EXISTS bank_audit_equity_change (
    bank_ticker                  TEXT NOT NULL,
    period                       TEXT NOT NULL,
    kind                         TEXT NOT NULL,
    period_type                  TEXT NOT NULL,
    item_order                   INTEGER NOT NULL,
    hierarchy                    TEXT,
    item_name                    TEXT NOT NULL,
    paid_in_capital              REAL,
    share_premium                REAL,
    share_cancellation_profits   REAL,
    other_capital_reserves       REAL,
    oci_not_reclassified_1       REAL,
    oci_not_reclassified_2       REAL,
    oci_not_reclassified_3       REAL,
    oci_reclassified_1           REAL,
    oci_reclassified_2           REAL,
    oci_reclassified_3           REAL,
    profit_reserves              REAL,
    prior_period_profit_loss     REAL,
    period_net_profit_loss       REAL,
    total_equity                 REAL,
    minority_interest            REAL,
    total_equity_incl_minority   REAL,
    source_page                  INTEGER,
    extracted_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_equity_change_bank_period
  ON bank_audit_equity_change(bank_ticker, period);

-- Extraction counters for the two new statement types.
ALTER TABLE bank_audit_extractions ADD COLUMN rows_cash_flow INTEGER;
ALTER TABLE bank_audit_extractions ADD COLUMN rows_equity_change INTEGER;
