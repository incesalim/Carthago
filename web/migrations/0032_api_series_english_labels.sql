-- English labels for the public API's series catalog.
--
-- Exists because the BDDK bulletin tables are filed in Turkish, so api_series
-- shipped with Turkish-only item_name — and /serieList?q= therefore returned
-- ZERO hits for "loans", "deposits" or "total assets". An API whose search only
-- answers to the language the filer used is unusable by most of the people an
-- API is for, and it forced any LLM client to be handed a hardcoded code table.
--
-- These are BDDK's OWN English labels, not a translation: the monthly endpoint
-- serves the same rows in the same order under .../BultenAylik/en/..., verified
-- across all 17 tables. That matters for regulatory line items, where an
-- invented rendering would quietly misname a supervisory concept.
-- scripts/fetch_bddk_english_labels.py caches them; the catalog builder joins
-- them on (table_number, item_order).
--
-- NULL is meaningful: it means BDDK publishes no English for that line. The
-- weekly bulletin datasets (WLOAN/WSEC/WDEP/WNPL/WOBS/WBAL/WFX) have no English
-- source at all, so they are NULL throughout and consumers fall back to
-- item_name. Do NOT backfill this column with a machine translation.
ALTER TABLE api_series ADD COLUMN item_name_en TEXT;

-- /serieList?q= searches both languages; the Turkish index already exists.
CREATE INDEX IF NOT EXISTS idx_api_series_item_name_en
  ON api_series(item_name_en);
