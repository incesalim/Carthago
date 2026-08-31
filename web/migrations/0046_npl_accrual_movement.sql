-- NPL interest/profit-share accrual movements are separately disclosed flows,
-- not FX differences. No default: an undisclosed value remains NULL.
ALTER TABLE bank_audit_npl_movement ADD COLUMN accrual_movement REAL;
