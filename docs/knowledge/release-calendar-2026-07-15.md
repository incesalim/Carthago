# Release calendar — the Ahead strips fill themselves

**Date:** 2026-07-15 · **Status:** ✅ SHIPPED (v1: TCMB scraped + BDDK/BRSA/earnings derived)

## What prompted it

The "Ahead" strips (homepage + `/deposits` `/capital` `/liquidity` `/profitability`) are the site's calendar — "what lands next." They'd already been converted from hand-typed placeholders to *derived* rows (BDDK monthly/weekly, BRSA filing windows), but still leaned on one hand-transcribed artefact — `MPC_DATES` in `web/app/lib/ahead.ts` — and were thin: four cadence rows, when TCMB actually publishes a richer calendar.

The user's ask: make the strips a real, automated release calendar. Scope, after clarifying: **enrich the existing strips (no new `/calendar` page)** and **banking backbone only** (TÜİK macro-data releases deferred — that source is a JS SPA behind auth).

## What shipped

**One scraper retires the hand-typed dates and adds three event types.** TCMB publishes its "Monetary Policy Committee Meeting and Reports Calendar" as one HTML `<table>` — four columns: MPC Decision · Summary of the MPC Meeting (minutes) · Inflation Report · Financial Stability Report, cells in "Month D, YYYY" form.

- **`src/release_calendar/scraper.py`** — `requests`+`lxml`, no browser. Key gotcha: a bare User-Agent gets the WCM shell *without* the table; sending `User-Agent` + `Accept` + `Accept-Language` makes the server render the full page. `parse_calendar(html)` is pure and unit-tested against a saved fixture (`tests/fixtures/tcmb_calendar.html`). Same `www.tcmb.gov.tr` host the news lane already scrapes from CI, so no IP-block (the faaliyet-lane hazard doesn't apply here).
- **`web/migrations/0025_release_calendar.sql`** — `release_calendar (source, kind, event_date, title, source_url, downloaded_at)`, PK `(source, kind, event_date)`. Holds only the *scraped* events; the derived BDDK/BRSA/earnings rows stay computed live in `ahead.ts`. `source='tcmb'` today; TÜİK data releases fit later as `source='tuik'` with no schema change.
- **Cron** `.github/workflows/refresh-calendar.yml` — 1st of month (TCMB publishes ~yearly), advertised-rates blueprint: R2 snapshot round-trip → scrape → `push_to_d1.py --only-tables release_calendar`. Reuses existing secrets (no new one).

**Wiring** (`ahead.ts` + `ahead-data.ts`):
- `AheadKind` gains `mpc-minutes`, `inflation-report`, `fsr`. `aheadDates()` now takes the scraped `events` and picks the next event `>= now` per TCMB kind.
- **`MPC_DATES` is now a fallback, not the source.** MPC decision reads from the scrape; if the scrape is unavailable at render time, it falls back to `MPC_DATES` — so an outage degrades to the previous behaviour, never a blank. `check_calendar_fresh.py` stays, now guarding the fallback.
- The report kinds have **no fallback** — absent a scrape, their rows are simply omitted (fail closed, the Ahead contract).
- The 5 strips gained the report rows where relevant: Inflation Report on `/`, `/profitability`, `/deposits` (the real-return backdrop); Financial Stability Report on `/`, `/capital`, `/liquidity` (the systemic read).

## Verification

- Parser: `tests/test_release_calendar.py` — 4 kinds parse to expected ISO dates off the fixture; the 12 MPC-decision dates reproduce the hand-transcribed `MPC_DATES` exactly (which is why the scrape can replace them). Live scrape confirmed: 33 events, next MPC 2026-07-23.
- Web: `ahead.test.ts` extended — picks next-of-kind, MPC falls back to `MPC_DATES` when the scrape is empty, omits a kind whose events are all past. `tsc`/`lint`/`test` green (272 tests).
- Gates: `check_docs_sync`, `check_pipeline_graph_sync`, `check_schema_naming`, `check_calendar_fresh` all green. Pipeline-graph gains source + workflow + store nodes (+ `statusKey: release_calendar` freshness query in `pipeline-status.ts`).

## Not in v1 / follow-ons
- **No `/calendar` page** — per scope, the strips are the surface. A dedicated page is a small add on the same `release_calendar` table if wanted later.
- **TÜİK macro-data releases** (CPI/GDP/unemployment/trade/budget) — deferred. The `data.tuik.gov.tr/Bulten/Takvim` calendar is a JS SPA (redirects to `veriportali`, behind a Keycloak realm; the obvious path 404s), so it needs a headless scrape or approximate-cadence derivation. Natural Phase B: `source='tuik'` in the same table.
- First scheduled `refresh-calendar` run should be watched (standard advertised-rates caution), though the shared host makes an IP block unlikely.

Memory: [[project_prose_claims_lane]] (same Ahead system), [[reference_r2_token_scope_and_ci_ip]] (local-seed fallback if ever needed), [[reference_schema_conventions]].
