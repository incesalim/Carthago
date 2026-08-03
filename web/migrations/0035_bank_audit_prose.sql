-- Narrative prose from BRSA audit reports, as item rows.
--
-- Every other bank_audit_* table holds a table the filing prints. This one holds
-- what the filing says: accounting-policy notes, the risk narrative, the
-- review-report explanations, the interim activity report. Roughly half of a
-- filing is prose and none of it has ever been readable outside the PDFs in R2.
--
-- Shaped like a statement's item rows on purpose — (item_order, heading,
-- heading_path, text) is the prose analogue of (item_order, hierarchy,
-- item_name, amount) — so /admin renders it with the same machinery as the
-- tables and the coverage matrix treats it as one more statement type.
--
-- section vs section_role: §6 and §7 SWAP between annual and interim filings
-- (annual: §6 other explanations, §7 audit report; interim: §6 review-report
-- pointer, §7 interim activity report), and ALTERNATİFBANK splits into eight
-- sections. The printed number is therefore not the meaning. `section_role` is
-- read off each filing's own declared title and is what queries must join on.
--
-- Written by src/audit_reports/prose.py — deterministic, fitz-only, no model.
CREATE TABLE IF NOT EXISTS bank_audit_prose (
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    item_order    INTEGER NOT NULL,
    section       INTEGER NOT NULL,
    section_role  TEXT NOT NULL,
    heading       TEXT,
    heading_path  TEXT,
    page_start    INTEGER NOT NULL,
    page_end      INTEGER NOT NULL,
    lang          TEXT NOT NULL,
    text          TEXT NOT NULL,
    char_count    INTEGER NOT NULL,
    extracted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_prose_section
  ON bank_audit_prose(section_role, period);
