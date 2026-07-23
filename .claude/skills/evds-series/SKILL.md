---
name: evds-series
description: Add, replace or debug a TCMB EVDS macro series (evds_series table, the /economy /inflation /growth /budget /foreign-trade /bop pages). Use when adding a series code, when a chart on a macro page goes blank or flat, when a series stops updating, when the user says "add this EVDS series", "this macro chart is empty", "TP.* isn't updating", or when a TÜİK rebase changes a code. Encodes the silent-failure modes — a dead code and a CI timeout both leave the refresh exiting 0.
---

# EVDS series work

## Where a series lives

`SERIES` in `src/scrapers/evds_scraper.py` — a flat list of
`Series(code, label, category, freq)`:

- `category` — one of `rates` / `fx` / `inflation` / `cbrt` / `macro`;
  drives which page picks it up.
- `freq` — `evds.FREQ_DAILY` (1) / `FREQ_WEEKLY` (3) / `FREQ_MONTHLY` (5) /
  `FREQ_QUARTERLY` (6). Wrong frequency doesn't error, it just returns
  resampled values that quietly disagree with the published figure.

Writes are `INSERT OR REPLACE` on `(code, period_date)`, so re-running is
safe and a corrected vintage overwrites cleanly.

Finding a code: the EVDS metadata endpoints are the **slash form** on
`evds3` — `categories/`, `datagroups/`, `serieList/`. Don't guess codes from
the web UI's display names.

## The two silent failures

Both of these leave `refresh.py` **exiting 0**. Never take a green run as
evidence a series arrived.

1. **A dead code.** When TÜİK rebases, the old code stops returning data
   rather than erroring. `TP.FG.J0` (CPI 2003=100) died at the Jan-2026
   rebase; `TP.TUKFIY2025.GENEL` is the replacement and is backcast, so the
   old code is kept only for continuity. If a macro chart flatlines from a
   specific month onward, suspect a rebase before suspecting the chart.
2. **A CI read-timeout.** `evds3` intermittently times out from the GitHub
   Actions runner. The affected series logs `[err]` and the run continues
   green. Read the log lines, not the exit code — and re-dispatch rather
   than "fixing" a scraper that isn't broken.

After any change, confirm the rows actually landed in D1 for the expected
`period_date` range. A code that returns 200 with an empty payload looks
identical to success from the outside.

## What EVDS can and cannot tell you

- **Rates are sector-level only.** `TP.KTFTUK` / `TP.KTF17` / `TP.KTF12` /
  `TP.TRY.MT06` are survey aggregates. There is no per-bank rate in EVDS —
  the per-bank complements are `bank_advertised_rates` (posted rates,
  scraped) and the P&L-derived realized yield/cost in `heatmap.ts`. Don't
  present a sector series as a bank's rate.
- **PMI is not in EVDS** and the İSO/S&P release is paywalled. Use the TCMB
  Real Sector Confidence series instead of implying PMI coverage.
- **FC rates** for the FC-side charts are `TP.KTF17.USD` / `TP.KTF17.EUR`.

## Derivations that have a right answer

- **12-month average inflation** is the **ratio of two 12-month averages**,
  not the average of twelve y/y rates. The two differ by enough to be wrong
  in print.
- **y/y from an index** — compute from the index level, don't chain
  published monthly rates.
- Chain-volume TÜİK growth series carry gaps that EVDS won't fill; those
  need the TÜİK Excel path (veriportali cookie-session →
  `/api/en/data/downloads`).

## Wiring a series to a chart

A new series usually arrives with a chart. Add a
`web/app/lib/chart-specs.catalog.json` entry alongside it:

- `series[].locator` — `{ "code": "TP.…", "years_back": N }`
- `registry_additions` — the same code/label/category/freq you added to
  `SERIES`, so the catalog is self-describing
- a `verify` block — series / date / value / tolerance, taken from the
  **published** figure

`scripts/verify_chart_spec.py` runs in the daily healthcheck. Without a
`verify` entry a 0-row query renders an empty panel and nothing complains.

## After it ships

Public pages cache their D1 reads, so a correct push can take hours to
appear. Before debugging a "missing" series on the live site, check D1
directly; purge `NEXT_INC_CACHE_KV` if you need it immediately.
