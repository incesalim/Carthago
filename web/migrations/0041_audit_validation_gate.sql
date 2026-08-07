-- 0041_audit_validation_gate
--
-- Expose the validator dependency graph to D1 consumers. Coverage, targeted
-- repair and overwrite protection already require every result in this gate;
-- the admin drawer and future alerts need the same names so they can explain
-- which related check made a lane fail.

ALTER TABLE bank_audit_statement_types
  ADD COLUMN validation_gate TEXT NOT NULL DEFAULT '';

-- Free provision is conditional, not unvalidated. A missing row is normally
-- N/A, but a modified audit-opinion basis that names the reserve proves a
-- recall failure. sync_audit_expected.py rebuilds these rows from the registry;
-- this backfill keeps deploy-time D1 correct before the next audit refresh.
UPDATE bank_audit_statement_types
   SET has_validator = 1
 WHERE key = 'free_provision';

UPDATE bank_audit_statement_types
   SET validation_gate = CASE key
     WHEN 'balance_sheet_assets' THEN 'assets,liabilities,cross'
     WHEN 'balance_sheet_liabilities' THEN 'assets,liabilities,cross'
     WHEN 'other_comprehensive_income' THEN 'oci'
     WHEN 'credit_quality' THEN 'credit_quality,stages'
     WHEN 'stages' THEN 'credit_quality,stages'
     WHEN 'profile' THEN 'profile'
     WHEN 'audit_opinion' THEN 'audit_opinion'
     WHEN 'free_provision' THEN 'free_provision'
     ELSE key
   END
 WHERE has_validator = 1;
