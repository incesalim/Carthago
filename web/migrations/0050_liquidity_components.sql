-- Selected LCR totals; historic rows remain NULL until a scoped repair.
-- Amounts are thousand TRY. Weighted outflows/inflows, capped HQLA/net outflows.
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_hqla_total REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_hqla_fc REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_cash_outflows_total REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_cash_outflows_fc REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_cash_inflows_total REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_cash_inflows_fc REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_net_cash_outflows_total REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_net_cash_outflows_fc REAL;
ALTER TABLE bank_audit_liquidity ADD COLUMN lcr_components_source_json TEXT;
