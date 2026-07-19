-- The public API's series catalog: one row per addressable time series in the
-- BDDK monthly (tables 1-17) and weekly datasets, keyed by a stable dotted code
-- (`BDDK.T01.I005.10001.TOT`) modelled on EVDS's `TP.DK.USD.A`.
--
-- Exists because our BDDK tables are stored LONG (period x dimension x item),
-- not as series: there is no column anywhere that holds "the series this row
-- belongs to". A caller asking for one line of the balance sheet over six years
-- is really asking for a (source_table, table_number, currency, bank_type_code,
-- item, value_column) tuple held fixed while year/month vary. This table names
-- those tuples so they can be requested by a short code, listed by /serieList,
-- and carry a unit + display name that the raw rows don't have.
--
-- STABILITY IS THE WHOLE POINT. Once a code is published a caller may hardcode
-- it forever, so scripts/build_api_catalog.py MUST re-derive an existing code's
-- meaning rather than re-assign it: it carries existing item slots forward and
-- only allocates a new one for a genuinely new item. Never renumber in bulk.
--
-- Column notes (kept out of the table body because check_schema_naming.py splits
-- that body on commas without stripping comments, so a comma in a trailing
-- comment invents a bogus column name):
--   series_code     BDDK.<DATASET>.<I###>.<BANKTYPE>.<COL>
--   dataset         T01..T17 monthly; WLOAN/WSEC/WDEP/WNPL/WOBS/WBAL/WFX weekly
--   source_table    balance_sheet | income_statement | loans | deposits
--                   | financial_ratios | other_data | weekly_series
--   table_number    BDDK's own monthly table number; NULL for weekly
--   category        weekly bulletin section; NULL for monthly
--   item_key        the REAL filter value: item_order for the monthly statement
--                   tables; item_name for other_data (its item_order COLLIDES
--                   inside table 12); the dotted outline id for weekly
--   item_name       display label as filed - Turkish or English
--   bank_type_code  BDDK ownership/type code; joins bank_types(code)
--   report_currency reporting basis for monthly rows; NULL for weekly
--   value_column    physical column to read; for weekly it is the currency leg
--   unit            million TL | thousand TL | percentage | count
--
-- The I### token in the CODE is a catalog-assigned slot for other_data and a
-- direct rendering of the source key elsewhere. Either way resolution ALWAYS
-- goes through this row - never parse a code into SQL.
CREATE TABLE IF NOT EXISTS api_series (
    series_code     TEXT PRIMARY KEY,
    dataset         TEXT NOT NULL,
    frequency       TEXT NOT NULL,
    source_table    TEXT NOT NULL,
    table_number    INTEGER,
    category        TEXT,
    item_key        TEXT NOT NULL,
    item_name       TEXT NOT NULL,
    bank_type_code  TEXT NOT NULL,
    report_currency TEXT,
    value_column    TEXT NOT NULL,
    unit            TEXT,
    start_date      TEXT,
    end_date        TEXT,
    obs_count       INTEGER,
    built_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- /serieList filters by dataset and by bank type; both are low-cardinality.
CREATE INDEX IF NOT EXISTS idx_api_series_dataset
  ON api_series(dataset);
CREATE INDEX IF NOT EXISTS idx_api_series_bank_type
  ON api_series(bank_type_code);
-- Substring search over labels in /serieList?q=
CREATE INDEX IF NOT EXISTS idx_api_series_item_name
  ON api_series(item_name);
