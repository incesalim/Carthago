-- Explicit deductions made AFTER Tier 1 + Tier 2 in the BRSA own-funds table.
-- Canonical thousand TRY, like the existing capital amount columns. NULL means
-- not extracted/disclosed; historical rows are deliberately not backfilled.
ALTER TABLE bank_audit_capital ADD COLUMN capital_deductions REAL;
