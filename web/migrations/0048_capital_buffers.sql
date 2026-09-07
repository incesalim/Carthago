-- Add source-disclosed buffer percentages to the existing capital summary.
-- Historical values remain NULL until an explicitly scoped extraction.
-- Ratios are percentage points, never scaled by the report's monetary unit.
ALTER TABLE bank_audit_capital ADD COLUMN total_buffer_requirement_ratio REAL;
ALTER TABLE bank_audit_capital ADD COLUMN capital_conservation_buffer_ratio REAL;
ALTER TABLE bank_audit_capital ADD COLUMN countercyclical_buffer_ratio REAL;
ALTER TABLE bank_audit_capital ADD COLUMN systemic_buffer_ratio REAL;
ALTER TABLE bank_audit_capital ADD COLUMN cet1_available_buffer_ratio REAL;
ALTER TABLE bank_audit_capital ADD COLUMN buffer_source_json TEXT;
