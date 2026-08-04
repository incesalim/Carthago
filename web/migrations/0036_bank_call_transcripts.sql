-- 0036_bank_call_transcripts
-- Earnings-call transcripts for the BIST-listed banks that hold an English call.
-- Source: AlphaSpread's per-quarter call pages (server-rendered HTML; the bank's
-- index page enumerates every call as a '/earnings-call/q<N>-<YYYY>' slug, so the
-- archive discovers itself — see data/banks/call_transcript_sources.json).
--
-- One row per call. Speaker turns live in transcript_json rather than a child
-- table: a call is only ever read whole, and D1 bills rows WRITTEN, so the fat-row
-- shape costs ~1/25th of a per-turn table across the same corpus.
--
-- Three listed banks are absent by source, not by omission: SKBNK and ICBCT hold
-- no English call and QNBFB is delisted. An empty lane for them is correct.
--
-- Quality note carried in the data: these are machine transcriptions. The body is
-- complete (opening through closing remarks incl. Q&A) but attribution is not —
-- the operator naming a Turkish analyst frequently lands as '[indiscernible]',
-- which also leaves the turn untagged as role='analyst'. indiscernible_count makes
-- that measurable per call instead of invisible.
--
-- Powers the call-transcript block on /banks/[ticker] and the reader at
-- /banks/[ticker]/calls/[period]. Kept byte-identical to src/transcripts/schema.py.
-- Idempotent: INSERT OR REPLACE on (source, bank_ticker, period); fetched_at drives
-- push_to_d1's incremental sync (like bank_earnings).

CREATE TABLE IF NOT EXISTS bank_call_transcripts (
    source              TEXT NOT NULL,     -- 'alphaspread' (room for a second transcriber)
    bank_ticker         TEXT NOT NULL,     -- internal code, joins banks.ticker
    period              TEXT NOT NULL,     -- 'YYYYQn' as the source labels the call
    call_date           TEXT,              -- 'YYYY-MM-DD'; NULL when the page omits it
    source_url          TEXT NOT NULL,
    title               TEXT,
    language            TEXT,              -- 'en' (these are the English calls)
    turn_count          INTEGER,           -- speaker turns parsed
    word_count          INTEGER,           -- words across all turns
    speaker_count       INTEGER,           -- distinct named speakers
    analyst_turn_count  INTEGER,           -- turns the source tagged role='analyst'
    indiscernible_count INTEGER,           -- '[indiscernible]' markers — attribution quality
    transcript_json     TEXT NOT NULL,     -- [{seq, speaker, role, text}]
    fetched_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, bank_ticker, period)
);

CREATE INDEX IF NOT EXISTS idx_bank_call_transcripts_bank
  ON bank_call_transcripts(bank_ticker, period DESC);
CREATE INDEX IF NOT EXISTS idx_bank_call_transcripts_date
  ON bank_call_transcripts(call_date DESC);
