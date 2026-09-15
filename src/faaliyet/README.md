# `src/faaliyet/` — annual-report franchise stats

Franchise statistics parsed from bank annual reports (Faaliyet Raporu PDFs).

- `client.py` — acquisition; `extractor.py` — PyMuPDF (`fitz`) extraction;
  `r2_storage.py`; `loader.py` / `schema.py`.

**Entry points:** `scripts/update_faaliyet.py`, `backfill-faaliyet.yml`.

**Writes:** `faaliyet_franchise`, `faaliyet_extractions`.

> Deliberately a separate extractor from `audit_reports/`, but bound by the same
> fitz-only rule.