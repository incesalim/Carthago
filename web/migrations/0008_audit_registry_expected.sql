-- Coverage spine for the /admin audit coverage matrix
-- (scripts/sync_audit_expected.py; src/audit_reports/registry.py).
-- Three tables, all rebuilt wholesale by the sync (DELETE + INSERT) — IF NOT
-- EXISTS here is the create-once guard; the sync owns the rows.
-- Mirrored in src/audit_reports/schema.py.

-- The EXPECTED universe: one row per (bank, period, kind) the corpus should
-- hold (from data/audit_profiles.json), overlaid with whether the PDF is in R2.
CREATE TABLE IF NOT EXISTS bank_audit_expected (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    bank_type      TEXT,
    language       TEXT,
    equity_numeral TEXT,
    pdf_present    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bank_ticker, period, kind)
);

-- The statement-type registry mirrored from registry.web_metadata().
CREATE TABLE IF NOT EXISTS bank_audit_statement_types (
    key           TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    source_table  TEXT NOT NULL,
    statement     TEXT,
    is_core       INTEGER NOT NULL DEFAULT 0,
    has_validator INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

-- Precomputed coverage rollup: one row per (bank, period, kind, statement_type).
-- status: 'not_expected' | 'missing' | 'error' | 'manual' | 'ok'.
CREATE TABLE IF NOT EXISTS bank_audit_coverage (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    status         TEXT NOT NULL,
    row_count      INTEGER NOT NULL DEFAULT 0,
    checks_failed  INTEGER NOT NULL DEFAULT 0,
    is_manual      INTEGER NOT NULL DEFAULT 0,
    pdf_present    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bank_ticker, period, kind, statement_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_coverage_status
  ON bank_audit_coverage(status);
CREATE INDEX IF NOT EXISTS idx_bank_coverage_type_kind
  ON bank_audit_coverage(statement_type, kind);
