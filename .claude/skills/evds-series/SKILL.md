---
name: evds-series
description: Add, replace, or diagnose a TCMB EVDS macro series used by the dashboard. Use when adding a series code, repairing an empty or stale macro chart, checking a frequency mismatch, or handling an upstream series change. Verifies the current EVDS response, ingestion path, stored rows, chart wiring, and silent-success cases without restamping unchanged D1 rows.
---

# EVDS series work

## Read the current path first

Inspect these before changing anything:

- `src/scrapers/evds_scraper.py` for `Series`, `SERIES`, cadence groups, and
  compare-before-write behavior;
- `src/scrapers/evds_client.py` for request, date, frequency, retry, and cache
  semantics;
- the consuming page or query under `web/`;
- `web/app/lib/chart-specs.catalog.json` and
  `scripts/verify_chart_spec.py` for the chart's verification contract;
- the current workflow and `docs/OPERATIONS.md` for when the series is fetched.

Do not rely on a remembered code, label, schedule, or upstream availability.

## Add or replace a series

`SERIES` entries use `Series(code, label, category, freq)`. Confirm from current
EVDS metadata and a real read-only fetch:

- the exact code and display name;
- the source unit and aggregation;
- the native publication frequency;
- the available date range and latest observation;
- whether a replacement series is backcast or begins only at the break.

Use the frequency constants from `evds_client.py`; a wrong requested frequency
may return plausible resampled values instead of an error. Discover codes from
the current EVDS metadata hierarchy rather than guessing from UI labels.

Preserve the D1 cost invariant. The natural key is `(code, period_date)`, but
`INSERT OR REPLACE` alone is not sufficient idempotence: it still bills a write.
The scraper must compare fetched business values with stored rows and write only
new or changed observations. Do not refresh timestamps or rewrite settled rows.

## Diagnose silent success

A successful process exit does not prove that the series arrived. Check each
layer separately:

1. The EVDS fetch returned non-empty observations for the expected dates.
2. The requested frequency and units match the published series.
3. Refresh logs contain no per-series warning or timeout.
4. The staging table contains the expected `MAX(period_date)` and values.
5. If production verification is in scope, a read-only D1 query confirms the
   expected rows. A registry entry proves configuration, not ingestion.
6. The chart query uses the same code and date semantics.
7. The chart verification entry exercises a published date and value.

When a series stops at a clean date boundary, investigate an upstream revision,
rebase, rename, or publication lag before changing the chart. Verify current
source terms and availability instead of preserving a historical assumption in
this skill.

## Derivations

- Compute year-over-year change from the index level when that is the intended
  definition; do not chain published monthly rates.
- Twelve-month average inflation is the ratio of two twelve-month average index
  levels, not the mean of twelve year-over-year rates.
- Do not fill source gaps unless the methodology explicitly defines how.
- Keep sector aggregates distinct from bank-level observations.
- Label approximations and source substitutions honestly; do not reuse the
  source chart's label for a materially different measure.

## Wire the chart contract

For a new chart series, update the catalog entry with:

- the exact series locator and intended history;
- a registry addition consistent with `SERIES`;
- a verification date, published value, and tolerance from an authoritative
  source.

A zero-row query can render an empty panel without raising an error, so every
new chart needs a meaningful verification case.

## Operational boundary

Local work is limited to code changes and light, read-only probes. Heavy refresh
or backfill runs belong in GitHub Actions. A request to add or diagnose a series
does not by itself authorize a workflow dispatch, D1 write, deployment, or cache
purge. Perform those only when the current request explicitly includes them,
and confirm changed rows after the run rather than trusting the exit code.
