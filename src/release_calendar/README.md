# `src/release_calendar/` — TCMB release calendar

TCMB's published calendar (MPC decisions/minutes, Inflation Report, Financial
Stability Report), which feeds the dashboard "Ahead" strips and replaces the
hand-typed `MPC_DATES` fallback.

- `scraper.py` — fetch + parse; `schema.py` — table. Runs as a module.

**Entry point:** `python -m src.release_calendar.scraper`
(`refresh-calendar.yml`, 1st of month 06:00 UTC).

**Writes:** `release_calendar`.
`scripts/check_calendar_fresh.py` keeps the hand-typed fallback ≥ 90 days ahead.