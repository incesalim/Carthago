-- 0056_regulation_events
-- The regulation lane: what the rule-makers published, dated, from the
-- primary record.
--
-- WHY: the weekly regulation briefing had no source for the rules themselves.
-- It read press releases and announcements, so when it came to capital-adequacy
-- or credit-card rules it either cited a document it did not hold or invented
-- one, and its own grounding gate stopped it (failed 2026-11-15 and 2026-11-22).
-- These tables hold the primary record instead.
--
-- regulation_events — one row per document from the central bank (TCMB) or the
-- banking regulator (BDDK) in the Resmî Gazete. The Gazette lists every document
-- it publishes with a title, and each document page opens with the date, the
-- issue number, the instrument and the issuing body. event_date is the
-- publication date. summary is the opening of the document's own text and is
-- NULL when the document has no text layer — BDDK board decisions are scanned
-- images, so they carry a title and a link and nothing else. A NULL here means
-- exactly that; it is never an empty string.
--   document_id  Gazette document id with an 'RG-' prefix ('RG-20261127-2')
--   issuer       'TCMB' | 'BDDK'
--   instrument   as printed: TEBLIĞ, GENELGE, YÖNETMELİK, KARAR, ANO …
--   title        the document's title (its own heading, else the listing's)
--   gazette_no   the Resmî Gazete issue number
--
-- tcmb_card_rate_caps — the maximum interest rates TCMB sets for credit-card
-- and overdraft-account transactions, effective-dated, from TCMB's own table.
--   currency     'TL' | 'FX'
--   tier         'statement_under' | 'statement_mid' | 'statement_over' |
--                'cash_withdrawal' | 'all' (the reference rate)
--   rate_kind    'reference' | 'contractual' | 'late_payment'
--   rate         percent per month
--   tier_floor_tl / tier_ceiling_tl — the statement-debt band the tier names.
--        Stored as values because TCMB has moved the thresholds (25,000 →
--        30,000 TL) and a column named "_30k" would have been wrong silently.
--
-- Natural keys: document_id; (period_date, currency, tier, rate_kind). Writers
-- compare before writing, so a re-run that finds nothing new writes nothing.
-- Mirrors src/regulation/schema.py verbatim.

CREATE TABLE IF NOT EXISTS regulation_events (
    document_id TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    issuer      TEXT NOT NULL,
    instrument  TEXT,
    title       TEXT NOT NULL,
    summary     TEXT,
    gazette_no  TEXT,
    source_url  TEXT NOT NULL,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id)
);

CREATE INDEX IF NOT EXISTS idx_regulation_events_date ON regulation_events(event_date);

CREATE TABLE IF NOT EXISTS tcmb_card_rate_caps (
    period_date     TEXT NOT NULL,
    currency        TEXT NOT NULL,
    tier            TEXT NOT NULL,
    rate_kind       TEXT NOT NULL,
    rate            REAL,
    tier_floor_tl   REAL,
    tier_ceiling_tl REAL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period_date, currency, tier, rate_kind)
);
