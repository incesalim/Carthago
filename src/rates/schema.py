"""SQLite + D1 schema for the advertised-rates lane.

One tidy long table, mirroring web/migrations/0023_bank_advertised_rates.sql
verbatim. Values are stored in the RAW units the source publishes:
  - loans  → MONTHLY % (how TR banks quote consumer/mortgage/vehicle loans)
  - deposits → ANNUAL % (how TR banks quote time deposits)
`rate_basis` records which, so the web layer never has to guess.

Two shapes share the table:
  - a POINT rate  (loans): `rate` set, `rate_min`/`rate_max` NULL.
  - a rate BAND   (deposits): `rate_min`/`rate_max` set, `rate` NULL — the
    aggregator publishes each bank's min–max advertised band across terms.

Natural key is (source, rate_type, raw_bank_name, product_name, currency,
snapshot_date): `raw_bank_name` (always present) rather than `bank_ticker`
(nullable — non-audited brands resolve to NULL), and `snapshot_date` so a new
snapshot accretes history instead of overwriting. Idempotent within a day.
"""
from __future__ import annotations

import sqlite3

# Column semantics are documented in web/migrations/0023_bank_advertised_rates.sql.
# Kept comment-free inside the parens so both sides stay byte-comparable (and so
# scripts/check_schema_naming.py doesn't read a trailing `--` as a column name).
DDL = """
CREATE TABLE IF NOT EXISTS bank_advertised_rates (
    source          TEXT NOT NULL,
    rate_type       TEXT NOT NULL,
    raw_bank_name   TEXT NOT NULL,
    bank_ticker     TEXT,
    product_name    TEXT NOT NULL DEFAULT '',
    currency        TEXT NOT NULL DEFAULT 'TRY',
    rate            REAL,
    rate_min        REAL,
    rate_max        REAL,
    rate_basis      TEXT NOT NULL,
    term_min        INTEGER,
    term_max        INTEGER,
    term_unit       TEXT,
    amount_min      REAL,
    amount_max      REAL,
    snapshot_date   TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, rate_type, raw_bank_name, product_name, currency, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_adv_rates_type_bank
  ON bank_advertised_rates(rate_type, bank_ticker);
CREATE INDEX IF NOT EXISTS idx_adv_rates_snapshot
  ON bank_advertised_rates(snapshot_date);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/bddk_data.db")
    with sqlite3.connect(db) as conn:
        init_schema(conn)
    print(f"Initialized bank_advertised_rates schema in {db}")
