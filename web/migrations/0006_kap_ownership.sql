-- KAP ownership-structure lane (kap.org.tr Genel Bilgi Formu §5).
-- One row per shareholder grid line / free-float line / capital scalar.
-- Populated weekly by scripts/update_kap_ownership.py via push_to_d1.py;
-- each run fully replaces a bank's partition (stale keys are deleted via
-- the d1_pending_deletes outbox in the staging DB).

CREATE TABLE IF NOT EXISTS kap_ownership (
    bank_ticker    TEXT NOT NULL,
    bank_name      TEXT NOT NULL,
    kap_company_id INTEGER NOT NULL,
    item           TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    holder         TEXT,
    share_tl       REAL,
    ratio_pct      REAL,
    voting_pct     REAL,
    as_of          TEXT,
    downloaded_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, item, seq)
);

CREATE INDEX IF NOT EXISTS idx_kap_ownership_item
  ON kap_ownership(item, bank_ticker);
