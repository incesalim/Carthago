# `src/` — source domains

Python ingestion + extraction code. **One package per data lane.** A package
owns the source client, parser/extractor and the local `schema.py` for its
tables; a thin CLI in `../scripts/` drives it. For the pipeline shape see
[`docs/SYSTEM_MAP.md`](../docs/SYSTEM_MAP.md); for the scripts see
[`scripts/ORGANIZATION.md`](../scripts/ORGANIZATION.md).

## Package catalog

| Package | Owns | Entry scripts | D1 tables |
|---|---|---|---|
| [`scrapers/`](scrapers/) | BDDK monthly+weekly bulletins, TCMB EVDS client | `refresh.py`, `update_monthly.py`, `update_weekly.py` | `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data`, `weekly_series`, `evds_series` |
| [`audit_reports/`](audit_reports/) | Per-bank BRSA PDF → rows; document corpus | `sync_audit_reports.py`, `reextract_statement.py`, `sync_audit_expected.py` | all `bank_audit_*` |
| [`tbb/`](tbb/) | TBB digital-banking + acquisition | `update_tbb_digital.py`, `update_tbb_acquisition.py` | `tbb_digital_stats`, `tbb_acquisition_stats` |
| [`tkbb/`](tkbb/) | TKBB participation digital + acquisition | `update_tkbb_digital.py`, `update_tkbb_acquisition.py` | `tkbb_digital_stats`, `tkbb_acquisition_stats` |
| [`kap/`](kap/) | KAP ownership form | `update_kap_ownership.py` | `kap_ownership` |
| [`tefas/`](tefas/) | TEFAS fund market | `update_tefas.py` | `tefas_*` |
| [`tuik/`](tuik/) | TÜİK detail series | `update_tuik.py` | `evds_series` (`TUIK.*`) |
| [`news/`](news/) | News feeds, regulation briefing, "The Read" | `sync_news.py`, `summarize_regulations.py`, `generate_read_headlines.py` | `news_items`, `news_item_banks`, `regulation_briefings`, `read_headlines` |
| [`earnings/`](earnings/) | Results calendar + IR decks | `update_presentations.py` | `bank_earnings` |
| [`transcripts/`](transcripts/) | Earnings-call transcripts | `update_transcripts.py` | `bank_call_transcripts` |
| [`faaliyet/`](faaliyet/) | Annual-report franchise stats | `update_faaliyet.py` | `faaliyet_franchise`, `faaliyet_extractions` |
| [`nonbank/`](nonbank/) | Non-bank monthly bulletin | `update_nonbank.py` | `nonbank_balance_sheet` |
| [`rates/`](rates/) | Posted loan/deposit rates | `python -m src.rates.scraper` | `bank_advertised_rates` |
| [`release_calendar/`](release_calendar/) | TCMB release calendar | `python -m src.release_calendar.scraper` | `release_calendar` |
| [`products/`](products/) | Product-shelf benchmark | `python -m src.products.build` | `product_attributes`, `bank_products`, `bank_product_profile` |
| [`analyst/`](analyst/) | Deterministic detectors | `scripts/analyst/detect.py` | `analyst_signals`, `analyst_basis_metadata`, `analyst_notes` |
| `d1_usage.py` | D1 billing-cycle usage reader (not a lane) | by hand | — |

## Conventions

- **`schema.py`** in each package declares its local SQLite tables; D1 serving
  schema is hand-authored in `web/migrations/` and is the single source of truth.
- **`loader.py`** is the usual local-persistence seam; `client.py` / `scraper.py`
  / `parser.py` are the source-facing pieces.
- **`null` is not `0`.** A disclosure never made and a real zero are different
  facts; every layer keeps them apart.
- **PDF extraction is PyMuPDF (`fitz`) only** (`audit_reports/`, `faaliyet/`).
  `pdfplumber` is banned and CI enforces it.