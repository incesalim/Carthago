# `src/tuik/` — TÜİK detail series

TÜİK veriportali data for detail series EVDS does not publish (GDP expenditure,
PPI MIG), stored under `TUIK.*` codes.

- `client.py` — cookie-session `.xls` download; `parser.py` — tidy rows.

**Entry point:** `scripts/update_tuik.py` (via `scripts/refresh.py`).

**Writes:** `evds_series` (as `TUIK.*`).