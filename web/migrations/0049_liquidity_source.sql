-- Existing rows remain NULL and keep extracted_at. Populate only when their
-- exact filing is re-read; no fleet-wide restamping or invented prior values.
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_source_json TEXT;
