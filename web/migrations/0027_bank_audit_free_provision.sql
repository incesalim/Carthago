-- 0027_bank_audit_free_provision
-- The free provision (serbest karşılık): a bank's discretionary "rainy-day"
-- reserve, set aside from profit OUTSIDE the BRSA provisioning rules.
--
-- WHY: this is the number behind the ALBRK Q1-2025 case — auditors qualify over
-- it (bank_audit_opinion), and releasing it flows straight into profit. We had it
-- nowhere: it lives only in the "Other provisions" liability note, never in a
-- statement we extract. A first sweep shows it is widely held and volatile —
-- ALBRK ₺7.3bn→₺0.3bn, VAKBN ₺15bn→₺4bn, ZIRAAT ₺9bn, QNBFB ₺6.6bn — the raw
-- material for a "quality of earnings" screen.
--
-- Columns:
--   free_provision        current-period STOCK, thousand TL; 0 = bank holds none
--   free_provision_prior  prior-period (Dec 31) stock from the note's parenthetical
--                         comparison — best-effort, may be NULL
--   source_text           the matched sentence, for verification
--
-- One row per (bank, period, kind). Only DISCLOSED rows are written: a row with
-- free_provision=0 means the bank explicitly disclosed "none"; a MISSING row means
-- no disclosure was found. Mirrors the bank_audit_free_provision block in
-- src/audit_reports/schema.py; classified by src/audit_reports/free_provision.py
-- (deterministic, fitz-only); synced by push_to_d1.py (--table-set audit) on
-- extracted_at.

CREATE TABLE IF NOT EXISTS bank_audit_free_provision (
    bank_ticker          TEXT NOT NULL,
    period               TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    free_provision       REAL,
    free_provision_prior REAL,
    source_page          INTEGER,
    source_text          TEXT,
    extracted_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_bank_freeprov_bank_period
  ON bank_audit_free_provision(bank_ticker, period);
