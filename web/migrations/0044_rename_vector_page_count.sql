-- vector_page_count → unreadable_page_count.
--
-- The column counted pages whose tables are drawn as vector glyph outlines
-- (Fibabanka). On 2026-08-19 a second mechanism with the same consequence was
-- measured: statement BODIES embedded as raster images under a typed banner —
-- İş Bankası 2025Q1 consolidated and 2025Q2 unconsolidated, Fibabanka 2023Q3
-- consolidated. Zero path ink, so the vector probe scored them 'text' and the
-- capture silently recorded 3 cells per statement page; only the reconcile
-- check saw the hole (19% / 61% / 92%). The probe now detects both, the
-- per-page ledger keeps them apart ('vector' | 'raster'), and this column
-- carries their sum — pages whose content is not machine-readable text, by
-- either route. The old name would have under-promised what it counts.
--
-- The table is empty in D1 at migration time (the manifest backfill was never
-- dispatched), so this renames no data.
ALTER TABLE bank_audit_document_manifest
  RENAME COLUMN vector_page_count TO unreadable_page_count;
