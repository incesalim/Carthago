# `src/scrapers/` — BDDK bulletins + TCMB EVDS

Acquires the sector aggregates that form the bulletin/macro lane.

- `bddk_api_scraper.py` / `bddk_probe.py` — BDDK monthly bulletin API.
- `weekly_api_scraper.py` — BDDK weekly bulletin.
- `evds_client.py` — TCMB EVDS v3 HTTP client; `evds_scraper.py` — series refresh.
- `_http.py` — shared retry/session helper.

**Entry points:** `scripts/update_monthly.py`, `scripts/update_weekly.py`,
orchestrated by `scripts/refresh.py`; EVDS additionally by
`refresh-evds-daily.yml`.

**Writes:** `balance_sheet`, `income_statement`, `loans`, `deposits`,
`financial_ratios`, `other_data`, `weekly_series`, `evds_series`.

See [`docs/SYSTEM_MAP.md`](../../docs/SYSTEM_MAP.md) §2 for the lane model.