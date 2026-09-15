# `src/tkbb/` — participation-bank digital + acquisition stats

TKBB (participation banks association) digital-banking stats via the Turboard
JSON API, plus remote-vs-branch acquisition.

- `turboard.py` — Turboard API client; `digital.py` / `acquisition.py` — the two
  lanes; `loader.py` / `schema.py` — local persistence.

**Entry points:** `scripts/update_tkbb_digital.py`,
`scripts/update_tkbb_acquisition.py` (both via `scripts/refresh.py`).

**Writes:** `tkbb_digital_stats`, `tkbb_acquisition_stats`.