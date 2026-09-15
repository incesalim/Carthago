# `src/tbb/` — Banks Association of Türkiye stats

TBB quarterly digital-banking workbooks and monthly remote-vs-branch
customer-acquisition stats.

- `client.py` — TBB download; `parser.py` — workbook → tidy rows.
- `acquisition.py` — monthly acquisition stats.
- `loader.py` / `schema.py` — local persistence.

**Entry points:** `scripts/update_tbb_digital.py`,
`scripts/update_tbb_acquisition.py` (both via `scripts/refresh.py`).

**Writes:** `tbb_digital_stats`, `tbb_acquisition_stats`.