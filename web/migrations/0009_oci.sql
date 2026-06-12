-- Other Comprehensive Income (OCI) statement table.
-- Single-column format (like P&L): current period amounts only.
-- Follows the P&L page in every BRSA report. Row I. = P&L net, II. = OCI
-- sub-items (2.1 not-recycled / 2.2 recycled with sub-items), III. = total.
CREATE TABLE IF NOT EXISTS bank_audit_oci (
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

CREATE INDEX IF NOT EXISTS idx_bank_oci_bank_period
  ON bank_audit_oci(bank_ticker, period);

-- rows_oci counter in the extractions log (added alongside the OCI extractor).
ALTER TABLE bank_audit_extractions ADD COLUMN rows_oci INTEGER;
