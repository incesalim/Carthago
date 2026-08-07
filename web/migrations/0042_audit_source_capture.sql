-- Source-completeness footprint for intentionally normalized/summary audit
-- tables.  Raw source lines stay in the local/R2 SQLite snapshot; D1 receives
-- one compact row per filing/lane for validation, admin health and alerts.
CREATE TABLE IF NOT EXISTS bank_audit_capture_manifest (
    bank_ticker               TEXT NOT NULL,
    period                    TEXT NOT NULL,
    kind                      TEXT NOT NULL,
    statement_type            TEXT NOT NULL,
    capture_scope             TEXT NOT NULL,
    source_pages_json         TEXT NOT NULL DEFAULT '[]',
    source_page_count         INTEGER NOT NULL DEFAULT 0,
    source_line_count         INTEGER NOT NULL DEFAULT 0,
    source_numeric_line_count INTEGER NOT NULL DEFAULT 0,
    source_data_row_count     INTEGER NOT NULL DEFAULT 0,
    mapped_data_row_count     INTEGER NOT NULL DEFAULT 0,
    unmapped_data_row_count   INTEGER NOT NULL DEFAULT 0,
    normalized_row_count      INTEGER NOT NULL DEFAULT 0,
    content_hash              TEXT NOT NULL,
    shape_hash                TEXT NOT NULL,
    mapping_hash              TEXT NOT NULL,
    capture_status            TEXT NOT NULL,
    extracted_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, statement_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_capture_manifest_status
  ON bank_audit_capture_manifest(statement_type, capture_status);
