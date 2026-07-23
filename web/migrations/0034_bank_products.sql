-- 0034_bank_products
-- Per-bank PRODUCT-SHELF benchmark: which bank offers which products, with every
-- "has it" backed by the bank's own published page.
--
-- WHY: everything else in the pipeline measures what banks EARN (balance sheet,
-- P&L, capital, liquidity). Nothing measured what they SELL. This lane is the
-- input side — the product shelf that feeds those financials. Built by a research
-- pass over each bank's own site (data/product_benchmark/), scored against a fixed
-- 100-attribute taxonomy; the source of truth is data/product_benchmark/*.json,
-- loaded by src/products/build.py.
--
-- Three tables:
--   product_attributes    the 100-attribute catalog (English column labels)
--   bank_products         one row per (bank, attribute, snapshot) — the cell
--   bank_product_profile  per-bank rollup + English prose
--
-- Snapshots accrete by snapshot_date (never deleted), mirroring bank_advertised_rates:
-- product shelves move slowly and the sources only ever expose "today", so history
-- builds forward. Synced by push_to_d1.py on downloaded_at. Mirrors src/products/schema.py.
--
-- Evidence rule (enforced in the builder + aggregate.py QC): every value of
-- 'yes'/'partial' carries an evidence_url on the bank's OWN domain, or it is not
-- 'yes'. 'no' = category page checked, product absent (a fact about the BANK).
-- 'unknown' = we could not verify (a fact about US, not a gap in the bank).
--
-- Columns — product_attributes:
--   code           'A01'..'J08' (block letter + ordinal)
--   block          'A'..'J'
--   block_name_en  English block name ('Deposits & savings', ...)
--   label_en       English attribute label (the column header)
--   label_tr       Turkish source label (provenance)
--   is_distinctive 1 if this attribute discriminates banks (not a table-stakes line)
--   sort_order     stable display order (matches the taxonomy)
--
-- Columns — bank_products:
--   bank_ticker    banks.ticker
--   attr_code      product_attributes.code
--   value          'yes' | 'partial' | 'no' | 'unknown'
--   note           Turkish source note (provenance; the English page does not print it)
--   evidence_url   the bank's own page backing the value (required for yes/partial)
--   snapshot_date  'YYYY-MM-DD' capture day
--
-- Columns — bank_product_profile:
--   cluster_en     benchmark peer cluster ('State deposit', 'Large private', ...)
--   shelf          verified shelf breadth = (yes + 0.5*partial) / verified, verified = yes+no+partial
--   coverage       evidence coverage = verified / 100  (how much we could verify — about US)
--   n_yes/n_no/n_partial/n_unknown  cell counts over the 100 attributes
--   shelf_notes_en English 2-4 sentence shelf summary
--   distinctive_en JSON array of English "what sets this shelf apart" lines

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
