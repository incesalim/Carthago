-- Add Stage 1 (performing loans) column to loans_by_sector.
-- Additive, nullable: existing rows keep stage1_amount = NULL.
-- Captures the 4-column layout (Stage 1 / Stage 2 / Stage 3 / ECL)
-- that some banks print in their sector-level IFRS-9 disclosure.
ALTER TABLE bank_audit_loans_by_sector ADD COLUMN stage1_amount REAL;
