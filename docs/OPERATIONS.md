# Operations

The data pipeline runs entirely from GitHub Actions. The scheduled
workflows pick up new BDDK bulletins, new audit reports, and fresh
EVDS data on their own and push everything to Cloudflare D1 — no local
machine involvement is required for routine refreshes.

## Schedules

| When | Workflow | What it does |
|---|---|---|
| Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` | TCMB EVDS scrape (FX, rates, sterilization, …) → D1 |
| Saturday 02:00 UTC | `refresh-bddk-bulletins.yml` | Monthly + weekly BDDK bulletins (no EVDS, no audit) → D1 |
| Saturday 03:00 UTC | `refresh-data.yml` | Monthly + weekly BDDK + EVDS → D1 |
| Sunday 04:00 UTC | `refresh-audit.yml` | Audit-report scrape + extract → `bank_audit_*` → D1 (own DB + snapshot) |
| Daily 06:00 UTC | `healthcheck.yml` | D1 freshness check → Telegram/Discord alert if stale/failing |
| On push touching `web/**` | `deploy-cloudflare.yml` | Apply D1 migrations, build OpenNext bundle, deploy to Workers |
| On every PR | `ci.yml` | ruff + pytest + eslint + tsc quality gates |

All are also triggerable manually: **GitHub → Actions → pick
workflow → Run workflow**.

The bulletin/EVDS workflows and the audit workflow run on **separate storage
lanes** (different staging DB, R2 snapshot, and concurrency group), so they
don't serialize against each other and an audit failure can't stall bulletins.

## Manual operations (rare)

### Force a fresh refresh outside the cron schedule
```
GitHub → Actions → pick the workflow (refresh-bddk-bulletins / refresh-data /
refresh-evds-daily / refresh-audit) → Run workflow
```
Or use the **/admin** control center's Pipeline trigger buttons (needs
`GITHUB_DISPATCH_TOKEN`).

> **Dashboard caching:** public pages cache their D1 reads for ~12h, so freshly
> pushed data can take up to ~12 hours to appear on the site even though D1 itself
> is updated immediately. The `/admin` health view is uncached.

### One-off refresh from a local checkout (development)
```bash
# Monthly + weekly + EVDS into local SQLite
python scripts/refresh.py

# EVDS-only
python scripts/refresh.py --skip-monthly --skip-weekly

# Scrape new audit PDFs to R2 + extract into the standalone audit SQLite
# (requires R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)
python scripts/sync_audit_reports.py --db data/bank_audit.db
python scripts/build_bank_audit_stages.py --db data/bank_audit.db

# Push new rows to D1 (requires CLOUDFLARE_API_TOKEN)
python scripts/push_to_d1.py --hours 168                      # bulletin/EVDS lane
python scripts/push_to_d1.py --db data/bank_audit.db --hours 168 \
    --only-tables bank_audit_balance_sheet,bank_audit_profit_loss,bank_audit_credit_quality,bank_audit_profile,bank_audit_loans_by_sector,bank_audit_npl_movement,bank_audit_stages,bank_audit_extractions
```

> First-time local audit run: seed the standalone DB from the combined one
> with `python scripts/seed_audit_db.py` so you don't re-extract every PDF.

### Add new audit-report URLs (quarterly cadence)

When a bank publishes a new quarterly report (~late April / July /
October / February), add the URL to
`data/banks/audit_report_urls.json` — that's the only edit needed. The
Sunday `refresh-audit.yml` cron picks it up automatically, downloads the
PDF to R2, extracts the financial tables, and pushes the rows to D1.

To pick up the change before the next Sunday cron, trigger
`refresh-audit.yml` manually.

### Change the D1 schema (migrations)

The schema source of truth is the hand-authored, version-controlled files in
`web/migrations/` (idempotent, `IF NOT EXISTS`). To change it:

1. Add a new numbered file, e.g. `web/migrations/0002_add_xyz.sql`, with the
   `CREATE TABLE IF NOT EXISTS …` / `ALTER TABLE … ADD COLUMN …` statements.
   Mirror the change in the Python DDL (`src/*/schema.py` / scraper) so the
   staging SQLite matches.
2. Commit + push. The deploy workflow runs `wrangler d1 migrations apply
   bddk-data --remote`, which applies only files not yet recorded in the
   `d1_migrations` table. (`CREATE … IF NOT EXISTS` makes re-apply a no-op.)
3. Test locally first: `cd web && npx wrangler d1 migrations apply bddk-data --local`.

`scripts/generate_d1_migrations.py` is **data seeding only** (writes to
`web/seeds/`, gitignored) — not schema. Routine row updates go through
`push_to_d1.py`.

## Disaster recovery

Two independent safety nets, both **free**:

**D1 (the serving store) — Time Travel.** D1 keeps a 7-day point-in-time history
automatically (always on, no cost). To roll back a bad write:
```
cd web
npx wrangler d1 time-travel info bddk-data                 # see the restore window
npx wrangler d1 time-travel restore bddk-data --timestamp=<UNIX_TS>
```
(Destructive — it overwrites current data after a confirm. Free plan = 7 days back.)

**Pipeline snapshots — dated R2 backups.** Each refresh writes a dated copy to
`state/history/<lane>-YYYYMMDD.db.gz` (lane = `bddk_data` or `bank_audit`) and
keeps the last 7, so a corrupt run never destroys the only snapshot. To recover,
copy a good dated backup over the live key, e.g.:
```
# in a checkout with R2 creds in env
python - <<'PY'
from src.audit_reports import r2_storage
r2_storage.download_to("state/history/bddk_data-20260601.db.gz", "snap.db.gz")
r2_storage.upload_file("snap.db.gz", "state/bddk_data.db.gz")
PY
```
Then re-run the relevant refresh workflow to push the restored rows to D1.

## Secrets

GitHub repo → Settings → Secrets and variables → Actions:

| Secret | Used by |
|---|---|
| `CLOUDFLARE_API_TOKEN` | wrangler (D1 push, dashboard deploy) |
| `EVDS_API_KEY` | TCMB EVDS API |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | audit-report PDFs in R2 |

### Worker secrets (dashboard / `/admin`)

Set on the Worker — Cloudflare → Workers & Pages → `turkish-banking-dashboard`
→ Settings → Variables and Secrets (or `cd web && npx wrangler secret put NAME`):

| Secret | Used by |
|---|---|
| `ADMIN_PASSWORD` | unlocks `/admin` (password login) — **required to open /admin** |
| `GITHUB_DISPATCH_TOKEN` | `/admin` run status + trigger buttons (fine-grained PAT, Actions: read+write) |
| `CF_ANALYTICS_TOKEN` | `/admin` traffic panel (optional) |

Non-secret vars live in `web/wrangler.jsonc`: `CF_ANALYTICS_SITE_TAG`,
`CF_ACCOUNT_TAG`, and `CF_ACCESS_*` (only if you move to a custom domain and
switch `/admin` to Cloudflare Access). Full setup: [ADMIN.md](ADMIN.md).

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
