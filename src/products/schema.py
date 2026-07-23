"""SQLite + D1 schema for the product-shelf benchmark lane.

Three tables, mirroring web/migrations/0034_bank_products.sql verbatim:
  - product_attributes    the 100-attribute catalog (English column labels)
  - bank_products         one row per (bank, attribute, snapshot) — the cell
  - bank_product_profile  per-bank rollup + English prose

Snapshots accrete by snapshot_date (never deleted), like bank_advertised_rates;
downloaded_at drives the incremental push in push_to_d1.py. Evidence rule:
every 'yes'/'partial' carries an evidence_url on the bank's own domain, enforced
in the builder and re-checked by data/product_benchmark/aggregate.py.
"""
from __future__ import annotations

import sqlite3

# Comment-free inside the parens so this stays byte-comparable with the migration
# and scripts/check_schema_naming.py doesn't read a trailing `--` as a column.
DDL = """
CREATE TABLE IF NOT EXISTS product_attributes (
    code            TEXT NOT NULL PRIMARY KEY,
    block           TEXT NOT NULL,
    block_name_en   TEXT NOT NULL,
    label_en        TEXT NOT NULL,
    label_tr        TEXT,
    is_distinctive  INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_products (
    bank_ticker     TEXT NOT NULL,
    attr_code       TEXT NOT NULL,
    value           TEXT NOT NULL,
    note            TEXT,
    evidence_url    TEXT,
    snapshot_date   TEXT NOT NULL,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, attr_code, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_bank_products_attr_value
  ON bank_products(attr_code, value);
CREATE INDEX IF NOT EXISTS idx_bank_products_snapshot
  ON bank_products(snapshot_date);

CREATE TABLE IF NOT EXISTS bank_product_profile (
    bank_ticker     TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    cluster_en      TEXT NOT NULL,
    shelf           REAL NOT NULL,
    coverage        REAL NOT NULL,
    n_yes           INTEGER NOT NULL,
    n_no            INTEGER NOT NULL,
    n_partial       INTEGER NOT NULL,
    n_unknown       INTEGER NOT NULL,
    shelf_notes_en  TEXT,
    distinctive_en  TEXT,
    downloaded_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, snapshot_date)
);
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
    print(f"Initialized product-shelf schema in {db}")
