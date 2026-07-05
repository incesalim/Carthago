# Operations

The data pipeline runs entirely from GitHub Actions. The scheduled
workflows pick up new BDDK bulletins, new audit reports, and fresh
EVDS data on their own and push everything to Cloudflare D1 — no local
machine involvement is required for routine refreshes.

## Schedules

| When | Workflow | What it does |
|---|---|---|
| Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` | TCMB EVDS scrape (FX, rates, sterilization, …) + TBB/TKBB/KAP/TEFAS non-critical steps → D1 |
| Saturday 02:00 UTC | `refresh-bddk-bulletins.yml` | Monthly + weekly BDDK bulletins (no EVDS, no audit) → D1 |
| Saturday 03:00 UTC | `refresh-data.yml` | Monthly + weekly BDDK + EVDS → D1 |
| Sunday 04:00 UTC | `acquire-audit.yml` | Audit-report **acquisition only**: discover + download new PDFs → R2, refresh the coverage matrix, notify on new reports (own `bddk-audit` group, read-only on the snapshot) |
| Manual / admin only | `refresh-audit.yml` | Audit-report **extraction**: PDFs from R2 → `bank_audit_*` → D1 + snapshot. Triggered from `/admin` (Pipeline "Extract audit reports" card or the coverage matrix's per-cell Re-extract). No schedule — extraction is reviewed, not automated |
| Manual only | `backfill-tefas.yml` | One-time (re-runnable) ~5-year TEFAS fund-market history backfill (API cap) — resumable via `tefas_fetch_log` (re-dispatch with the same `from` date) |
| Manual only | `backfill-audit.yml` | Re-extract already-ingested audit PDFs after an extractor fix (extraction skips `success=1`, so history never self-heals) → clear D1 partitions → push → snapshot. **Never run `banks=ALL`** — it exceeds the 180-min job timeout mid-extraction; dispatch ~5-bank chunks sequentially (the `bddk-audit` concurrency group queues them) |
| Manual only | `reextract-statement.yml` | Targeted **single-statement** re-extract (`reextract_statement.py`): one lane (`oci` / `cash_flow` / `equity_change` / `npl_movement` / `loans_by_sector` / `bank_profile` / `credit_quality`) for selected `periods`/`banks` → inline-validate → push that table + `bank_audit_validation` → snapshot → refresh matrix. `only_failing=true` (default) processes only NOT-passing partitions (`checks_failed>0 OR checks_passed=0` — catches stale empties); the non-destructive guard skips passing ones, so it can only improve. **`force=true`** overwrites even passing partitions — needed when the defect is in a **derived** table (e.g. `credit_quality` passes but its derived `bank_audit_stages` fails, so `only_failing` wouldn't select it); the `credit_quality` lane also rebuilds `bank_audit_stages` after the run. **Preferred over `backfill-audit.yml` for a single-lane fix** — one lane on fitz, no full-extract timeout (an all-periods lane run is ~6–10 min). How OCI/CF/NPL/loans_by_stage were fixed fleet-wide |
| Daily 06:00 UTC | `healthcheck.yml` | D1 freshness check → Telegram/Discord alert if stale/failing |
| On push touching `web/**` | `deploy-cloudflare.yml` | Apply D1 migrations, build OpenNext bundle, deploy to Workers |
| On every PR | `ci.yml` | ruff + pytest + eslint + tsc + vitest quality gates |

All are also triggerable manually: **GitHub → Actions → pick
workflow → Run workflow**.

The bulletin/EVDS workflows and the audit workflow run on **separate storage
lanes** (different staging DB, R2 snapshot, and concurrency group), so they
don't serialize against each other and an audit failure can't stall bulletins.

### Two staging DBs (and the spine-table guard)

There are **two** local SQLite staging DBs, each with its own R2 snapshot:

| DB | Holds | R2 snapshot | Lane |
|---|---|---|---|
| `data/bddk_data.db` | BDDK monthly/weekly + EVDS + news + TBB + TKBB + KAP + TEFAS + BIST | `state/bddk_data.db.gz` | `bddk-pipeline` |
| `data/bank_audit.db` | the `bank_audit_*` tables (PDF extraction) | `state/bank_audit.db.gz` | `bddk-audit` |

Both lanes push to the **same D1**, writing a disjoint set of tables. The catch:
the coverage-matrix **spine tables** (`bank_audit_coverage` / `bank_audit_expected`
/ `bank_audit_statement_types`) are **full-rebuild** — `push_to_d1.py` issues
`DELETE FROM <t>; INSERT …` from the local copy, not a time-windowed upsert. Those
tables are only populated in `bank_audit.db` (by `sync_audit_expected.py`); in
`bddk_data.db` they exist but are **empty**. A daily news/EVDS push from
`bddk_data.db` would therefore `DELETE` the spine and insert nothing — **wiping the
/admin coverage matrix**. The guard: `push_to_d1.fetch_recent` now **skips a
full-rebuild table when the local copy is empty** (it never emits the wiping
`DELETE`). See *Troubleshooting → coverage matrix blank* for the restore recipe.

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
# Or just one bank's freshly published quarter:
python scripts/sync_audit_reports.py --db data/bank_audit.db --only-bank ZIRAAT --latest-period
python scripts/build_bank_audit_stages.py --db data/bank_audit.db

# Push new rows to D1 (requires CLOUDFLARE_API_TOKEN)
python scripts/push_to_d1.py --hours 168                      # bulletin/EVDS lane
python scripts/push_to_d1.py --db data/bank_audit.db --hours 168 \
    --only-tables bank_audit_balance_sheet,bank_audit_profit_loss,bank_audit_oci,bank_audit_credit_quality,bank_audit_profile,bank_audit_loans_by_sector,bank_audit_npl_movement,bank_audit_stages,bank_audit_capital,bank_audit_liquidity,bank_audit_extractions,bank_audit_validation
```

> First-time local audit run: seed the standalone DB from the combined one
> with `python scripts/seed_audit_db.py` so you don't re-extract every PDF.

### Get a newly published audit report in (quarterly cadence)

When a bank publishes a new quarterly report (~late April / July /
October / February):

- **13 banks auto-discover** from their IR page — no edit needed. They are
  ALBRK, ANADOLU, EMLAK, EXIM, FIBA, HALKB, ING, PASHA, TEB, TFKB, TSKB,
  VAKIFK, ZIRAAT (`DISCOVERY_BANKS` in `src/audit_reports/discovery.py`).
- **Every other bank**: add the URL to `data/banks/audit_report_urls.json`
  — that's the only edit needed.

The Sunday `acquire-audit.yml` cron then **downloads the PDF to R2 by itself**,
refreshes the coverage matrix (the new quarter shows as a **missing** column),
and pings Telegram. **Extraction is a deliberate second step**: open **/admin**,
find the new cell, and click **Re-extract** (or run the Pipeline "Extract audit
reports" card). Extraction is not automatic — you review the matrix after.

To acquire before the next Sunday cron, trigger `acquire-audit.yml` manually
(GitHub → Actions, or the /admin Pipeline "Acquire audit PDFs" card).

To enable auto-discovery for more banks, run
`python scripts/validate_discovery.py` (it checks discovery against the
config) and add any passing ticker to `DISCOVERY_BANKS`. See
[ADMIN.md](ADMIN.md) §Auto-discovery.

### TBB digital-banking statistics (quarterly)

The weekly Saturday `refresh-data.yml` cron already refreshes TBB (a
non-critical step in `refresh.py` → `scripts/update_tbb_digital.py`, latest 2
reports). When TBB publishes a new quarter (~Feb / May / Aug / Nov) it is
picked up automatically; nothing to edit. Discovery constructs the report slug
(`{year}-{month}-dijital-internet-ve-mobil-bankacilik-istatistikleri`) and
verifies the Excel link exists, so not-yet-published quarters are ignored.

**One-time / full-history backfill** (e.g. after first deploy, or to extend
history). Run against the bulletin-lane snapshot, then push + re-upload — the
same pattern as other backfills:

```bash
# 1. Pull the current snapshot from R2 → data/bddk_data.db (R2 creds in env)
python - <<'PY'
import gzip, shutil, pathlib
from src.audit_reports import r2_storage
gz, db = pathlib.Path("data/bddk_data.db.gz"), pathlib.Path("data/bddk_data.db")
r2_storage.download_to("state/bddk_data.db.gz", gz)
with gzip.open(gz, "rb") as s, open(db, "wb") as d: shutil.copyfileobj(s, d)
PY
# 2. Backfill every published quarter into the snapshot DB
python scripts/update_tbb_digital.py --all --start-year 2018
# 3. Push the table to D1 (wide window so it all lands), then re-upload snapshot
python scripts/push_to_d1.py --only-tables tbb_digital_stats --hours 8760
python - <<'PY'
import pathlib; from src.audit_reports import r2_storage
r2_storage.upload_file(pathlib.Path("data/bddk_data.db.gz"), "state/bddk_data.db.gz")
PY
```

The `tbb_digital_stats` table must exist in D1 first (migration
`0003_tbb_digital_stats.sql`, applied by the deploy workflow). Workbooks
overlap and revise; `--all` processes oldest→newest so the latest figure wins.

### TKBB participation-bank digital statistics

Participation banks aren't TBB members; their digital stats come from TKBB's
Veri Peteği portal, served by a Turboard BI instance
(`https://veri-petegi.tkbb.org.tr`) whose JSON API is publicly readable — no
auth, plain GETs (recipe in `src/tkbb/turboard.py`). Two lanes, both
non-critical steps in `refresh.py` (skippable with `--skip-tkbb`):

- **Quarterly digital stats** (`scripts/update_tkbb_digital.py` →
  `tkbb_digital_stats`): active customers (total / channel-mix / province),
  transaction volume & count (by channel / segment / category), 2020-Q1 →
  present, RAW units (persons / count / TRY — the web layer scales). The
  default run is **incremental with automatic backfill**: it enumerates the
  live period-filter values (verbatim — TKBB's labels are inconsistently
  spaced, never construct them), diffs against periods already in the DB, and
  always re-fetches the newest stored period for revisions. On an empty table
  that means the full ~25-quarter backfill in one run (~275 GETs, minutes).
  `verify_dashboard()` fails loudly if TKBB rebuilds the dashboard (pinned
  dashlet ids missing) and warns on title drift.
- **Monthly remote-vs-branch acquisition** (`scripts/update_tkbb_acquisition.py`
  → `tkbb_acquisition_stats`): the public dashboard exposes only a **rolling
  last-12-months window** — each run upserts it and history accumulates
  forward (from 2025-07). **Never delete rows**; there is no way to re-fetch
  months that have left the window. Measure names (applications/customers) are
  resolved from the live dashboard's measure aliases and fail loudly on drift.

Tables must exist in D1 first (migration `0017_tkbb_stats.sql`). A manual
wide-window push after a local run:

```bash
python scripts/push_to_d1.py --only-tables tkbb_digital_stats,tkbb_acquisition_stats --hours 8760
```

For a from-scratch rebuild, use the same R2 snapshot pull → run → push →
re-upload sequence as the TBB backfill above (both updaters take `--db`).

### KAP ownership structure (weekly)

The weekly Saturday `refresh-data.yml` cron refreshes `kap_ownership` (a
non-critical step in `refresh.py` → `scripts/update_kap_ownership.py`). For
every bank in `data/banks/kap_company_map.json` it scrapes the KAP "Genel
Bilgi Formu" page (server-rendered Next.js — plain requests decode the flight
payload; no browser, no API key) and **replaces the bank's whole partition**:
≥5% shareholders (+ DİĞER/TOPLAM), indirect holders, free float, paid-in
capital, capital ceiling, and §7 subsidiaries / financial investments
(item='subsidiary': company, activity, relation type, share %, and the bank's
capital share **in the filing currency** — TRY/EUR/USD, not converted).
Listed and non-listed banks file different item-key variants
(`sermayede_dogrudan` vs `ortaklik_yapisi`); both are handled, but only the
full form carries the subsidiaries grid (~15 banks — variant filers like
Ziraat/Kuveyt don't disclose it on KAP). Per-bank failures keep the previous
rows; ATBANK has no published form at all.

Shrunken grids queue DELETEs in the staging-side `d1_pending_deletes` outbox,
which `push_to_d1.py` replays against D1 before its INSERTs (the push is
otherwise INSERT OR REPLACE-only and would leave orphan rows).

When a bank is added/renamed on KAP, rebuild the map and review the diff:

```bash
python scripts/update_kap_ownership.py --discover   # rewrites kap_company_map.json
# entries with "manual": true (e.g. EXIM → TÜRKİYE İHRACAT KREDİ BANKASI)
# survive re-discovery; pin any new mismatch the same way.
python scripts/update_kap_ownership.py --banks NEWTICKER   # spot-refresh
```

The `kap_ownership` table must exist in D1 first (migration
`0006_kap_ownership.sql`). Caveats: `as_of` is the KAP filing date — ownership
rows can be years old if the structure hasn't changed; in the non-listed grid
variant some banks enter the ratio into the TL column too (Ziraat reports
`share_tl` = 100), so treat `ratio_pct` as authoritative there.

### TEFAS fund market (daily + one-time backfill)

The daily crons refresh the four `tefas_*` aggregate tables (a non-critical
step in `refresh.py` → `scripts/update_tefas.py`): each run re-fetches a
trailing **7-day window** per fund type from the tefas.gov.tr JSON API and
re-aggregates, so T+1 publishing lag, holidays and revisions self-heal via the
idempotent upsert. Per-fund rows are never stored — see
[METRICS.md](METRICS.md) §15.

**Rate limit.** The API allows ~6 requests/min (HTTP 429 beyond, resets
~65 s) and max 30 days per request. `src/tefas/client.py` paces at ~5.5/min
(11 s spacing) and sleeps 70 s on a 429. The site's robots.txt disallows
`/api/` for AI crawlers — this lane is a polite, low-volume scheduled
fetcher: never parallelize it or shrink the pacing interval.

**Backfill / re-aggregation.** Dispatch `backfill-tefas.yml` (inputs:
`from` — empty = the API's ~5-year horizon (start dates older than 5 years
are rejected: "Başlangıç Tarihi 5 yıldan eski olamaz") — plus optional `to`
and `types`). It pulls the bulletin snapshot, walks 28-day windows
oldest→newest (~660 requests ≈ 2–2.5 h, holding the `bddk-pipeline` group so
daily crons queue behind it),
pushes to D1 every 15 windows, and uploads the snapshot back. Completed
windows are recorded in the staging-only `tefas_fetch_log` — **resume by
re-dispatching with the same `from` date** (windows are aligned from it).
After changing `extract_manager` / `categorize_fund` / `ASSET_ROLLUP` in
`src/tefas/normalize.py`, history must be re-aggregated: clear the log, then
re-run the full backfill:

```bash
python - <<'PY'
import sqlite3
c = sqlite3.connect("data/bddk_data.db")
c.execute("DELETE FROM tefas_fetch_log"); c.commit()
PY
python scripts/update_tefas.py --backfill --push-every 15  # from = ~5y horizon
```

The `tefas_*` tables must exist in D1 first (migration
`0007_tefas_funds.sql`, applied by the deploy workflow) — the periodic
`--push-every` pushes fail otherwise. Top-fund partition shrinks queue
DELETEs in the shared `d1_pending_deletes` outbox (KAP pattern). The
healthcheck watches `MAX(date)` in `tefas_manager_daily` with a 120 h
threshold; one benign alert can fire during multi-day religious holidays
(no trading days → no new data).

### BIST equity market (daily + one-time backfill)

The daily crons refresh `bist_prices` / `bist_dividends` / `bist_shares` (a
non-critical step in `refresh.py` → `python -m src.scrapers.bist_scraper`): each
run re-fetches a trailing **35-day window** for the 11 listed banks + the XU100 /
XBANK indices from the Yahoo Finance chart API and upserts, so the EOD ~1-day
lag, market holidays and late closes self-heal. Source data + universe rules in
[METRICS.md](METRICS.md) §17.

**One-time / re-backfill.** To (re)load deep history:

```bash
python -m src.scrapers.bist_scraper --backfill   # ~12 years, all symbols
python scripts/push_to_d1.py --hours 8760 --only-tables bist_prices,bist_dividends,bist_shares
```

The `bist_*` tables must exist in D1 first (migration `0012_bist.sql`, applied
by the deploy workflow). For a full backfill, pull the R2 snapshot first and
upload it back afterwards (same pattern as the EVDS workflow) so the cron's
working copy carries the history — otherwise D1 keeps the deep history but the
R2 snapshot only rebuilds the trailing 35-day window.

**Shares outstanding.** `bist_shares` drives market cap (P/B, P/E). The scraper
refreshes it best-effort each run from Yahoo `quoteSummary` (cookie+crumb) and
falls back to the committed `data/banks/bist_shares.json` seed. **Refresh the
seed on capital actions** (bonus/rights issues, splits) — re-run the standalone
quoteSummary pull and update the JSON, or trust the live refresh if it resolves.
QNBFB is intentionally absent (delisted float on Yahoo → no price → no cap).

**Live price overlay (request-time, NOT the cron).** `web/app/lib/bist-live.ts`
fetches the latest (delayed ~15-min) Yahoo price when `/banks/[ticker]`,
`/cross-bank`, or `/economy` render, and overlays it on the stored EOD figures.
This is **separate from the daily cron** and writes nothing to D1. It does NOT
use the Next/KV data cache (that would breach the ~1k KV-writes/day cap) — it
relies on Cloudflare's edge cache (`cf.cacheTtl=60`) + a per-isolate in-memory
TTL, with a 2.5 s timeout and silent fallback to the stored close.
- **Disable it without a deploy:** set the Worker var `BIST_LIVE_DISABLED=1`
  (`wrangler secret put BIST_LIVE_DISABLED` or a `vars` entry) → pages fall back
  to the stored EOD prices. Use this if Yahoo ever rate-limits the Worker egress.
- **Monitoring:** if pages feel slow, check the edge cache is engaging (repeated
  loads within 60 s should not re-hit Yahoo) and watch KV writes stay flat (the
  overlay must never add KV writes).

### Bank logos (rare — when a bank is added)

Per-bank brand marks live as committed static PNGs in `web/public/logos/<TICKER>.png`
and render on the `/banks` index cards + per-bank header via `BankLogo`
(`web/app/components/BankLogo.tsx`). They are **not** in D1 — no cron, no runtime
fetch (CSP-safe, offline-stable).

```
# Fetch any missing logos (skips those already present):
python scripts/fetch_bank_logos.py
# Re-fetch a specific bank (e.g. after a rebrand):
python scripts/fetch_bank_logos.py --force GARAN
```

The fetcher sources each bank's own `apple-touch-icon`, falling back to curated
Wikimedia / site-header logos (`WIKIMEDIA` / `OVERRIDES` in the script) for banks
that expose no usable square mark. SVG sources are rasterised via Wikimedia's
thumbnail renderer or the weserv proxy (no local SVG renderer needed). Every logo
is trimmed to its natural aspect ratio; the UI renders them at a fixed height, so
square marks and wide wordmarks line up. The script also regenerates
`web/app/lib/bank-logos.generated.ts` (each committed logo's intrinsic
`[width, height]`) — commit it alongside the PNGs so the UI never points at a
missing file. Banks with no sourceable logo (a small tail — currently ATBANK,
PASHA, TSKB) fall back to a neutral ticker chip; drop a hand-made square PNG at
`web/public/logos/<TICKER>.png` and re-run `--renorm` to adopt it. Domain map:
`data/banks/bank_logo_domains.json` (keep in sync with `bank_names.ts`).

### Generate a presentation deck (PDF)

A one-command board-style "sector read-out" as a PDF slide deck — a dark title
slide, a KPI vitals slide (stat tiles), one slide per T1 tab (headline + driver
bullets + a trend chart), and a methodology slide:

```
# Fetch the rendered deck → PDF (reports/presentation-<date>.pdf):
python scripts/generate_presentation.py --open
# Save the HTML only (open it and Ctrl+P → Save as PDF):
python scripts/generate_presentation.py --html-only
# A subset / reorder of sections, custom title / output path:
python scripts/generate_presentation.py --tabs overview,capital,profitability
python scripts/generate_presentation.py --title "Q1 Board Pack" --out ~/deck.pdf
# Print a local HTML you already have:
python scripts/generate_presentation.py --file deck.html
```

The generator (`scripts/generate_presentation.py`) is a **thin wrapper**: it
`GET`s the fully-rendered deck HTML from `/api/presentation` (the single source
of truth — `web/app/lib/presentation-deck.ts` off
`web/app/lib/presentation-data.ts`, which reuses the dashboard's **own**
`metrics.ts` functions, so tiles and charts carry the site's exact numbers — no
re-derivation, no drift), then prints it to PDF with a **headless Chrome/Edge**
`--print-to-pdf` (auto-detected; `--browser <path>` or `CHROME_PATH` to override
— no new dependency). The route can't produce a PDF itself (Workers can't run
headless Chrome); this script is that render step. Output goes to `reports/`
(gitignored). `--tabs` / `--title` pass straight through as query params.

The **in-dashboard button** does the same without the CLI: `/admin` →
**Presentation** → **Generate PDF** opens `GET /api/presentation?print=1` and the
browser print dialog (Save as PDF). See [ADMIN.md](ADMIN.md) §Presentation deck.

### Change the D1 schema (migrations)

The schema source of truth is the hand-authored, version-controlled files in
`web/migrations/` (idempotent, `IF NOT EXISTS`). To change it:

1. Add a new numbered file, e.g. `web/migrations/0002_add_xyz.sql`, with the
   `CREATE TABLE IF NOT EXISTS …` / `ALTER TABLE … ADD COLUMN …` statements.
   Follow the naming rules in [SCHEMA_CONVENTIONS.md](SCHEMA_CONVENTIONS.md)
   (`bank_ticker` / `amount_fc` / snake_case / no reserved words / unique number)
   — CI's `scripts/check_schema_naming.py` enforces them for migrations ≥ 0022.
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
- **/admin coverage matrix went blank** — the full-rebuild spine tables were
  wiped in D1 (historically by a push from the wrong staging DB; now guarded —
  see *Two staging DBs*). Restore from a checkout with R2+CF creds:
  ```bash
  python -c "from scripts.audit_d1 import pull_snapshot; pull_snapshot(guard=False)"
  python scripts/sync_audit_expected.py --db data/bank_audit.db --push
  ```
  (pull the fresh audit snapshot → rebuild + push the matrix; ~13.6k cells.)
- **Audit data-quality alerts** — each audit run ends with
  `check_audit_quality.py --alert`. Beyond the per-partition validators it runs
  **within-bank outlier** checks for the reconciliation-free tables:
  `_liquidity_outliers` (a ratio ≥8× off the bank's own median = a decimal/wrong-cell
  slip; covers `lcr_fc`, which the band check never reads) and
  `_off_balance_consistency` (TOTAL/Σromans jumping off the bank's median = a dropped
  roman section). A flag is a real extraction error, not a false positive — fix the
  extractor, then re-extract that lane.
