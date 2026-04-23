# Operations

Two-paragraph guide to keeping the dashboard fresh after BDDK publishes
new data.

## One command

From the project root:

```bash
python scripts/refresh.py --push
```

That does **everything**:
1. Checks BDDK for new monthly bulletins, scrapes anything it hasn't got.
2. Pulls the latest 13 weeks of weekly data (overlaps are safe — idempotent).
3. Vacuums the SQLite DB.
4. Re-compresses `data/bddk_data.db.gz` to ship with the repo.
5. Commits the snapshot and pushes to GitHub → Render auto-redeploys.

Drop the `--push` flag if you want to refresh locally without publishing.

## When to run it

| Cadence | Why |
|---|---|
| Every Friday evening / Saturday | BDDK publishes weekly data Fridays. |
| ~6 weeks after each month-end | Monthly bulletins lag ~4–6 weeks. Running weekly still catches monthly as soon as it's available. |

Running more often than that is harmless — the update scripts are
idempotent and skip work that's already done.

## Individual scripts (if you want finer control)

- `python scripts/update_monthly.py` — only monthly.
- `python scripts/update_weekly.py` — only weekly (13-week window).
- `python scripts/backfill_2020_2023.py` — full historical monthly backfill (~3 h).
- `python scripts/backfill_weekly_2y.py` — full 2-year weekly backfill (~3.5 h).

## Developing the dashboard (hot reload)

```bash
python scripts/dev.py
```

Dash runs with `debug=True` + auto-reload. Edit a file, save, browser
refreshes in under a second. No process kills, no manual restart. Stop
with Ctrl+C.

Production (Render) still uses `src/dashboard/app.py` directly via
gunicorn — `scripts/dev.py` is local-only.

## Series registry

Every EVDS code, BDDK chart-id, published-ratio `item_name` lives in
[`src/dashboard/series.py`](../src/dashboard/series.py) keyed by short
names (`"policy_rate"`, `"w_total_loans"`, `"r_npl_ratio"` …). Any new
chart should look up series by key, never paste a raw code. Missing key?
Add it to the registry — don't inline.

## Troubleshooting

- **Render build succeeded but dashboard blank** — re-check that
  `data/bddk_data.db.gz` is in the latest commit and under 100 MB.
- **"No new months published"** — expected most of the time; BDDK only
  publishes once a month and runs a 4–6 week lag.
- **`refresh.py` errors on push** — usually a merge conflict if you
  edited files on GitHub directly. `git pull --rebase && git push` and
  retry.
- **Deploy logs mention `EVDS_API_KEY`** — set it in Render's Environment
  tab (it's a secret, not in the repo).
