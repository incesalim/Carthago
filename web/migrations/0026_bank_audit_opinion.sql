-- 0026_bank_audit_opinion
-- The independent auditor's verdict, classified from the auditor's report at the
-- front of every BRSA filing (src/audit_reports/audit_opinion.py).
--
-- WHY: the pipeline read every number a bank reported but never whether its own
-- auditor stood behind them. That blind spot is what let ALBRK's Q1-2025 "record
-- profit" pass unremarked — PwC had QUALIFIED the accounts over a ₺7bn free-
-- provision reversal, and we had no field to see it. A modified opinion is
-- strictly more informative than any ratio computed from the same numbers: the
-- person paid to verify them is telling you not to. (A first sweep already finds
-- ISCTR, HALKB and VAKBN carrying modified opinions too — several over the same
-- free-provision practice — all previously invisible.)
--
-- Columns:
--   opinion_type  'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'unknown'
--   is_modified   1 when qualified/adverse/disclaimer — the flag the UI keys on
--   report_kind   'audit' (annual, full opinion) | 'review' (interim, limited)
--   basis_text    the "Basis for Qualified/Adverse …" paragraph (NULL if clean)
--   auditor       canonical firm brand (PwC/KPMG/EY/Deloitte/…), best-effort
--   language      'en' | 'tr'
--   source_page   0-indexed page the opinion heading sat on
--
-- One row per (bank_ticker, period, kind). 'unknown' rows are never written, so a
-- failed re-extract can't overwrite a stored verdict. Mirrors the
-- bank_audit_opinion block in src/audit_reports/schema.py; synced by
-- push_to_d1.py (--table-set audit, via registry.AUDIT_TABLES) on extracted_at.

CREATE TABLE IF NOT EXISTS bank_audit_opinion (
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    opinion_type  TEXT NOT NULL,
    is_modified   INTEGER NOT NULL DEFAULT 0,
    report_kind   TEXT,
    basis_text    TEXT,
    auditor       TEXT,
    language      TEXT,
    source_page   INTEGER,
    extracted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_bank_opinion_modified
  ON bank_audit_opinion(is_modified);
