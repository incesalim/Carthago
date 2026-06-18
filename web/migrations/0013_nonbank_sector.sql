-- 0013_nonbank_sector
-- BDDK non-bank financial-sector bulletin (BultenAylikBdmk) — aggregate sector
-- balance sheets for the BDDK-supervised non-bank institutions:
--   leasing | factoring | financing | amc (VYŞ asset management).
-- Sibling of the banking monthly bulletin (balance_sheet); keyed on sector_code
-- instead of bank_type_code. Powers the /non-bank tab — "how much of banking
-- business is done by non-banks" — with the in-D1 banking aggregate
-- (balance_sheet, bank_type_code=10001) as the same-source denominator.
--
-- Amounts are stored AS PUBLISHED (Million TL); the web data layer normalizes
-- to a common unit before computing any share ratio. Idempotent: INSERT OR
-- REPLACE on the composite primary key, so push_to_d1's sync behaves identically.

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
