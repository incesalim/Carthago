# Operations

The data pipeline runs entirely from GitHub Actions. The scheduled
workflows pick up new BDDK bulletins, new audit reports, and fresh
EVDS data on their own and push everything to Cloudflare D1 — no local
machine involvement is required for routine refreshes.

> **Shell note.** This repo is worked from **Windows PowerShell 5.1**, which has
> no `&&` — `cd web && npx wrangler …` is a parser error there, not a chaining
> operator. Commands in these docs use `;` so they run in both PowerShell and
> bash, and call CLIs through `npx` since `wrangler` is a local dependency and is
> not on PATH.

## Schedules

| When | Workflow | What it does |
|---|---|---|
| Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` | TCMB EVDS scrape (FX, rates, sterilization, …) + the non-critical TBB/TKBB/KAP/TEFAS/Faaliyet steps of `refresh.py` → D1 |
| Daily 04:00 UTC | `refresh-news-daily.yml` | `sync_news.py` → `news_items` + `news_item_banks` (KAP filings, TCMB/BDDK announcements, bank press rooms, Google News) → D1 |
| Daily 13:00 UTC + Fri 13:30/15:30 UTC + Sat 02:00 UTC | `refresh-bddk-bulletins.yml` | BDDK bulletins (no EVDS, no audit) → D1. **Daily 13:00** = **monthly** check (probe-then-fetch; the month lands mid-month on no fixed day). **Fri 16:30 & 18:30 Turkey** = **weekly** (BDDK publishes it Friday afternoon). **Sat 02:00** = weekly backstop. Each per-schedule run skips the other lane via `github.event.schedule`; manual dispatch does both. Sends a positive Telegram ping ("published & fetched") when a new weekly/monthly period lands (`notify_new_bddk.py`); quiet otherwise |
| Saturday 03:00 UTC | `refresh-data.yml` | Monthly + weekly BDDK + EVDS → D1 |
| Saturday 06:00 UTC | `refresh-presentations-weekly.yml` | `update_presentations.py` → `bank_earnings` (IR presentation decks) → D1 (`--only-tables=bank_earnings`). Bulletin lane (`bddk-pipeline` group). Tier-1 results filings ride `refresh-news-daily.yml` instead |
| Monday 06:00 UTC | `refresh-advertised-rates.yml` | `src.rates.scraper` → `bank_advertised_rates` → D1 (`--only-tables=bank_advertised_rates`). Per-bank **advertised** (posted-to-new-customers) loan + deposit rates scraped from doviz.com (loans) and hangikredi (deposits) — the only per-bank rate source; EVDS/BDDK publish rates at sector level only. Each run appends a dated `snapshot_date`, so history accretes (the sources only expose "today"). Bulletin lane (`bddk-pipeline` group) |
| 1st of month 06:00 UTC | `refresh-calendar.yml` | `src.release_calendar.scraper` → `release_calendar` → D1 (`--only-tables=release_calendar`). Scrapes TCMB's published calendar (MPC decisions + minutes + Inflation Report + Financial Stability Report) so the **Ahead** strips fill themselves — retires the hand-typed `MPC_DATES` (now a render-time fallback, still guarded by `check_calendar_fresh.py`). `requests`+`lxml`, no browser. Bulletin lane (`bddk-pipeline` group) |
| Sunday 04:00 UTC | `acquire-audit.yml` | Audit-report **acquisition only**: discover + download new PDFs → R2, refresh the coverage matrix, notify on new reports (own `bddk-audit` group, read-only on the snapshot) |
| Sunday 06:00 UTC | `summarize-regulations.yml` | Weekly regulation briefing via Kimi → `regulation_briefings` → D1. **Needs the `KIMI_API_TOKEN` secret** (see Secrets). Runs with `--require-baseline`, so it **fails rather than shipping an ungrounded briefing** (it warned-and-continued for 7 weeks unnoticed — see [regulation_followups.md](regulation_followups.md) §A). **Annual pin:** once a year dispatch it with `baseline_year=YYYY` + `baseline_url=<TCMB "Monetary Policy for YYYY" PDF>` — the ingest must run *here*, between the snapshot pull and upload, because a local run writes a DB production never reads. **Posts the briefing to Telegram** (every section + bullet, split across messages under the 4k cap) whenever the LLM actually runs; silent on unchanged-input weeks. `force=true` regenerates on demand |
| Sunday 07:30 UTC | `generate-reads.yml` | "The Read" — LLM-rewritten headline per dashboard tab → `read_headlines` → D1. Free providers with per-family pacing + magnitude-match number validation; falls back to a deterministic template |
| Manual / admin only | `refresh-audit.yml` | Audit-report **extraction**: PDFs from R2 → `bank_audit_*` → D1 + snapshot. Triggered from `/admin` (Pipeline "Extract audit reports" card or the coverage matrix's per-cell Re-extract). No schedule — extraction is reviewed, not automated |
| Manual only (eval) | `analyst-research.yml` | **Analyst V2 — agentic discovery over deterministic evidence** ([ANALYST_V2.md](ANALYST_V2.md)): pulls the R2 snapshots + the filing PDF's per-page text, runs the story-agnostic anomaly scout, then a bounded hypothesis-driven research loop over typed read-only tools, deterministic verification of structured findings, and a rendered summary of survivors. **Artifact-only, no D1 writes, no schedule, nothing publishes automatically** — V1 (`analyst-daily.yml`) stays the baseline; publishing waits on the evaluation corpus + explicit human approval. `scout_only=true` runs without any LLM |
| Manual only (freeze) | `analyst-daily.yml` | The analyst layer: pulls both R2 snapshots, runs the deterministic detectors (`scripts/analyst/detect.py` — unit switches, cross-period restatements, opinion changes, perimeter, CAR−CET1 / NPL-vs-coverage divergences), then generates grounded LLM memos for the requested banks (`web/scripts/analyst-run.ts --memo`, free-model chain, figure guard). Migration `0037_analyst_signals.sql` is **applied**, and a **`push` input (default false)** sends `analyst_signals` + `analyst_basis_metadata` + `analyst_notes` to D1 via `push_to_d1.py --db data/analyst.db`. All three are `_FULL_REBUILD` (derived wholesale each run, so a signal that stops firing must disappear rather than linger) and tiny — ~9,030 billed rows, and the content hash makes an unchanged re-run free. ⚠️ `fired_at` is excluded from that hash: `detect.py` omits the column on INSERT so it takes a fresh `CURRENT_TIMESTAMP` every run, and leaving it in would rebuild the tables daily forever. The daily 07:00 UTC cron is live; `push` stays opt-in per dispatch. `banks=CALIBRATE` runs the ALBRK+SKBNK calibration pair from the feasibility test; Telegram ping on critical signals |
| Manual only | `backfill-tefas.yml` | One-time (re-runnable) ~5-year TEFAS fund-market history backfill (API cap) — resumable via `tefas_fetch_log` (re-dispatch with the same `from` date) |
| Manual only | `backfill-audit.yml` | Re-extract already-ingested audit PDFs after an extractor fix (extraction skips `success=1`, so history never self-heals) → clear D1 partitions → push → snapshot. **Never run `banks=ALL`** — it exceeds the 180-min job timeout mid-extraction; dispatch ~5-bank chunks sequentially (the `bddk-audit` concurrency group queues them) |
| Manual only | `reextract-statement.yml` | Targeted **single-statement** re-extract (`reextract_statement.py`): one lane (`oci` / `cash_flow` / `equity_change` / `npl_movement` / `loans_by_sector` / `bank_profile` / `credit_quality`) for selected `periods`/`banks` → inline-validate → push that table + `bank_audit_validation` → snapshot → refresh matrix. `only_failing=true` (default) processes only NOT-passing partitions (`checks_failed>0 OR checks_passed=0` — catches stale empties); the non-destructive guard skips passing ones, so it can only improve. **`force=true`** overwrites even passing partitions — needed when the defect is in a **derived** table (e.g. `credit_quality` passes but its derived `bank_audit_stages` fails, so `only_failing` wouldn't select it); the `credit_quality` lane also rebuilds `bank_audit_stages` after the run. **Preferred over `backfill-audit.yml` for a single-lane fix** — one lane on fitz, no full-extract timeout (an all-periods lane run is ~6–10 min). How OCI/CF/NPL/loans_by_stage were fixed fleet-wide |
| Manual only | `purge-partition.yml` | Remove one `(bank, period[, kind])` from the audit lane **everywhere** — local snapshot → D1 → re-uploaded R2 snapshot (`purge_partition.py`), then a coverage re-sync so the cell returns to `missing`. The PDF in R2 is untouched, so the cell reads missing **with** `pdf_present` = "acquired, awaiting extraction"; re-extracting restores it. For an extraction that succeeded and validated **green but is known wrong**, when the fix isn't ready. Deleting from D1 alone is the trap this avoids — the snapshot would keep the rows and the next `push_to_d1` would restore them. Built for **TEB 2026Q2**, whose filing switched from thousands to **millions** of TL: every figure landed 1000× small while every internal identity still footed, so only the fx lane's cross-period anchor saw it. `dry_run=true` (default) is genuinely read-only |
| Manual only | `repair-loans-zeros.yml` | One-time (idempotent) repair of the `loans` table: `_save_loans` used falsy `or` chains, so every BDDK-reported **0** in `total_tl` / `total_fx` / `total_amount` / `npl_amount` / `non_cash_amount` fell through to an absent column and stored NULL. Re-derives the true values from `raw_api_responses` (kept verbatim — nothing is re-fetched): **~44k cells across ~30k rows**, the largest block being consumer-loan FX, where 0 is Decree 32 and not absence. Scraper fixed 2026-08-01; this fixes the history. `dry_run=true` by default and is genuinely read-only. Stamps `downloaded_at` on corrected rows ONLY, so the `--hours 2 --only-tables loans` push carries exactly those rows — **do not widen the window into a full-table push**. Bulletin lane (`bddk-pipeline` group) |
| Manual only | `audit-triage.yml` | **Read-only diagnosis** of the failing audit partitions: `triage_partitions.py` + `watch_cross_period.py` over the R2 snapshot. `bank_audit_validation` says *which* identity broke; this says *why*, assigning a deterministic cause per partition (`dropped_cell` / `missing_row` / `column_slip` / `wrapped_cell` / `anchor_miss` / `drawn_page` / `rotated_page` / `wrong_pdf` / `unit_switch` / `source_defect`) with the page and the printed evidence behind it. **No model is called and no figure is produced.** Writes nothing anywhere — no D1, no row update, no snapshot re-upload, no extractor edit — so it is unaffected by the D1 write freeze; the reports come back as a build artifact. Inputs: `statement`, `bank`, `limit`, `render` (rasterises the page next to each note). The companion cross-period watch is the **only** instrument that can see a reporting-unit change: every in-filing identity is a ratio of figures sharing a scale, which is why the 2026Q2 Bin→Milyon switch footed perfectly while every figure was 1000× wrong. Shares the `bddk-pipeline` group (it reads the snapshot the refresh lanes write) |
| Manual only | `backfill-nonbank.yml` | One-time historical backfill of the non-bank sector lane (leasing / factoring / financing) from `from_year` (default 2020) → now (~5–10 min). The incremental refresh rides `refresh.py`; this is only for the initial history load. Apply migration 0013 first (via a `web/**` deploy) |
| Manual only | `backfill-faaliyet.yml` | Fleet backfill of the Faaliyet-raporu franchise lane (branches / personnel from annual-report PDFs) → `faaliyet_franchise` + `faaliyet_extractions`. The incremental refresh rides `refresh.py` |
| Manual only | `build-products.yml` | Loads the frozen **product-shelf** benchmark (`data/product_benchmark/*.json` + `src/products/labels_en.py` + `profiles_en.json`) via `src.products.build` → `product_attributes` / `bank_products` / `bank_product_profile` → D1 (`--only-tables=product_attributes,bank_products,bank_product_profile`) + snapshot. Deterministic and idempotent (loads committed JSONs, not a scrape); re-run for the same `snapshot_date` replaces its rows. Powers `/products`. Runs the `0034` DDL against remote D1 first (`CREATE … IF NOT EXISTS`), so it is safe to dispatch independently of deploy. NOT the refresh automation (that lane is designed but not built — see [knowledge/turkish-bank-product-benchmark-2026-07-22.md](knowledge/turkish-bank-product-benchmark-2026-07-22.md) §5). Bulletin lane (`bddk-pipeline` group) |
| Manual only | `refresh-transcripts-weekly.yml` | `update_transcripts.py` → `bank_call_transcripts` (earnings-call transcripts for the 8 listed banks that hold an English call) → optional D1 push (`--only-tables=bank_call_transcripts`) + snapshot. Bulletin lane (`bddk-pipeline` group). **Carries no `schedule:` on purpose** — the freeze is enforced by `gh workflow disable`, which is invisible in git, so a new workflow shipped with a cron would be born enabled and become the one lane writing to D1 during it. The `push` input therefore defaults to **false**: a run ingests and re-uploads the snapshot but does not touch D1 unless asked. When the freeze lifts, add `schedule: "0 7 * * 6"` (Sat 07:00 UTC, after `refresh-presentations-weekly`) and flip `push` to true. Inputs: `banks` (ALL/NONE sentinel — a blank dispatch input arrives as the default, not empty), `refresh` (refetch stored quarters; parser changes only), `push`. Source rate-limits at ~70 pages, so the fetcher backs off on 429 and paces at 3s |
| Daily 06:00 UTC | `healthcheck.yml` | D1 freshness check + `verify_chart_spec.py` + `check_amount_integrity.py` + Telegram webhook-target check → Telegram/Discord alert if stale/failing/drifted |
| Manual only | `test-openrouter.yml` | **Scratch probe** for the `OPEN_ROUTER_API` secret. `task=smoke` — auth + credits + DeepSeek price list + a completion through `free_llm.py`'s number validators. `task=usage` — accounting only, spends nothing. `task=regulation` — runs the **real** `summarize_regulations.py` against OpenRouter (repointing the `KIMI_API_URL`/`KIMI_MODEL`/`KIMI_API_KEY` env vars `kimi.py` already reads, so the production prompt is unchanged) with a Kimi A/B on the same section. **Read-only on production**: pulls the R2 snapshot, never uploads one, never pushes to D1. Delete it (+ `scripts/scratch_test_openrouter.py`, `scripts/scratch_dump_briefing.py`, and its `SCRATCH_WORKFLOWS` entry in `scripts/check_pipeline_graph_sync.py`) once the OpenRouter question is settled |
| Manual only | `telegram-webhook.yml` | Register (`set`) / inspect (`info`) / verify (`check`) the Q&A bot webhook. Lives in CI because `TELEGRAM_BOT_TOKEN` + `TELEGRAM_WEBHOOK_SECRET` aren't available locally. Run `set` after anything that moves the site origin — notably a **Worker rename**, which changes the `workers.dev` hostname and silently orphans the webhook |
| After CI passes on `master` | `deploy-cloudflare.yml` | Apply D1 migrations, build OpenNext bundle, deploy to Workers |
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
| `data/bddk_data.db` | BDDK monthly/weekly + EVDS + news + TBB + TKBB + KAP + TEFAS | `state/bddk_data.db.gz` | `bddk-pipeline` |
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
# Audit the archive for WRONG-BASIS PDFs (consolidated file under an
# "unconsolidated" key or vice-versa) — read-only, exits non-zero on any mismatch:
python scripts/sync_audit_reports.py --verify-basis            # all banks
python scripts/build_bank_audit_stages.py --db data/bank_audit.db

# Push new rows to D1 (requires CLOUDFLARE_API_TOKEN)
python scripts/push_to_d1.py --hours 168                      # bulletin/EVDS lane
python scripts/push_to_d1.py --db data/bank_audit.db --hours 168 --table-set audit
```

> **Never hand-list the audit tables.** `--table-set audit` expands to every
> `bank_audit_*` table in `src/audit_reports/registry.py`. The literal list that
> used to sit here named 12 of the 16 — and the copy in `refresh-audit.yml` named
> 14 — so `bank_audit_fx_position` and `bank_audit_repricing` were extracted and
> snapshotted for weeks without ever reaching D1, while the push exited 0.
> `push_to_d1` now hard-errors on a table it cannot sync.

> First-time local audit run: seed the standalone DB from the combined one with
> `python scripts/seed_audit_db.py`. It seeds statement rows only — never the
> extraction log, which would make the restore skip the re-extraction it exists
> to trigger.

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
`python scripts/diagnostics/validate_discovery.py` (it checks discovery against
the config) and add any passing ticker to `DISCOVERY_BANKS`. See
[ADMIN.md](ADMIN.md) §Auto-discovery.

### Narrative prose lane — local backfill, deferred D1 push

`bank_audit_prose` is extracted and validated **locally**, into its own SQLite
file, and has deliberately **not been pushed to D1** (the write freeze stands).

```bash
python scripts/backfill_prose.py                    # whole R2 fleet -> data/bank_audit_prose.db
python scripts/backfill_prose.py --only-bank GARAN  # one bank
python scripts/backfill_prose.py --local-dir data/eye   # no network
```

Idempotent and resumable — a partition that already has rows is skipped unless
`--force`, so an interrupted run continues where it stopped. Roughly 1.7 s per
filing at the default 6 workers.

**Why its own file, not `data/bank_audit.db`.** `apply_overrides` and every
refresh workflow OVERWRITE the lane snapshot from R2. Prose rows written into the
snapshot would be destroyed by the next pull with no error. `data/bank_audit_prose.db`
is gitignored and self-contained.

**When the freeze lifts**, merge and push — do NOT re-extract:

```bash
sqlite3 data/bank_audit.db "
  ATTACH 'data/bank_audit_prose.db' AS p;
  INSERT OR REPLACE INTO bank_audit_prose SELECT * FROM p.bank_audit_prose;
  INSERT OR REPLACE INTO bank_audit_validation
    SELECT * FROM p.bank_audit_validation WHERE statement='prose';"
python scripts/push_to_d1.py --only-tables=bank_audit_prose,bank_audit_validation
```

Apply migration `0035_bank_audit_prose.sql` first (it rides a `web/**` deploy).
Budget: ~330k rows ≈ **$0.33** one-off at D1's $1/M rows written; re-runs write
only what changed. Nothing else in the lane costs anything — extraction is
deterministic and uses no model.

**Automation is not wired yet.** The intended shape is a `statement=prose` run of
`reextract-statement.yml` (the lane is already registered there and in
`push_to_d1`), plus a step in `sync_audit_reports.py` so a newly synced PDF gets
its prose in the same pass.

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

### BIST equity market — REMOVED 2026-08-01

The Yahoo-sourced BIST lane (daily EOD prices, dividends, shares outstanding) was
removed: Yahoo's terms forbid redistribution outright and prohibit automated
access. Both the scraper and every serving path are deleted, so there is nothing
to operate here. The `bist_prices` / `bist_dividends` / `bist_shares` tables
still exist in D1 with their history — nothing reads them, and `bot-sql.ts`
denies them to the public Q&A bot by name. Do not re-enable a fetch without a
licensed feed. Detail: METRICS.md §17.

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
3. Test locally first: `cd web; npx wrangler d1 migrations apply bddk-data --local`.

`scripts/archive/generate_d1_migrations.py` was a one-time D1 seed (writes to
`web/seeds/`, gitignored) — **not schema, and no longer part of any lane**.
Routine row updates go through `push_to_d1.py`.

### Rebuild the public-API series catalog

The public API (`/api/v1`, see [API.md](API.md)) serves only what's listed in the
`api_series` catalog. **Both** BDDK ingest workflows rebuild and push it:
`refresh-bddk-bulletins.yml` (daily monthly-probe / Friday weekly — the runs that
actually land new periods) and `refresh-data.yml` (Saturday). The steps below are
for out-of-band rebuilds.

> Rebuilding only in the Saturday run left `/serieList` advertising an
> `end_date` up to a week behind what `/series` would actually return. The
> catalog must be rebuilt by whichever workflow lands new BDDK data.

```bash
python scripts/build_api_catalog.py --dry-run          # report; changes nothing
python scripts/build_api_catalog.py                    # write data/bddk_data.db
python scripts/push_to_d1.py --only-tables api_series  # publish
```

`api_series` is a **full-rebuild** table (no per-row timestamp), so a windowed
push skips it — it must be named in `--only-tables` or it never reaches D1.

Two things to watch in the build output:

- **`WARNING: N previously published codes no longer resolve`** — a code someone
  may have hardcoded has stopped working. Expected when BDDK retires a line;
  investigate if unexplained.
- **`excluded: N USD-basis series`** — normal. BDDK's USD-converted variant
  covers one month against 76 of TL, so it's excluded by `INCLUDE_USD_BASIS`.

New BDDK data extends existing series and may add new ones; **codes are carried
forward and never renumbered**, so a rebuild on unchanged data is a no-op.

### Refresh the English labels

`api_series.item_name_en` holds **BDDK's own English labels**, not translations:
BDDK serves the monthly bulletin at `.../BultenAylik/en/...` with identical rows
in identical order. `scripts/fetch_bddk_english_labels.py` caches them to
`data/bddk_labels_en.json`, which the catalog builder joins on
`(table_number, item_order)`.

```bash
python scripts/fetch_bddk_english_labels.py --check   # report drift, write nothing
python scripts/fetch_bddk_english_labels.py           # refresh the cache
python scripts/build_api_catalog.py                   # then rebuild + push as above
```

The cache is committed, so the catalog build stays offline and deterministic.
Only re-run this when BDDK changes the report template — the build prints
English coverage (currently 98.1% of monthly series) and a drop is the signal.

⚠️ **Never machine-translate this column.** These are regulatory line items
where an invented rendering would quietly misname a supervisory concept. Where
BDDK publishes no English the value is NULL and consumers fall back to
`item_name`: all weekly datasets (BDDK has no English weekly bulletin), plus the
`other_data` lines whose `item_order` collides — the builder drops those rather
than risk attaching the wrong term to one of a colliding pair.

### Cloudflare Configuration Rule: BIC off for `/api/v1` (load-bearing)

Cloudflare's **Browser Integrity Check** rejects known-bot user agents with
`403` / **Cloudflare error 1010** *before the request reaches the Worker*.
Python's stdlib default (`Python-urllib/3.x`) is caught — and `pandas.read_csv`
fetches URLs through stdlib `urllib`, so reading a CSV URL into a DataFrame, the
most natural way to consume this API, was failing. `requests`, `httpx`, `curl`
and browsers were never affected.

Fixed 2026-07-19 by a **Configuration Rule** (dashboard → `carthago.app` →
Rules → Configuration Rules), named `API v1`:

> expression: `starts_with(http.request.uri.path, "/api/v1")`
> setting: **Browser Integrity Check = Off**

Verified after deploy: `/api/v1/*` returns 200 to `Python-urllib`, while `/`
still returns 403 to it — bot protection intact everywhere except the API path.

⚠️ **This rule is part of the API's contract.** If it is deleted or its
expression broken, every stdlib-`urllib` and `pandas.read_csv` caller starts
getting 403s while `curl` keeps working — so it fails invisibly to anyone
testing with curl.

`healthcheck.yml` watches it daily via `scripts/check_public_api.py`, which
probes with stdlib `urllib` (i.e. the blocked user agent) on purpose and alerts
naming this rule. **Don't "fix" that script to use `requests` or to set a
User-Agent** — either change makes it pass unconditionally and the check
becomes decorative. To check by hand:

```bash
python scripts/check_public_api.py     # all four probes, exit 1 on failure
```

It is a **zone** setting: the repo's `CLOUDFLARE_API_TOKEN` is scoped to
Workers/D1/R2 and cannot read or change it. Do **not** disable BIC zone-wide
instead — that would drop bot protection on the whole dashboard. Note also that
a WAF *skip* rule does not bypass BIC; it must be a Configuration Rule.

### D1 write budget

D1 bills **rows written**: the Workers Paid plan includes 50 million a month and
charges **$1.00 per million** after that. Rows *read* are $0.001 per million —
a thousandth the price. Two consequences worth internalising:

- **`rowsWritten` is not "rows you changed".** It counts `DELETE` and `UPDATE`
  as well as `INSERT`, and it counts **index maintenance**. Measured on this
  database: one override push reported 392,363 rowsWritten against 107,636
  actual changes — a **3.6x** multiplier. Every logical write avoided is worth
  about 3.6 billed ones.
- **Reads are essentially free by comparison.** Preferring a read that avoids a
  write is almost always correct, at a 1000:1 price ratio.

Check current usage (needs `CLOUDFLARE_API_TOKEN` + `R2_ACCOUNT_ID`):

```bash
# rowsWritten / rowsRead per day per database, last 14 days
python - <<'EOF'
import os, json, urllib.request, datetime
tok=os.environ["CLOUDFLARE_API_TOKEN"]; acc=os.environ["R2_ACCOUNT_ID"]
end=datetime.datetime.now(datetime.UTC).date(); start=end-datetime.timedelta(days=14)
q=("query($acc:String!,$start:Date!,$end:Date!){viewer{accounts(filter:{accountTag:$acc})"
   "{d1AnalyticsAdaptiveGroups(limit:200,filter:{date_geq:$start,date_leq:$end})"
   "{dimensions{date databaseId} sum{rowsRead rowsWritten}}}}}")
req=urllib.request.Request("https://api.cloudflare.com/client/v4/graphql",
  data=json.dumps({"query":q,"variables":{"acc":acc,"start":str(start),"end":str(end)}}).encode(),
  headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"})
for r in json.load(urllib.request.urlopen(req))["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]:
    print(r["dimensions"], r["sum"])
EOF
```

⚠️ **The account hosts more than one D1 database.** `bddk-data` is this project;
`gazelhan` is not, and was ~14% of the account's writes and half its reads when
this was last measured (2026-07-27). Attribute before optimising.

⚠️ **Measure month-to-date; never extrapolate a short window.** Writes here are
extremely bursty — an audit campaign day is 20-30x a quiet one. Scaling a
fortnight that happened to contain three campaign days to a month overstated the
bill by 4x (claimed $72, actual $18). The query above already returns per-day
rows: sum the calendar month, do not multiply an average.

**Measured 2026-07-01 → 07-27** (27 days, the whole month to date): 68.1M rows
written account-wide (bddk-data 58.6M + gazelhan 9.5M) against the 50M included —
**18.1M over, ~$18**. The QUIET-day baseline is flat and cheap: Jul 6-10 ran
486,892 / 487,107 / 488,156 / 484,448 / 487,011 rows a day, i.e. ~14.6M a month,
comfortably inside the allowance. **The entire overage is campaign days** — Jul
15 (12.4M), Jul 17 (15.1M) and Jul 26 (9.4M) alone are 36.9M of the 68.1M.

**The guard: `push_to_d1.py` prices every push before it runs.**

Added 2026-08-04, because the two rules below only ever made the *quiet* days
cheap. Every campaign day that blew the allowance ran to completion without
announcing what it was about to write, and nothing stopped it. Now:

- **The estimate is printed on every push**, with a per-table breakdown. Billed
  rows are estimated structurally — `1 + index_count` per row, doubled for a
  full rebuild's `DELETE` — which lands near the measured 3.6x for the usual
  table mix. It is an estimate for authorising a push, never a report of spend;
  read actuals from the analytics query above.
- **A single row over D1's 100,000-byte statement limit fails locally**, naming
  the table and row, instead of shipping a file doomed to return a bare
  `SQLITE_TOOBIG`. Byte-sized batching handles every other case, but no batch
  size can send one oversized row: D1 permits a 2 MB *row* and caps a
  *statement* at 100 KB, so a value in between has to go to R2 with a reference
  kept in D1, or be split.
- **A push over `--max-billed-rows` FAILS (exit 3)**, it does not warn. Default
  **2,500,000**: a whole-audit-corpus push is 1,678,540 and the pending one-off
  prose push is 1,110,204, so both clear it, while July's smallest campaign day
  (9.4M) does not. Raise it deliberately — and because the number then lives in
  the workflow file, the cost is reviewable in a diff instead of discovered on
  the invoice.
- **The cap tightens itself as the cycle fills.** Before pushing, the script
  reads rows-written for the current cycle from `d1AnalyticsAdaptiveGroups`
  (needs `CLOUDFLARE_API_TOKEN` + `CF_ACCOUNT_TAG`/`R2_ACCOUNT_ID`; skipped when
  absent, or with `--no-cycle-check`). The cap becomes
  `min(declared, max(remaining_headroom, 250,000))` — so 100k of headroom left
  will **not** wave a 2.5M push through to land 2.4M past the allowance, which
  the first version did: the guard would have "passed" the very run that blew the
  budget. The 250,000 floor keeps routine crons alive when headroom is gone;
  campaigns wait for the 11th. Freezing everything was July's *other* mistake:
  four days with nothing watching the data, for a bill the crons were not causing.
- **An unreadable API means unknown, not zero.** The cycle reading returns `None`
  on any failure and the declared cap is used unchanged — it neither relaxes nor
  tightens. A missing reading reported as "plenty of headroom" is precisely the
  silent-wrong shape this repo keeps rediscovering.

Pinned by `tests/test_d1_write_budget.py` (cycle boundary is the 11th, a spent
cycle never *raises* a lower declared cap, a dead API cannot take the push down).

⚠️ The per-push cap bounds **one invocation, not a day**. July's campaign days
were several pushes each and no single one would have tripped 2.5M — the
cycle-aware layer is what closes that, and it only works where the analytics
credentials are present.

**Partition digests: a campaign costs what it CHANGED, not what it touched.**

The guard above makes a campaign *declared*. This makes it *cheap*. The windowed
`bank_audit_*` tables key on the extraction stamp, so re-running the fleet after
an extractor fix re-pushed every partition it touched — including every partition
the fix did not alter. Each `(table, bank_ticker|period|kind)` now carries a
digest of its own rows in `d1_pushed_partitions` (staging DB, rides the R2
snapshot, same as `d1_push_state`), and an unchanged partition is not emitted.

Measured on the real balance-sheet corpus (1,050 partitions / 182,141 rows):

| Campaign | Rows pushed before | After |
|---|---:|---:|
| Re-extraction that changed nothing | 182,141 | **0** |
| Re-extraction that fixed one cell | 182,141 | **181** (1 partition) |

⚠️ **The skip is OPT-IN (`--skip-unchanged-partitions`).** A plain windowed push
is upsert-only, so silently declining to send partitions for a caller that did
not ask for it is the wrong default. Only `refresh-audit.yml` opts in. Targeted
repairs do not use it at all — they use explicit replacement, below.

When it IS on, the push **owns the partition end to end**: it emits its own
scoped `DELETE` for the changed partitions followed by their current rows, in the
same wrangler file (which executes atomically and rolls back as a unit). Without
that delete the push only upserts, so a row a re-extraction *removed* survives in
D1 — and its digest is then recorded as synced, leaving the partition silently
divergent for good. The deletes are chunked to stay under the statement limit;
the fleet gains 76 partitions a quarter and one statement would eventually breach
it.

Rules that keep it safe, each pinned by a test in `tests/test_d1_write_budget.py`
— several of which **replay the emitted SQL against a simulated remote and assert
it equals local**, because "an INSERT was emitted" was never the question:

- A partition with **no stored digest is always sent** — missing state means
  "send it", never "assume it landed". A reseeded staging DB pushes once.
- Digests are recorded **only after wrangler succeeds**, like the content hash;
  generating the SQL persists nothing.
- Stamp columns (`extracted_at`, `validated_at`, `derived_at`, `downloaded_at`)
  are **excluded** — a re-extraction bumps them on purpose, and including them
  would make every partition look changed and defeat the whole mechanism.
- A partition that **lost** a row counts as changed, and converges remotely.
- A partition that lost **every** row is found via `bank_audit_extractions` — with
  no rows left it is invisible to anything keyed on rows currently present, and
  the log was the only record that it had been touched. Scoping to the log's
  window is what makes that safe: comparing *all* stored keys against a windowed
  view would delete every historical partition merely out of window. Such a push
  is **DELETE-only**, and `total_inserts == 0` no longer discards it.
- An unchanged partition emits **no DELETE either** — clearing something the push
  then declines to re-insert is the failure this whole design exists to avoid.
- The estimate prices **both sides**. Skip mode emits DELETE *and* INSERT and D1
  bills both, so pricing the insert alone understated a replacement by half and
  an emptied partition at zero. `d1_pushed_partitions.row_count` records what D1
  holds, because a shrunk partition no longer has the rows locally to count.
- `--resend-partitions` is the deliberate-repair mode: resend everything **and**
  leave the digest state current, so the next opt-in run does not re-push it all
  again. (Simply omitting the opt-in flag pushes everything but records nothing.)

### There is no clear-then-push any more

Every audit repair tool used to issue a remote `DELETE` and then launch
`push_to_d1` as a second process. Anything between the two — a guard refusal, a
SQL error, a network blip, a cancelled runner — left the partitions deleted with
nothing local aware they needed restoring.

**A preflight cannot fix that**, and the earlier claim here that the two "cannot
disagree" was wrong: two remote calls cannot be made atomic, the cost guard reads
cycle usage independently in each, and headroom genuinely moves between them. An
accepted check could still be followed by a refused push *after* the delete.

`audit_d1.replace_partitions(parts, db, tables)` is now the only path.
`push_to_d1 --replace-partitions <file>` takes an explicit
`bank|period|kind` list, emits the scoped `DELETE`s and the current rows into
**one** file, prices the whole file under **one** guard, and lets wrangler execute
it as a unit that rolls back on failure. A partition is replaced or untouched.

Selection is explicit — neither the time window nor `bank_audit_extractions` is
consulted — so a partition holding zero rows locally is still cleared remotely.
Migrated: `apply_overrides.py`, `load_partition.py`, `reextract_pl.py`,
`push_from_scratch.py`, `backfill_extraction.py`, and both `audit_d1` helpers.
`purge_partition.py` is deliberately out of scope: destroying rows is its job.

**Replacement must name its tables.** `--replace-partitions` requires
`--only-tables` or `--table-set` and rejects any table that cannot honour it (a
full-rebuild rollup, or one without `bank_ticker/period/kind`). Without that a
replacement fell through to every *other* table's ordinary window — an AKBNK
repair emitted an unrelated recent `loans` row. `_NO_PARTITION_SKIP` suppresses
the digest **skip** only, never the selection: while it also disabled selection,
replacing AKBNK emitted GARAN's `bank_audit_extractions` row and no scoped
DELETE.

**Pricing a DELETE has exactly three sources, and no fourth.** The recorded
`row_count`; failing that the local count, valid **only when the digest matched**
— equality is what proves local and remote agree, so a partition shrunk from 100
rows to 1 has a *different* digest and its single row says nothing about what D1
holds; failing that D1 itself, since a read is a thousandth the price of a write.
If none can answer, the push **refuses**, and no flag overrides it — the number
is unknown, not merely large. Assuming one is how a 100-row delete got priced at
one row, and the guard then waves through the very push it exists to stop.

**The estimate covers the whole generated file, including the outbox.** Queued
`d1_pending_deletes` statements execute, so they are priced (one PK-scoped row
each, the outbox's contract) and a statement with no `WHERE` is refused outright
rather than replayed. Explicit replacement leaves the outbox alone entirely:
those entries belong to other lanes and must not ride along in a targeted repair.
- ⚠️ **`bank_audit_extractions` is exempt.** It is the extraction *log*: its job
  is to record that an extraction ran, and `extracted_at` — the fact it exists to
  carry — is excluded from every digest. Skipping it would freeze D1's audit
  trail while the rows it describes had genuinely been re-extracted. 1,050 rows;
  pushing it always is cheap and correct.

**And the bill is now watched.** `healthcheck.py` reads the cycle's rows-written
and alerts at **80%** of the allowance, not at 100% — at 100% the only choices
left are stop or pay. It stays **silent when the reading is unavailable**: an
alert that fires on its own blindness gets muted, and a muted alert is worse than
none. Needs `R2_ACCOUNT_ID` (account tag) beside `CLOUDFLARE_API_TOKEN` in
`healthcheck.yml`. The shared reader is `src/d1_usage.py`, stdlib-only so the
minimal-deps health-check job can import it.

**The two rules that keep the bill down**

1. **Never re-stamp a row that did not change.** `push_to_d1` windows on
   `downloaded_at`, so a scraper that re-fetches history and rewrites it
   identically re-pushes the whole table. **Any lane that re-fetches an
   overlapping window has this bug until it is shown not to** — the run succeeds,
   the data is correct, and only the bill moves. Three lanes have carried it:

   | Lane | Why it re-fetches | Waste before the fix | Fixed |
   |---|---|---|---|
   | `evds_scraper.fetch_one` | no incremental endpoint — pulls each series back to 2018 every run | 52,828 of 53,521 rows looked new **daily**, ~17M rows/month | 2026-07-27 |
   | `weekly_api_scraper.fetch_and_store` | the BDDK weekly API only serves a trailing **13-week** window | ~26,600 rows a run, of which 12/13 (~24,550) unchanged; 4 runs/week ⇒ **~1.5M billed writes/month** | 2026-08-04 |
   | `tefas.loader.upsert_day` | `update_tefas.py` re-fetches a trailing **7-day** window every day | ~2,150 rows/day, 6/7 unchanged ⇒ **~0.2M billed writes/month** | 2026-08-04 |

   All three now compare the stored tuple before writing, so an unchanged row
   keeps its old `downloaded_at` and the push window never sees it. A revision, a
   rebase or a new period still writes, because the tuple differs. A settled
   series reporting **0 rows written is the healthy reading** — the weekly
   scraper's `stats` prints `same=` beside `rows=` so the saving is visible in
   the Actions log, and `same` collapsing to ~0 means either the upstream
   restated the whole window or the comparison broke.

   `tests/test_d1_write_economy.py` is the gate: a second identical ingest must
   write nothing, and a genuine revision must still land.

   ⚠️ **Fixing a lane changes what its freshness check means — retune it in the
   same commit.** `MAX(downloaded_at)` stops answering "did the cron run" and
   starts answering "did new data land", so a threshold sized for the cron will
   cry wolf on the source's real cadence. Both `scripts/healthcheck.py`
   (`THRESHOLDS`) and `web/app/lib/admin-health.ts` read these columns and both
   must move. Weekly went 192h → **312h** on 2026-08-04: measured over 341
   publication gaps since 2019-11, 307 are exactly 7 days but 17 run longer, to a
   maximum of 11 (public holidays) — 8 days would have alerted ~2.5x a year for
   nothing. EVDS and TEFAS took the other route and switched to `MAX(<data
   date>)` instead. Either is fine; leaving the old threshold is not.

   ⚠️ **This class is the flat daily baseline, not the overage.** Together the
   weekly + TEFAS fixes take ~1.7M/month off a ~14.6M/month quiet baseline. The
   50M is blown by **campaign days** (Jul 15/17/26 alone were 36.9M of 68.1M) —
   backfills, re-extractions and override pushes. Fixing scrapers does not
   address those; budgeting the campaign does.
2. **Full-rebuild tables carry a content hash.** `api_series` (19,787 rows,
   rebuilt on the DAILY bulletin cron) and the audit spine
   (`bank_audit_coverage`, 18,936 rows, on every audit and override run) emit
   `DELETE` + `INSERT` for every row. `push_to_d1` now hashes the local contents
   against what it last pushed and skips entirely when nothing moved. Build-stamp
   columns (`built_at`, `downloaded_at`, …) are excluded from the hash — without
   that the skip could never fire, because `build_api_catalog` re-INSERTs without
   naming `built_at` and it takes a fresh `CURRENT_TIMESTAMP` on every run.

   The state lives in `d1_push_state` in the **staging** DB, which rides the R2
   snapshot. A fresh or reseeded staging DB has no state and pushes once — the
   safe default. The skip trusts that the last successful push landed, so after
   editing D1 by hand use **`push_to_d1.py --force-rebuild`** to resync.

**Freshness after the EVDS change.** `MAX(downloaded_at)` on `evds_series` now
means "when the data last moved", not "when the cron last ran", so both
`scripts/healthcheck.py` and `/admin` judge EVDS on **`MAX(period_date)`** with a
threshold that survives a long weekend (120h / a 3-day cadence). That is the
same treatment TEFAS already had, for the same reason — and it is strictly
better, because a data date catches a genuine TCMB publishing break while a
download stamp never could.

**`apply_overrides.py` pushes only what changed (fixed 2026-07-27).** It
re-applies every override on every run — that is what makes it idempotent — so
almost all of the ~216 named partitions were being rewritten with the values they
already held, then cleared from D1 and re-pushed regardless. Two runs earlier
that day wrote ~632,000 rows between them to correct **five cells**.

It now fingerprints each partition across every audit table *before* applying and
*after* revalidating (`_partition_digest`, timestamp columns excluded — they are
what the script bumps on purpose), and clears + pushes only the partitions whose
contents actually moved. An idempotent re-run costs **nothing**: no D1 write, no
R2 upload. Measured back-to-back on the real snapshot: `207 of 216 changed` on a
run with a pending validator change, then `0 of 216` on the next.

Two properties worth keeping in mind:
- **A validator change is a real change.** `bank_audit_validation` and
  `bank_audit_pl_roles` are inside the digest, and every partition is revalidated
  before the comparison — so editing a check correctly marks the partitions whose
  results moved, and they do get pushed.
- **The digest must ignore `extracted_at`/`validated_at`/`derived_at`.** Those are
  precisely what the script bumps to select rows for the `--hours 1` push window;
  including them would make every partition look changed and silently restore the
  old cost.

Audit campaigns remain where the bulk of this database's writes come from — two
days of lane work (2026-07-15/17) were 27.5M of that month's 68.1M.

### ⚠️ The billing cycle is NOT the calendar month

Confirmed on the dashboard 2026-07-28: this account's cycle runs **the 11th to
the 10th** (the period labelled "Aug 2026" is **Jul 11 → Aug 10**, 31 days). The
GraphQL query above defaults to whatever window you give it — give it the
**cycle**, not the month, or every projection is wrong at both ends. Cross-check:
Jul 11–27 summed 61,682,243 locally against the dashboard's 61.68M, exact.

Also note the dashboard's **projected cycle cost is structurally low**. It is
`average daily cost × cycle days`, and that average is diluted by the days that
cost $0 because they were still inside the 50M allowance. Once the allowance is
spent, every subsequent day bills at full rate, so project bottom-up from the
day-shapes (quiet weekday ~0.5–0.9M, Friday ~2M, Saturday ~3M, Sunday ~2.4M).

### Cron freeze 2026-07-28 → FULLY LIFTED 2026-08-04

**Current state: nothing is frozen.** All ten lanes are back on their schedules,
recorded in `data/workflow_state.json` and verified against the live API by
`scripts/check_workflow_state.py` on every CI run — which prints the frozen set,
so "0 frozen" is asserted rather than assumed.

`refresh-evds-daily` was the last one back. Keeping it weekly-only would have
been a false economy twice over: the re-stamp bug that made the lane expensive
was fixed on 2026-07-27 (it now writes only series whose value moved), and EVDS
carries genuinely daily data — FX, the policy rate and CBRT funding are ~2,116
daily observations each. A Saturday-only refresh would also have pushed age past
**both** freshness thresholds (`healthcheck.py` 120h, `admin-health.ts` 3-day
cadence ⇒ amber past 4.5 days) by every Thursday, i.e. a false Telegram alert
most weeks. Both thresholds are correct as written **for a daily EVDS cron** — if
that cron is ever switched off again, retune them in the same change.

Note `refresh-data.yml` (Sat 03:00) also refreshes EVDS: it runs
`scripts/refresh.py` without `--skip-evds`. Post-fix that Saturday overlap finds
nothing changed and costs ~nothing, so the redundancy is harmless — but it is why
disabling the daily lane does **not** stop EVDS refreshing.

<details><summary>Why the freeze happened, and why it ended</summary>

The 50M allowance for the Jul 11 → Aug 10 cycle was exhausted on Jul 26, so ten
scheduled workflows were disabled via `gh workflow disable` — a change that
leaves **no trace in git**, which is why `scripts/check_workflow_state.py` and
`data/workflow_state.json` now exist. On 2026-08-01 the freeze was extended
indefinitely; on 2026-08-04 it was lifted.

What changed in between is that the cost was finally attributed. The overage was
never these lanes: it came from **backfill campaigns** (36.9M of July's 68.1M
rows on three days), against a quiet baseline of ~14.6M/month. And the part of
that baseline which *was* avoidable turned out to be one bug in three places —
EVDS, weekly and TEFAS each re-stamped unchanged rows and re-shipped them to D1.
With all three fixed the baseline is roughly **7M/month against 50M included**,
so the crons cost about 15% of the allowance and the freeze had nothing left to
defend. See *D1 write budget* above.

Freezing `healthcheck` with the rest meant **nothing was watching data freshness
or extraction failures** for four days. Re-enable it first in any future freeze,
or accept that consequence explicitly.

</details>

To freeze again, or to thaw the remaining lane — **update the registry in the
same commit or CI fails**, which is the whole point of the gate:

```bash
gh workflow enable  refresh-evds-daily.yml     # or `disable` a lane
python scripts/check_workflow_state.py         # will fail until the JSON matches
```

**`refresh-news-daily` deliberately keeps running.** Every other lane reads an
archive and heals on resume — EVDS is a historical API, BDDK bulletins stay on
BDDK's site, audit PDFs stay on the banks' sites — so a pause defers their writes
into the next cycle rather than losing anything. News does not: KAP, Google News
and the press feeds are **windowed**, they only surface recent items, and an item
that scrolls out during a freeze is gone for good. A 13-day hole in `news_items`
would be permanent and would show on `/actions` and the per-bank news tabs
forever. It is also the cheapest of the daily jobs. Never freeze this one.

Consequences to expect while frozen: `/admin` freshness goes red across the
board (that is the freeze, not a break), no Telegram bulletin pings, and the
monthly BDDK bulletin — which lands mid-month on no fixed day — is picked up
whenever the daily probe resumes rather than the day it publishes.

**Publishing a release during the freeze** (done for 2026-06 on 2026-07-30 —
BDDK published while frozen and the site would otherwise have shown May until
Aug 11). Enable, dispatch, re-disable — the freeze stays intact, and only the one
release is paid for (~8.5k rows):

```bash
gh workflow enable  refresh-bddk-bulletins.yml
gh workflow run     refresh-bddk-bulletins.yml -f skip_monthly=false -f skip_weekly=true
gh run watch <id> --exit-status          # ~10 min for a landing run (~6 min when it only probes)
gh workflow disable refresh-bddk-bulletins.yml
```

Then three things the crons would normally have done, in this order:

1. **Purge the KV cache** — `/admin` → *Purge cache*, or the REST recipe (`wrangler
   kv bulk delete` crashes on Windows). Public pages cache D1 reads 12h, so the
   new month does not appear until this runs. Page prose needs nothing else: the
   takeaways are computed from D1 at render (`insights.ts`), so they re-derive.
2. **`python scripts/healthcheck.py`** — repoints `source_freshness` (frozen
   `healthcheck` is what normally writes it) so `/admin` isn't red on data we hold.
   On Windows prefix `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`; the console codec
   breaks both the wrangler read-back and the ✅ summary otherwise.
3. **`generate-reads`** (enable → run → disable) — new facts flip `det_hash`, so
   every tab silently falls back to its deterministic headline until this reruns.
   Must come **after** the purge: the generator reads `/api/reads` from the live
   site, so a pre-purge run rewrites the *previous* month's takeaway.

⚠️ **The campaigns are the cost centre, and they are all manual dispatches.**
`backfill-*`, `refresh-audit`, `reextract-statement`, `purge-partition`,
`build-products` and `apply_overrides.py` are $9–15 a run once a cycle's
allowance is spent — that is what blew July, not the crons. Thawing the schedules
did not change this: budget a campaign before dispatching it, and prefer
`only_failing` over `force`.

⚠️ **The Jul 11 → Aug 10 cycle is still the exhausted one.** It ran out on Jul 26,
so everything written until Aug 11 bills at full rate. The thawed crons add
~240k rows/day ≈ **1.7M rows ≈ $1.70** for the rest of this cycle — immaterial,
and the reason the thaw did not wait for the reset. A campaign in the same window
is not immaterial.

⚠️ **`gazelhan` is ~340k rows/day of the same account allowance and is not this
project.** It cannot be frozen from this repo. It was ~$4.40 of the remaining
13 days' spend — worth dealing with at the source.

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

> Kept honest by `scripts/check_docs_sync.py` (CI): every `secrets.X` / `vars.X` a
> workflow reads must appear below, and every optional key of `CloudflareEnv` must
> appear in this doc, [ADMIN.md](ADMIN.md), or [TELEGRAM_BOT.md](TELEGRAM_BOT.md).
> An undocumented secret is a lane that dies silently on re-provision.

GitHub repo → Settings → Secrets and variables → Actions:

| Secret | Used by |
|---|---|
| `CLOUDFLARE_API_TOKEN` | wrangler (D1 push, dashboard deploy) — 13 workflows |
| `EVDS_API_KEY` | TCMB EVDS API (`refresh-data.yml`, `refresh-evds-daily.yml`) |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | audit-report PDFs in R2 |
| `TELEGRAM_BOT_TOKEN` | `scripts/notify.py` — the ❌/🟡/🆕 alerts every workflow posts on failure |
| `TELEGRAM_CHAT_ID` | ditto — the destination chat |
| `TELEGRAM_WEBHOOK_SECRET` | `telegram-webhook.yml` (`set`) — **must be byte-identical to the Worker secret of the same name**, which is what verifies each inbound update. Rotating means writing both sides together, then re-running `set` |
| `ALERT_WEBHOOK_URL` | ditto — optional Discord/Slack webhook mirror of the same alerts |
| `CEREBRAS_KEY` | "The Read" headline lane (`generate-reads.yml` → `src/news/free_llm.py`) |
| `GROQ_API_KEY` | ditto — the other free provider |
| `OPEN_ROUTER_API` | OpenRouter (DeepSeek et al). Added 2026-07-05 and **unused by any lane** — read only by the scratch probe `test-openrouter.yml`. ⚠️ Note the name: no `_KEY` suffix, unlike every other provider secret |
| `KIMI_API_TOKEN` | weekly regulation briefing (`summarize-regulations.yml`). ⚠️ **Name mismatch**: the repo secret is `KIMI_API_TOKEN`, but the workflow maps it to env `KIMI_API_KEY`, which is what `src/news/kimi.py` reads. Provision the *secret* under the token name |

### Workflow env keys (not secrets, not Worker bindings)

`check_docs_sync.py` covers `secrets.X` and `CloudflareEnv` keys; a plain `env:`
value on a step is invisible to it. AGENTS.md still requires every env key the
code reads to be named here, and this one is load-bearing.

| Env key | Used by |
|---|---|
| `D1_RUN_LEDGER` | Path to a per-RUN file that `scripts/push_to_d1.py` debits before each write, so the 250,000 emergency cap bounds the whole workflow rather than each push. Applied per invocation it did not: the 2026Q2 audit refresh sent 203,799 then 226,069 estimated billed rows, each "under the cap", 429,868 for the run. Every pushing step in a job must be given the **same** run-scoped path (`${{ runner.temp }}/d1_run_ledger.json`) — `tests/test_workflow_ledger_wiring.py` fails the build otherwise. It also changes retry semantics: while it is set, `scripts/audit_d1.py` treats `EXIT_PUSH_FAILED` as terminal, because the estimate is booked *before* wrangler runs and nobody can observe whether a half-finished import billed. Unset = no ledger, per-push cap, exit 4 retryable as before. Wired in `refresh-audit.yml`, `refresh-bddk-bulletins.yml`, `refresh-data.yml` |

Actions **variables** (same screen, "Variables" tab — not secrets):

| Variable | Used by |
|---|---|
| `SITE_URL` | `generate-reads.yml` — the dashboard base URL "The Read" fetches; falls back to the prod URL when empty |
| `BRIEFING_LLM` | `summarize-regulations.yml` — which LLM runs the weekly briefing: `kimi` (default, current) or `deepseek-flash` (OpenRouter, pinned to the `Baidu` upstream). **Switching the scheduled lane is this one field** — no code change, no deploy. A dispatch `llm` input overrides it for a single run without making it stick. Unset = `kimi`. `deepseek-flash` needs the `OPEN_ROUTER_API` secret |

### Worker secrets (dashboard / `/admin` / bot)

Set on the Worker — Cloudflare → Workers & Pages → `carthago`
→ Settings → Variables and Secrets (or `cd web; npx wrangler secret put NAME`).
Declared (and commented) in `web/cloudflare-env.d.ts`; all optional — each feature
degrades gracefully when its key is unset:

| Secret | Used by |
|---|---|
| `ADMIN_PASSWORD` | unlocks `/admin` (password login) — **required to open /admin** |
| `ADMIN_DEV_BYPASS` | skips `/admin` auth for local dev — **never set in production** |
| `GITHUB_DISPATCH_TOKEN` | `/admin` run status + trigger buttons (fine-grained PAT, Actions: read+write) |
| `CF_ANALYTICS_TOKEN` | `/admin` traffic panel (optional) |
| `TELEGRAM_BOT_TOKEN` | the Q&A bot's Telegram API calls |
| `TELEGRAM_WEBHOOK_SECRET` | matched against the `setWebhook` secret_token on every update |
| `OPEN_ROUTER_API` (or `OPENROUTER_API_KEY`) | **the bot's primary LLM provider since 2026-08-01** — OpenRouter, `nvidia/nemotron-3-super-120b-a12b:free`. ⚠️ The identically-named **Actions** secret does not reach the Worker; set it separately with `wrangler secret put OPEN_ROUTER_API`. While unset the provider is skipped and the chain starts at Groq, so the bot keeps answering — just not on Nemotron. ⚠️ The `:free` suffix in the model id is load-bearing: the paid twin is a different id and would bill |
| `GROQ_API_KEY` (or `GROQ_API_TOKEN`) | the bot's first fallback LLM provider |
| `CEREBRAS_KEY` (or `CEREBRAS_API_KEY`) | the bot's second fallback LLM provider |
| `BOT_PER_CHAT_DAILY` / `BOT_GLOBAL_DAILY` | usage caps (defaults 20/chat, 300 global, per UTC day) |
| `BOT_TEST_KEY` | enables `GET /api/admin/bot-ask` (the bot test harness); **404s while unset** |
| `PUBLIC_API_DISABLED` | kill switch for the public `/api/v1` data API — set to `1` and every route 503s, no deploy needed |
| `APP_API_DISABLED` | kill switch for the mobile app's `/api/app/v1` API. **Separate from `PUBLIC_API_DISABLED` on purpose** — that one sheds third-party load in an incident, and reusing it would black out every installed app at the same moment. Setting this 503s the app while the website and public API stay up |

Bot detail: [TELEGRAM_BOT.md](TELEGRAM_BOT.md). Public API: [API.md](API.md). Non-secret vars live in
`web/wrangler.jsonc`: `CF_ANALYTICS_SITE_TAG` (the traffic panel's GraphQL
filter), `CF_ANALYTICS_SITE_TOKEN` (the public client-beacon token),
`CF_ACCOUNT_TAG`, `GA_MEASUREMENT_ID`
(the Google Analytics 4 gtag.js measurement ID, `G-…`; the tag is only emitted
when this is set **and** the visitor has opted in — GA has been consent-gated
since 2026-07-25, so expect GA4 traffic to read well below the Cloudflare beacon's,
which is cookieless and always on. `/privacy` documents both), and
`CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` (only if you move
to a custom domain and switch `/admin` to Cloudflare Access). Full setup:
[ADMIN.md](ADMIN.md).

### Python environment variables

Read by the pipeline scripts; none are required for a routine refresh, but they
change behaviour when set. Only `EVDS_API_KEY` is in `.env.example`:

| Var | Effect |
|---|---|
| `R2_BUCKET` / `R2_FAALIYET_BUCKET` | override the default R2 bucket names |
| `EVDS_CACHE_DISABLED` | bypass the local response cache (force a live fetch) |
| `KIMI_API_KEY` | the regulation-briefing key — fed from the `KIMI_API_TOKEN` secret (see above) |
| `KIMI_API_URL` / `KIMI_MODEL` | override the Kimi endpoint / model |
| `SITE_URL` | base URL for `generate_read_headlines.py` and `generate_presentation.py` |
| `WORKER_URL` | target Worker for `setup_telegram_webhook.py` |
| `CHROME_PATH` | headless Chrome binary for the presentation-deck PDF render |

### Amount-integrity alert ("read 1000x too small")

`healthcheck.yml` runs `scripts/check_amount_integrity.py --alert` daily. BRSA
reports print every figure as a whole number of **thousands of TL**, so a
fractional value in an amount column is a number we mis-read, not a small
number. The check sweeps every REAL column in the audit lane except the named
ratio columns (`RATIO_COLUMNS` in the script — CAR / LCR / NSFR / stage
coverage) and splits what it finds in two:

- **mis-read thousands separator** — the alerting class. `270336.203` where the
  filing printed `270.336.203`, or a hyphen-negative parsed down the English
  branch. The stored figure is a real one, 1000x too small. **No internal
  validator can see this**: every identity in `validator.py` compares figures to
  each other, and a scaling error on one cell breaks them only if that cell is
  in an identity at all.
- **leaked non-value** — a hierarchy marker, sector numbering or dipnot ref
  (`11.3`, `4.5`) that landed in an amount column. Reported, not alerted:
  it belongs to the equity_change / loans_by_sector column-alignment tails.

To run by hand:

```bash
python scripts/check_amount_integrity.py                    # remote D1
python scripts/check_amount_integrity.py --db data/bank_audit.db   # snapshot
python scripts/check_amount_integrity.py --strict           # fail on leaks too
```

**When it fires:** open the source PDF cell, and cross-check the same figure's
prior-period twin in the adjacent filing (a prior column re-prints the previous
year-end, so a correct extraction of that quarter is an independent anchor —
that is how the ISCTR 2024Q2 CET1 case was confirmed). Then correct via
`data/audit_overrides.json` + `scripts/audit_correct.py override-cells`, or
re-extract the partition. Do **not** widen `RATIO_COLUMNS` to silence it unless
the column genuinely holds a ratio.

## Troubleshooting

- **EVDS step failed** — TCMB occasionally rate-limits. Re-run the
  workflow; the scraper is idempotent (INSERT OR REPLACE on
  `(code, period_date)`).
- **`sync_audit_reports.py` reports a 404** — bank rotated a URL on
  their IR site. Update the entry in `audit_report_urls.json`.
- **`basis-mismatch:has-consolidated` (or `-unconsolidated`) on scrape** — the URL
  serves the WRONG report (a consolidated PDF under an `unconsolidated` key, or
  vice-versa). The scrape guard refuses to store it. Fix the URL in
  `audit_report_urls.json` (the correct file often has a different naming — GARAN's
  is on the Turkish site as `…Konsolide_Olmayan…`; a bank may list the consolidated
  under a `konsolide-` prefix with a different id) and re-run. Audit the whole
  archive for the class with `--verify-basis`. The basis is read from the PDF's own
  cover/auditor's-report front matter (`classify_report_basis`), so a filing whose
  content genuinely contradicts its filename is caught, not just a bad link.
- **D1 push errors `no such column`** — schema drift between local SQLite and D1.
  This should now **self-heal**: `ensure_d1_schema()` (`scripts/audit_d1.py`) has
  been column-aware since 2026-07-03 — it diffs the canonical schema (DDL **plus**
  `_COLUMN_MIGRATIONS`, realised in a scratch in-memory SQLite) against the remote
  `PRAGMA table_info` and emits the missing `ALTER TABLE … ADD COLUMN`s before the
  push. If you still see this, the column is missing from the canonical schema
  itself — add it to `src/*/schema.py` (DDL or `_COLUMN_MIGRATIONS`), not to a
  hand-written migration. Tables owned by `web/migrations/` (dashboard-side, not
  written by the Python lanes) instead need a new numbered migration.
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
