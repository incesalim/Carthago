-- Structural-validation results for extracted BRSA statements
-- (src/audit_reports/validator.py; docs/AUDIT_REWORK_PLAN.md Phase 1).
-- statement: 'assets' | 'liabilities' | 'cross'.
CREATE TABLE IF NOT EXISTS bank_audit_validation (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    statement      TEXT NOT NULL,
    checks_passed  INTEGER NOT NULL DEFAULT 0,
    checks_failed  INTEGER NOT NULL DEFAULT 0,
    checks_skipped INTEGER NOT NULL DEFAULT 0,
    failed_detail  TEXT,
    validated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, statement)
);

CREATE INDEX IF NOT EXISTS idx_bank_validation_failed
  ON bank_audit_validation(checks_failed);
