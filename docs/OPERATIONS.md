# Operations

The data pipeline runs entirely from GitHub Actions. The scheduled
workflows pick up new BDDK bulletins, new audit reports, and fresh
EVDS data on their own and push everything to Cloudflare D1 — no local
machine involvement is required for routine refreshes.

## Schedules

| When | Workflow | What it does |
|---|---|---|
| Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` | TCMB EVDS scrape (FX, rates, sterilization, …) → D1 |
| Saturday 03:00 UTC | `refresh-data.yml` | Monthly + weekly BDDK + EVDS + audit-report sync → D1 |
| On push touching `web/**` | `deploy-cloudflare.yml` | Build OpenNext bundle, deploy to Cloudflare Workers |

All three are also triggerable manually: **GitHub → Actions → pick
workflow → Run workflow**.

## Manual operations (rare)

### Force a fresh refresh outside the cron schedule
```
GitHub → Actions → "Refresh BDDK data" → Run workflow
```

### One-off refresh from a local checkout (development)
```bash
# Monthly + weekly + EVDS into local SQLite
python scripts/refresh.py

# EVDS-only
python scripts/refresh.py --skip-monthly --skip-weekly

# Scrape new audit PDFs to R2 + extract into local SQLite
# (requires R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
python scripts/sync_audit_reports.py

# Push new rows to D1 (requires CLOUDFLARE_API_TOKEN)
python scripts/push_to_d1.py --hours 168
```

### Add new audit-report URLs (quarterly cadence)

When a bank publishes a new quarterly report (~late April / July /
October / February), add the URL to
`data/banks/audit_report_urls.json` — that's the only edit needed. The
Saturday cron picks it up automatically, downloads the PDF to R2,
extracts the financial tables, and pushes the rows to D1.

To pick up the change before the next Saturday cron, trigger the
workflow manually.

## Secrets

GitHub repo → Settings → Secrets and variables → Actions:

| Secret | Used by |
|---|---|
| `CLOUDFLARE_API_TOKEN` | wrangler (D1 push, dashboard deploy) |
| `EVDS_API_KEY` | TCMB EVDS API |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | audit-report PDFs in R2 |

## Troubleshooting

- **EVDS step failed** — TCMB occasionally rate-limits. Re-run the
  workflow; the scraper is idempotent (INSERT OR REPLACE on
  `(code, period_date)`).
- **`sync_audit_reports.py` reports a 404** — bank rotated a URL on
  their IR site. Update the entry in `audit_report_urls.json`.
- **D1 push errors `no such column`** — schema drift between local
  SQLite and D1. Regenerate migrations with
  `python scripts/generate_d1_migrations.py` and apply via wrangler.
- **Cron didn't run on Saturday** — GitHub Actions sometimes delays
  free-tier crons by up to a few hours. Trigger manually for faster
  turnaround.
