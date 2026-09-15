# `src/tefas/` — fund market

TEFAS fund-market data (rate-limited tefas.gov.tr JSON client). Per-fund rows
are not persisted; the lane stores per-day sector aggregates.

- `client.py` — rate-limited JSON client; `normalize.py` — fund taxonomy;
  `aggregate.py` — sector rollups; `loader.py` / `schema.py` — persistence.

**Entry points:** `scripts/update_tefas.py` (via `scripts/refresh.py`),
`backfill-tefas.yml`.

**Writes:** `tefas_manager_daily`, `tefas_category_daily`,
`tefas_allocation_daily`, `tefas_top_funds`.