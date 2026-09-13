-- Signed Other movements include disclosed reclassifications to non-defaulted
-- status. Keep them separate from sales, FX and interest/profit-share accruals.
-- No default: absence of a separately disclosed row remains NULL.
ALTER TABLE bank_audit_npl_movement ADD COLUMN other_movement REAL;
