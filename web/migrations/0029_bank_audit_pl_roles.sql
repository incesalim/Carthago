-- Per-row semantic tags for the income statement: which row IS the period-net,
-- the gross operating profit, the two opex lines, etc. — resolved against the
-- FILER'S OWN roman numbering by validator.pl_roles() and rebuilt from stored
-- rows by scripts/revalidate_audit_db.py (no re-extraction).
--
-- Exists because the BRSA roman ordinals are NOT fixed across the corpus: the
-- compressed template some participation banks file puts net-operating at XII
-- and period-net at XXIV, not XIII/XXV. A SQL consumer that hardcodes an ordinal
-- silently reads the wrong LINE — heatmap.ts's `COALESCE(XXV., XIX.)` reported
-- DUNYAK's net profit as 0 for six quarters (it fell through to XIX =
-- discontinued-ops income, which is nil) and its `XI. + XII.` summed other-opex
-- plus net operating PROFIT as "opex". Consumers join here instead of guessing,
-- so the resolution lives in exactly one place — the Python side, which has the
-- Turkish fold that SQL's ASCII-only UPPER() lacks.
--
-- Mirrors src/audit_reports/schema.py. Roles: gross, net_op, pretax, tax,
-- cont_net, disc_net, period_net, opex_personnel, opex_other.
CREATE TABLE IF NOT EXISTS bank_audit_pl_roles (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    hierarchy   TEXT NOT NULL,
    role        TEXT NOT NULL,
    derived_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, hierarchy)
);

CREATE INDEX IF NOT EXISTS idx_bank_pl_roles_role
  ON bank_audit_pl_roles(role);
