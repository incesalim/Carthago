-- These metadata counters already exist on some deployments through the retired
-- auto-ensure helper. reconcile_schema.py verifies/adopts exactly this migration
-- before Wrangler applies remaining files; a fresh DB applies both statements.
ALTER TABLE bank_audit_extractions ADD COLUMN rows_fx_position INTEGER;
ALTER TABLE bank_audit_extractions ADD COLUMN rows_repricing INTEGER;
