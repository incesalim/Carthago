-- Full-document table capture — compact per-filing footprint.
--
-- The capture itself records every table a filing prints (rows, columns, cells)
-- plus the footnotes that qualify them, linked to the rows carrying their
-- marker. That raw ledger is 5.4M lines and 11.2M cells across the corpus, so
-- it lives ONLY in data/bank_audit_capture.db and the per-partition JSONL
-- export — never here, because written rows are D1's cost centre.
--
-- What reaches D1 is one row per (bank, period, kind): how much was captured,
-- and three content-addressed hashes.
--   content_hash  every captured line — changes when any printed text changes
--   shape_hash    the same lines with values masked — changes when the TEMPLATE
--                 changes even though the figures did not
--   grid_hash     block/column/row geometry — changes when a filer restructures
--                 a table, which is the signal a lane parser is about to break
--
-- The writer leaves an unchanged row untouched, so routine refreshes do not
-- re-bill identical rows.
CREATE TABLE IF NOT EXISTS bank_audit_document_manifest (
    bank_ticker       TEXT NOT NULL,
    period            TEXT NOT NULL,
    kind              TEXT NOT NULL,
    page_count        INTEGER NOT NULL DEFAULT 0,
    table_page_count  INTEGER NOT NULL DEFAULT 0,
    block_count       INTEGER NOT NULL DEFAULT 0,
    line_count        INTEGER NOT NULL DEFAULT 0,
    cell_count        INTEGER NOT NULL DEFAULT 0,
    note_count        INTEGER NOT NULL DEFAULT 0,
    linked_note_count INTEGER NOT NULL DEFAULT 0,
    -- Pages whose TABLES are drawn as vector outlines rather than typed. They
    -- are perfectly legible on screen and unreadable to any extractor, so none
    -- of their rows are in the capture. Fibabanka prints its statements this
    -- way — 39 of 92 pages in 2022Q1, the balance sheet among them. Recorded
    -- because the alternative is a filing that reports "13 tables, 71 rows" and
    -- reads as a small bank rather than as a hole in the data.
    vector_page_count INTEGER NOT NULL DEFAULT 0,
    content_hash      TEXT NOT NULL,
    shape_hash        TEXT NOT NULL,
    grid_hash         TEXT NOT NULL,
    -- 'captured' | 'partial' (some pages drawn) | 'unreadable' (no text at all)
    capture_status    TEXT NOT NULL,
    captured_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_doc_manifest_status
  ON bank_audit_document_manifest(capture_status);
