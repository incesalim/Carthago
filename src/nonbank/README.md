# `src/nonbank/` — non-bank lenders

BDDK non-bank monthly bulletin (leasing, factoring, financing companies).

- `scraper.py` — bulletin acquisition/parse; `schema.py` — tables.

**Entry points:** `scripts/update_nonbank.py` (via `scripts/refresh.py`),
`backfill-nonbank.yml`.

**Writes:** `nonbank_balance_sheet`.