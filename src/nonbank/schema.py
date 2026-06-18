"""SQLite + D1 schema for the non-bank financial-sector lane.

One aggregate table: the BDDK non-bank monthly bulletin (BultenAylikBdmk)
balance sheet, one row per (sector, period, line item). Mirrors the banking
`balance_sheet` shape but keys on ``sector_code`` instead of bank_type_code.

Amounts are stored **as published — Million TL** (the bulletin's unit); the web
data layer rescales to a common unit before comparing against the banking
aggregate (which is the apples-to-apples denominator for "share of banking").

The D1 migration ``web/migrations/0013_nonbank_sector.sql`` mirrors this DDL
exactly so ``scripts/push_to_d1.py``'s INSERT OR REPLACE conflict-detection
behaves identically.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS nonbank_balance_sheet (
    sector_code   TEXT NOT NULL,      -- leasing|factoring|financing|amc|savings
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,   -- VYŞ/savings report only quarter-end months (3,6,9,12)
    item_order    INTEGER NOT NULL,   -- BDDK 'Sıra' (1..N), stable within a sector
    item_name     TEXT,               -- 'Kalem' verbatim (Turkish, roman-numeral hierarchy)
    is_subtotal   INTEGER,            -- 1 for roman-numeral / TOPLAM lines (heuristic)
    amount_tp     REAL,               -- TP column (Turkish lira), Million TL
    amount_yp     REAL,               -- YP column (foreign currency), Million TL
    amount_total  REAL,               -- Toplam column, Million TL
    source        TEXT DEFAULT 'bddk',-- 'bddk' (bulletin) | 'fkb' (savings-finance fallback)
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sector_code, year, month, item_order)
);
CREATE INDEX IF NOT EXISTS idx_nbbs_sector_period
  ON nonbank_balance_sheet(sector_code, year, month);
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
    print(f"Initialized nonbank_balance_sheet schema in {db}")
