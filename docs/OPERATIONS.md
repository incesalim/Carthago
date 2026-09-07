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
| After audit acquisition/refresh + manual | `build-document-corpus.yml` | Preserve original audit PDFs and versioned source-page evidence in `document-corpus/v1/` on R2. Inputs `banks=ALL`, optional `period`, `limit=0`, `publish=true`. Uses existing `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; optional local `R2_BUCKET` overrides the default bucket. Separate `audit-document-corpus` concurrency group; no D1 or analytical snapshot writes. Reuses only evidence matching current PDF bytes and current engine; retains every source revision and failed filing. Run artifacts contain inventory and outcomes. Successful source preservation does not certify table/prose correctness. |
| Manual only | `repair-audit-roles.yml` | Restore missing/stale `bank_audit_pl_roles` after a targeted reload omitted the role map. Pulls the current audit snapshot, compares semantic role content with live D1, and requires identical underlying P&L rows before replacing **only differing role partitions**. No PDF extraction or financial-row writes. Inputs: explicit `banks` (no ALL), optional `periods`, `kind`, `dry_run=true` by default. `--apply` is Actions-only; a repeat run writes nothing. Uses existing R2 and `CLOUDFLARE_API_TOKEN` secrets; serialized with the `bddk-audit` lane |
| Manual only | `repair-missing-audit-rows.yml` | Repair narrowly proven D1 drift against the latest authoritative R2 audit snapshot without extraction or re-stamping. Default missing-row mode accepts explicit allowlisted `tables` (no ALL) plus optional `banks`/`periods`/`kind`; complete D1 factual multisets must be strict source subsets (null is distinct from zero), then Actions-only apply replaces only affected table partitions, post-verifies, requires a no-op replay, and uploads updated snapshot digests. `remove_remote_extras=true` instead requires explicit `partitions=BANK:YYYYQn:kind` and no Cartesian filters; every named D1 partition must contain every authoritative fact unchanged, then one atomic import deletes only the extra full primary keys. Canonical rows and R2 remain untouched. Missing tables, source-empty targets, schema/PK drift, changed or missing canonical facts, duplicate keys, or incomplete reads abort **all selected tables before any write**. `dry_run=true` by default; unchanged runs write neither D1 nor R2. Uses existing R2 and `CLOUDFLARE_API_TOKEN` secrets; serialized with `bddk-audit` |
| Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` | TCMB EVDS **daily/workday series only** (FX, policy/funding rates, sterilization, …) → D1. Weekly/monthly/quarterly series are polled by Saturday's full refresh. A run with no changed observation performs no D1 or R2 write |
| Daily 04:00 UTC | `refresh-news-daily.yml` | `sync_news.py` → `news_items` + `news_item_banks` (KAP filings, TCMB/BDDK announcements, bank press rooms, Google News) → D1 |
| First + last 5 days 13:00 UTC; Fri 13:30/15:30 UTC | `refresh-bddk-bulletins.yml` | BDDK bulletins only. The 13:00 runs probe the **monthly** bulletin around month-end; the Friday runs bracket the **weekly** publication window. The redundant Saturday 02:00 run is gone because `refresh-data.yml` follows at 03:00. A byte-stable SQLite result skips VACUUM, gzip, D1 and R2 entirely |
| Saturday 03:00 UTC | `refresh-data.yml` | Full weekly catch-up: monthly + weekly BDDK, every EVDS cadence, TBB/TKBB/KAP/TEFAS/Faaliyet → one incremental D1 handoff + snapshot only when something changed |
| Saturday 06:00 UTC | `refresh-presentations-weekly.yml` | `update_presentations.py` → `bank_earnings` (IR presentation decks) → D1 (`--only-tables=bank_earnings`). Bulletin lane (`bddk-pipeline` group). Tier-1 results filings ride `refresh-news-daily.yml` instead |
| Monday 06:00 UTC | `refresh-advertised-rates.yml` | `src.rates.scraper` → `bank_advertised_rates` → D1 (`--only-tables=bank_advertised_rates`). Per-bank **advertised** (posted-to-new-customers) loan + deposit rates scraped from doviz.com (loans) and hangikredi (deposits) — the only per-bank rate source; EVDS/BDDK publish rates at sector level only. Each run appends a dated `snapshot_date`, so history accretes (the sources only expose "today"). Bulletin lane (`bddk-pipeline` group) |
| 1st of month 06:00 UTC | `refresh-calendar.yml` | `src.release_calendar.scraper` → `release_calendar` → D1 (`--only-tables=release_calendar`). Scrapes TCMB's published calendar (MPC decisions + minutes + Inflation Report + Financial Stability Report) so the **Ahead** strips fill themselves — retires the hand-typed `MPC_DATES` (now a render-time fallback, still guarded by `check_calendar_fresh.py`). `requests`+`lxml`, no browser. Bulletin lane (`bddk-pipeline` group) |
| Manual only | `acquire-audit.yml` | Acquisition-only diagnostic: discover + download new audit PDFs → R2. Scheduled discovery moved to `refresh-audit.yml`, where a new filing is extracted immediately The full-document follow-up inherits manual `bank`/`period` filters; `--bank` accepts comma-separated tickers, while scheduled runs retain the recent-168-hour window. |
| Sunday 06:00 UTC | `summarize-regulations.yml` | Weekly regulation briefing via Kimi → `regulation_briefings` → D1. **Needs the `KIMI_API_TOKEN` secret** (see Secrets). Runs with `--require-baseline`, so it **fails rather than shipping an ungrounded briefing** (it warned-and-continued for 7 weeks unnoticed — see [regulation_followups.md](regulation_followups.md) §A). Since 2026-08-16 the generator **gates on the hand-verified fact checklist** (`src/news/briefing_facts.py`): bullets asserting a superseded value are stripped deterministically, omitted facts get one pointed retry naming the rule + source (never the value), and `check_briefing_facts.py --fail-under 0.75` is a **publication gate** — a briefing scoring under 75% is not pushed and not snapshotted, D1 keeps last week's verified text, and the run goes red (§E of the followups doc: a 69% briefing once shipped with a Telegram alert as the only trace). **Citations are gated the same way** (`src/news/briefing_citations.py`, §F): an id survives only if its body states the bullet's percentages, a figure-bearing bullet left uncited is retried once then dropped, and any miscited bullet in the stored briefing fails the gate like a missing section. **Annual pin:** once a year dispatch it with `baseline_year=YYYY` + `baseline_url=<TCMB "Monetary Policy for YYYY" PDF>` — the ingest must run *here*, between the snapshot pull and upload, because a local run writes a DB production never reads. **Posts the briefing to Telegram** (every section + bullet, split across messages under the 4k cap) whenever the LLM actually runs; silent on unchanged-input weeks. `force=true` regenerates on demand |
| Sunday 07:30 UTC | `generate-reads.yml` | "The Read" — LLM-rewritten headline per dashboard tab → `read_headlines` → D1. `deepseek-v4-flash` @Baidu (paid) ahead of the free providers, with per-family pacing + magnitude-match number validation; falls back to a deterministic template |
| Daily in earnings windows + manual/admin | `refresh-audit.yml` | Discover new audit PDFs → R2 → extract pending partitions → rebuild validation + coverage locally → **one** D1 push → snapshot. Filing windows: Jan 20–all February, Mar 1–15, and Apr/Jul/Oct 20 through May/Aug/Nov 20. Quiet checks stop after discovery and write nothing. Manual targeted re-extraction remains available from `/admin`. Runs two **alert-only** checks before the push — `check_audit_quality.py --alert` and, since 2026-08-13, `watch_cross_period.py --alert`, the only check in the pipeline that can see a **reporting-unit** error (every validator argues inside one filing, and a change of denomination scales both sides of each identity). It opens no PDF, writes nothing anywhere, and exits 0 even with no snapshot, so it can never fail a run whose data is already written. Since 2026-08-19 the run also **captures each freshly extracted filing document-scoped** (`backfill_document_capture.py --recent-hours 168` — run-local ledger, discarded; the compact `bank_audit_document_manifest` rides the same D1 push and snapshot) and **reconciles the freshly stored figures against the cells the filing printed** (`check_capture_reconcile.py --alert`, alert-only, exits 0) — the external unit-scale anchor working the same day a filing lands instead of at the next manual fleet backfill. A capture crash raises a job warning and skips; it cannot fail a run whose extraction is already written |
| Manual only (eval) | `analyst-research.yml` | **Analyst V2 — agentic discovery over deterministic evidence** ([ANALYST_V2.md](ANALYST_V2.md)): pulls the R2 snapshots + the filing PDF's per-page text, runs the story-agnostic anomaly scout, then a bounded hypothesis-driven research loop over typed read-only tools, deterministic verification of structured findings, and a rendered summary of survivors. **Artifact-only, no D1 writes, no schedule, nothing publishes automatically** — V1 (`analyst-daily.yml`) stays the baseline; publishing waits on the evaluation corpus + explicit human approval. `scout_only=true` runs without any LLM |
| Manual only (freeze) | `analyst-daily.yml` | The analyst layer: pulls both R2 snapshots, runs the deterministic detectors (`scripts/analyst/detect.py` — unit switches, cross-period restatements, opinion changes, perimeter, CAR−CET1 / NPL-vs-coverage divergences), then generates grounded LLM memos for the requested banks (`web/scripts/analyst-run.ts --memo`, free-model chain, figure guard). Migration `0037_analyst_signals.sql` is **applied**, and a **`push` input (default false)** sends `analyst_signals` + `analyst_basis_metadata` + `analyst_notes` to D1 via `push_to_d1.py --db data/analyst.db`. All three are `_FULL_REBUILD` (derived wholesale each run, so a signal that stops firing must disappear rather than linger) and tiny — ~9,030 billed rows, and the content hash makes an unchanged re-run free. ⚠️ `fired_at` is excluded from that hash: `detect.py` omits the column on INSERT so it takes a fresh `CURRENT_TIMESTAMP` every run, and leaving it in would rebuild the tables daily forever. The daily 07:00 UTC cron is live; `push` stays opt-in per dispatch. `banks=CALIBRATE` runs the ALBRK+SKBNK calibration pair from the feasibility test; Telegram ping on critical signals |
| Manual only | `backfill-tefas.yml` | One-time (re-runnable) ~5-year TEFAS fund-market history backfill (API cap) — resumable via `tefas_fetch_log` (re-dispatch with the same `from` date) |
| Manual only | `backfill-audit.yml` | Re-extract already-ingested audit PDFs after an extractor fix (extraction skips `success=1`, so history never self-heals) → clear D1 partitions → push → snapshot. **Never run `banks=ALL`** — it exceeds the 180-min job timeout mid-extraction; dispatch ~5-bank chunks sequentially (the `bddk-audit` concurrency group queues them) |
| Manual only | `reextract-statement.yml` | Targeted **single-statement** re-extract (`reextract_statement.py`): one lane (`oci` / `cash_flow` / `equity_change` / `npl_movement` / `loans_by_sector` / `bank_profile` / `credit_quality`) for selected `periods`/`banks` → inline-validate → push changed tables → snapshot → refresh matrix → persist the refreshed validation/coverage snapshot. `only_failing=true` (default) processes only NOT-passing partitions (`checks_failed>0 OR checks_passed=0` — catches stale empties); `require_passing=true` (default) rolls back a candidate unless that statement finishes with ≥1 passing check and zero failures. Passing partitions are skipped, and a re-extract whose factual columns are unchanged is rolled back without refreshing timestamps or writing D1. `dry_run=true` still pulls the authoritative R2 snapshot, but skips every D1/R2 write. **`force=true`** overwrites even passing partitions — needed when the defect is in a **derived** table (e.g. `credit_quality` passes but its derived `bank_audit_stages` fails, so `only_failing` wouldn't select it); the `credit_quality` lane also rebuilds `bank_audit_stages` after the run. The optional `partitions` input selects exact comma-separated `BANK:YYYYQn:kind` triples (intersected with other filters); malformed or unavailable targets fail before extraction. Parallel parsing is applied in bank/period order so corrected prior-year roots precede dependent comparisons. Direct monetary writers use the same canonical unit conversion as the full loader. A changed filing denomination is rejected even with `force`; use a scoped `refresh-audit.yml` preview and coordinated refresh so every monetary lane changes together. Rejected candidates print complete `[CANDIDATE_FAILURES]` diagnostics, including every failed relationship, before rollback; the stored validation row still describes the retained data. **Preferred over `backfill-audit.yml` for a single-lane fix** — one lane on fitz, no full-extract timeout (an all-periods lane run is ~6–10 min). How OCI/CF/NPL/loans_by_stage were fixed fleet-wide |
| Manual only | `purge-partition.yml` | Remove one `(bank, period[, kind])` from the audit lane **everywhere** — local snapshot → D1 → re-uploaded R2 snapshot (`purge_partition.py`), then a coverage re-sync and final snapshot save so the cell returns to `missing` consistently in D1 and R2. The PDF in R2 is untouched, so the cell reads missing **with** `pdf_present` = "acquired, awaiting extraction"; re-extracting restores it. For an extraction that succeeded and validated **green but is known wrong**, when the fix isn't ready. Deleting from D1 alone is the trap this avoids — the snapshot would keep the rows and the next `push_to_d1` would restore them. Built for **TEB 2026Q2**, whose filing switched from thousands to **millions** of TL: every figure landed 1000× small while every internal identity still footed, so only the fx lane's cross-period anchor saw it. `dry_run=true` (default) is genuinely read-only |
| Manual only | `repair-loans-zeros.yml` | One-time (idempotent) repair of the `loans` table: `_save_loans` used falsy `or` chains, so every BDDK-reported **0** in `total_tl` / `total_fx` / `total_amount` / `npl_amount` / `non_cash_amount` fell through to an absent column and stored NULL. Re-derives the true values from `raw_api_responses` (kept verbatim — nothing is re-fetched): **~44k cells across ~30k rows**, the largest block being consumer-loan FX, where 0 is Decree 32 and not absence. Scraper fixed 2026-08-01; this fixes the history. `dry_run=true` by default and is genuinely read-only. Stamps `downloaded_at` on corrected rows ONLY, so the `--hours 2 --only-tables loans` push carries exactly those rows — **do not widen the window into a full-table push**. Bulletin lane (`bddk-pipeline` group) |
| Manual only | `measure-free-provision.yml` | **Read-only corpus measurement** of the free-provision classifier. Downloads every audit PDF from R2, re-runs `classify_free_provision`, and diffs against the snapshot's stored values; the diff comes back as an artifact. **Writes nothing** — no D1, no R2 upload, no snapshot write — so it is safe to run at any time. Built when a page-selection defect was found (TEB 2026Q1 stored 0 while the filing states a ₺1,108,135k stock: the classifier read a *later* reversal note whose prior-period parenthetical said `Bulunmamaktadır`). Because the fix touches page selection corpus-wide, every changed cell has to be seen before any re-extraction is authorised. Inputs: `banks` (`ALL` sentinel), `limit`. Shares the `bddk-audit` group so a refresh cannot swap the snapshot underneath it |
| Manual only | `audit-triage.yml` | **Read-only diagnosis** of the failing audit partitions: `triage_partitions.py` + `watch_cross_period.py` over the R2 snapshot. `bank_audit_validation` says *which* identity broke; this says *why*, assigning a deterministic cause per partition (`dropped_cell` / `missing_row` / `column_slip` / `wrapped_cell` / `anchor_miss` / `drawn_page` / `rotated_page` / `wrong_pdf` / `unit_switch` / `source_defect`) with the page and the printed evidence behind it. **No model is called and no figure is produced.** Writes nothing anywhere — no D1, no row update, no snapshot re-upload, no extractor edit — so it is unaffected by the D1 write freeze; the reports come back as a build artifact. Inputs: `statement`, `bank`, `limit`, `render` (rasterises the page next to each note). The companion cross-period watch is the **only** instrument that can see a reporting-unit change: every in-filing identity is a ratio of figures sharing a scale, which is why the 2026Q2 Bin→Milyon switch footed perfectly while every figure was 1000× wrong. Shares the `bddk-pipeline` group (it reads the snapshot the refresh lanes write) |
| Manual only | `backfill-nonbank.yml` | One-time historical backfill of the non-bank sector lane (leasing / factoring / financing) from `from_year` (default 2020) → now (~5–10 min). The incremental refresh rides `refresh.py`; this is only for the initial history load. Apply migration 0013 first (via a `web/**` deploy) |
| Manual only | `backfill-faaliyet.yml` | Fleet backfill of the Faaliyet-raporu franchise lane (branches / personnel from annual-report PDFs) → `faaliyet_franchise` + `faaliyet_extractions`. The incremental refresh rides `refresh.py` |
| Manual only | `build-products.yml` | Loads the frozen **product-shelf** benchmark (`data/product_benchmark/*.json` + `src/products/labels_en.py` + `profiles_en.json`) via `src.products.build` → `product_attributes` / `bank_products` / `bank_product_profile` → D1 (`--only-tables=product_attributes,bank_products,bank_product_profile`) + snapshot. Deterministic and idempotent (loads committed JSONs, not a scrape); re-run for the same `snapshot_date` replaces its rows. Powers `/products`. Runs the `0034` DDL against remote D1 first (`CREATE … IF NOT EXISTS`), so it is safe to dispatch independently of deploy. NOT the refresh automation (that lane is designed but not built — see [knowledge/turkish-bank-product-benchmark-2026-07-22.md](knowledge/turkish-bank-product-benchmark-2026-07-22.md) §5). Bulletin lane (`bddk-pipeline` group) |
| Manual only | `refresh-transcripts-weekly.yml` | `update_transcripts.py` → `bank_call_transcripts` (earnings-call transcripts for the 8 listed banks that hold an English call) → optional D1 push (`--only-tables=bank_call_transcripts`) + snapshot. Bulletin lane (`bddk-pipeline` group). **Carries no `schedule:` on purpose** — the freeze is enforced by `gh workflow disable`, which is invisible in git, so a new workflow shipped with a cron would be born enabled and become the one lane writing to D1 during it. The `push` input therefore defaults to **false**: a run ingests and re-uploads the snapshot but does not touch D1 unless asked. When the freeze lifts, add `schedule: "0 7 * * 6"` (Sat 07:00 UTC, after `refresh-presentations-weekly`) and flip `push` to true. Inputs: `banks` (ALL/NONE sentinel — a blank dispatch input arrives as the default, not empty), `refresh` (refetch stored quarters; parser changes only), `push`. Source rate-limits at ~70 pages, so the fetcher backs off on 429 and paces at 3s |
| Daily 06:00 UTC | `healthcheck.yml` | D1 freshness check + **filing-season gap** (`filing_gap_problem`) + `verify_chart_spec.py` + `check_amount_integrity.py` + Telegram webhook-target check → Telegram/Discord alert if stale/failing/drifted/unacquired |
| Manual only | `test-openrouter.yml` | **Scratch probe** for the `OPEN_ROUTER_API` secret. `task=smoke` — auth + credits + DeepSeek price list + a completion through `free_llm.py`'s number validators. `task=usage` — accounting only, spends nothing. `task=regulation` — runs the **real** `summarize_regulations.py` against OpenRouter (repointing the `KIMI_API_URL`/`KIMI_MODEL`/`KIMI_API_KEY` env vars `kimi.py` already reads, so the production prompt is unchanged) with a Kimi A/B on the same section. **Read-only on production**: pulls the R2 snapshot, never uploads one, never pushes to D1. Delete it (+ `scripts/scratch/scratch_test_openrouter.py`, `scripts/scratch/scratch_dump_briefing.py`, and its `SCRATCH_WORKFLOWS` entry in `scripts/check_pipeline_graph_sync.py`) once the OpenRouter question is settled |
| Manual only | `telegram-webhook.yml` | Register (`set`) / inspect (`info`) / verify (`check`) the Q&A bot webhook. Lives in CI because `TELEGRAM_BOT_TOKEN` + `TELEGRAM_WEBHOOK_SECRET` aren't available locally. Run `set` after anything that moves the site origin — notably a **Worker rename**, which changes the `workers.dev` hostname and silently orphans the webhook |
| After CI passes on `master` | `deploy-cloudflare.yml` | Apply D1 migrations, build OpenNext bundle, deploy to Workers |
| On every PR | `ci.yml` | ruff + pytest + eslint + tsc + vitest quality gates |
| Manual only | `backfill-document-capture.yml` | Capture EVERY table each filing prints — rows, inferred columns, cells — plus the footnotes that qualify them, linked to the rows carrying their marker. Document-scoped, so tables with no parser are captured too. Writes no analytical row (safe over the settled BS/P&L). `--from-r2` streams each PDF, captures and deletes it. The raw ledger goes to `data/bank_audit_capture.db` and R2 `state/bank_audit_capture.db.gz`; **only** `bank_audit_document_manifest` is pushed to D1. `upload_ledger=false` skips the R2 object, `push_manifest=false` skips D1, `dry_run=true` writes nothing anywhere. Shares `bddk-audit` concurrency. Since migration `0044` the manifest's gap column is `unreadable_page_count` — vector-outline **and** raster-image pages both, İş Bankası having filed whole statement pages as pictures (PROJECT_STATE, 2026-08-19). The incremental per-run form (`--recent-hours`) runs inside `refresh-audit.yml`; this workflow remains the fleet build |
| Manual only | `backfill-audit-source-capture.yml` | Preserve and classify the physical source lines for the eight normalized/summary audit lanes without changing analytical facts. Pulls the audit snapshot, downloads existing PDFs, writes local/R2 `bank_audit_source_lines`, pushes only compact `bank_audit_capture_manifest` + changed validation rows, refreshes coverage, and saves the final refreshed snapshot so R2 and D1 retain the same verdict rows. Missing/non-captured manifests are the default scope; `refresh_existing=true` recomputes content-idempotently. `only_failing=true` selects only lanes with existing failed `capture_*` checks and takes precedence over refresh-existing; it does not select missing manifests or accounting-only failures. Repair financial rows first, or retain exact partition targets, because fixing a capture-only failure can make a financial partition pass and leave a later only-failing re-extract with no candidates. `dry_run=true` writes only the runner-local DB. Shares `bddk-audit` concurrency. |

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
the coverage-matrix spine is populated only in `bank_audit.db`. Two small
registry tables (`bank_audit_expected` / `bank_audit_statement_types`) are
content-hashed full rebuilds; `bank_audit_coverage` is row-delta + deletion
outbox. In
`bddk_data.db` they exist but are **empty**. A daily news/EVDS push from
`bddk_data.db` would therefore `DELETE` the spine and insert nothing — **wiping the
/admin coverage matrix**. The guard skips an empty local full-rebuild table, and
the incremental coverage table has no rows in the bulletin push window. See
*Troubleshooting → coverage matrix blank* for the restore recipe.

## Manual operations (rare)

### Website language preference

The public UI supports English and Turkish through `next-intl`. No new Worker
binding, secret, database migration or scheduled job is required. The TR/EN
switcher stores `carthago-locale=en|tr` for one year (`HttpOnly`, `SameSite=Lax`,
site-wide path; `Secure` in production). Without that cookie, Turkish is the
default regardless of browser language. It is independent of
analytics consent and never enters the data cache keys or API payloads. Clear the
cookie to test the Turkish default. Existing URLs and query parameters do
not change. The translation catalog and verification notes are in
[`web/i18n/README.md`](../web/i18n/README.md).

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
python -m src.scrapers.evds_scraper --frequencies all

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

During the filing windows, `refresh-audit.yml` checks daily. A valid new PDF is
downloaded to R2, extracted, validated, added to the coverage matrix, pushed to
D1 in the same batch, and snapshotted in that one run. If nothing new or pending
is found, the workflow stops before Node, D1 and the snapshot upload.

**The systemic-failure alarm exits 8, and 8 does not abort the run** (changed
2026-08-12). `sync_audit_reports.py` raises the alarm at the very END of `main()`,
after extraction has already written the local DB, so failing there skips the D1
push and the snapshot upload and destroys work the problem never touched. Both
`refresh-audit.yml` and `acquire-audit.yml` now special-case exit 8: they log a
`::warning::`, finish every persisting step, and re-raise in a final step so the
job still goes red and still alerts. **Any other nonzero code is a crash and
still stops the step immediately** — a half-written DB must never be pushed.

The alarm's scrape ratio also counts `pending` in its denominator. A
`not-a-report` verdict is a *successful* fetch — the PDF downloaded and was
inspected, it simply is not a filing yet — so excluding it measured the ratio
over only the handful of targets that resolved to a download. With the corpus
complete (`new` ≈ 0), four permanently-unreachable bank URLs were 100% of a
"batch" of four. That fired on five consecutive runs, 2026-08-08 → 08-12, and
each one discarded the same eight 2026Q2 partitions. Pinned by
`tests/test_sync_systemic_gate.py`, using those runs' real counts as fixtures.

**Those "unreachable" targets were the same bug, one layer down (fixed
2026-08-12).** AKTIF, COLENDI, VAKBN and EXIM were not missing — all six PDFs
were present in R2 *and* extracted in D1. `report_validity` read only the first
**6** pages looking for a filing's structural markers, and an ANNUAL report
prints the full independent auditor's report before the numbered Bölüm structure
starts. Every one of the six was a Q4. A stored PDF judged not-a-report sends
the scraper back to the bank's site on every run (the `replacing` branch in
`scrape_to_r2`), so ~80 genuine filings were re-fetched daily and the slow
sources timed out.

Measured over 60 random Q4 filings: first-marker page 1–9, with **19 of 60 (32%)
past page 6**; a non-Q4 sample never exceeded page 4. The window is now **16**
pages (`_HEAD_PAGES`), ~1.8× the observed tail. Diffed at 6 vs 16 across 80
filings: **10 gained, 0 lost** — widening is bounded by `_KAP_COVER_RX`, which is
tested first and positively identifies a notification, and by the 40-page floor
(a KAP cover sheet is ~14pp).

⚠️ Still expect some `[FAIL]` lines. ICBCT's filings carry KAP text in their
front matter and are refused as `kap-cover-sheet` despite being 77–108pp — a
separate, pre-existing issue this change did not touch (it moved ICBCT 2022Q4
from one refusal reason to the other, same outcome).

Outside a filing window, trigger `refresh-audit.yml` manually (GitHub → Actions
or `/admin`). `acquire-audit.yml` remains available only when an operator wants
to download/inspect a PDF without extracting it.

To enable auto-discovery for more banks, run
`python scripts/diagnostics/validate_discovery.py` (it checks discovery against
the config) and add any passing ticker to `DISCOVERY_BANKS`. See
[ADMIN.md](ADMIN.md) §Auto-discovery.

### Audit source-completeness backfill

Use **Actions → Backfill audit source capture** after migration `0042` is deployed.
The default run processes only missing or non-captured manifests across all eight target
lanes; narrow with `banks`, `periods`, `kind` or `lanes`. This is the safe historical
upgrade because it never calls an analytical upsert and never needs `--force`:

```bash
# Local inspection against an already-pulled snapshot; no D1/R2 writes.
python scripts/backfill_audit_source_capture.py --no-pull --dry-run \
  --banks AKBNK --periods 2025Q4 --lanes capital,equity_change
```

The raw `bank_audit_source_lines` table stays in `state/bank_audit.db.gz`; it is not a
D1 sync table. D1 receives `bank_audit_capture_manifest` (one row per partition/lane)
and any lane validation whose verdict changed. Source and manifest upserts compare factual
content before writing, so an identical `refresh_existing` run keeps its timestamps and
costs no D1 row writes. Near-full lanes fail on an unfamiliar numeric source row; selected
summary lanes retain/count their intentionally omitted detail and expose `shape_hash` for
the future alert mechanism.

Until this workflow has run over the historical corpus, partitions without a manifest keep
their pre-capture validator verdict. New extracts and targeted re-extracts populate evidence
automatically and enforce it immediately.

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
`refresh-bddk-bulletins.yml` (month-edge monthly probe / Friday weekly — the runs that
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

**`push_to_d1.py` prices every push before it runs — and stops nothing.**

> ⚠️ **The cost guard was REMOVED on 2026-08-12.** No push is refused on cost,
> at any size, in any lane. What follows describes what is left; the removed
> mechanism is recorded below it so the reasoning is not lost.

- **The estimate is printed on every push**, with a per-table breakdown. Billed
  rows are estimated structurally — `1 + index_count` per row, doubled for a
  full rebuild's `DELETE` — which lands near the measured 3.6x for the usual
  table mix. It is an estimate, never a report of spend; read actuals from the
  analytics query above. It is now **advisory**: the line says so, and the push
  proceeds regardless of the number.
- **A single row over D1's 100,000-byte statement limit fails locally**, naming
  the table and row, instead of shipping a file doomed to return a bare
  `SQLITE_TOOBIG`. Byte-sized batching handles every other case, but no batch
  size can send one oversized row: D1 permits a 2 MB *row* and caps a
  *statement* at 100 KB, so a value in between has to go to R2 with a reference
  kept in D1, or be split. **This one still refuses** — it is a correctness
  guard, not a cost guard, and a doomed file helps nobody.
- **`--check-only` prices without executing**, and now always exits 0. Use it to
  see a number before paying for it.
- **`--max-billed-rows` and `--no-cycle-check` are accepted and ignored.** Kept
  as no-ops so existing workflow files and pasted command lines keep working; a
  removed flag would have turned a dead argument into a dead lane.

**What actually holds the bill down now**, all of it upstream — none of it a
stop, and none of it able to catch a deliberate over-large push:

- **Partition digests** and the **content-hash skip** below: a table or
  partition whose rows are byte-identical to the last push is not sent at all.
  This is the primary defence and its tests are the ones that survived.
- **`upsert_validation` / `upsert_pl_roles` / `build_stages` compare before
  stamping**, so an unchanged row never enters the push window.
- **`scripts/healthcheck.py`** still reads rows-written for the cycle and is now
  the **only** thing watching the allowance. It reports after the fact; it
  cannot stop anything. If a campaign is going to be caught, it is caught here,
  once the rows are already billed.

<details>
<summary>What the guard was, 2026-08-04 → 2026-08-12</summary>

A per-push ceiling (`--max-billed-rows`, default **2,500,000**) that exited 3
rather than warning; a second cap that tightened as the billing cycle's 50M
allowance was spent (`min(declared, max(remaining_headroom, floor))`, floor
250,000); and a `D1_RUN_LEDGER` file making both cumulative across the several
pushes in one workflow run. An unreadable analytics API meant *unknown*, not
zero, so the declared cap was used unchanged.

It caught the shape it was built for and also produced two days of false
refusals: a routine BDDK push carrying the `api_series` rebuild bills ~237,456
for that table alone, which the 250,000 floor could not clear, and a refusal was
self-sustaining because the content-hash skip only records a hash after a
successful push. Removing the guard outright was the owner's call on 2026-08-12.

Reference figures, still accurate: a whole-audit-corpus push is **1,678,540**
billed rows; the one-off prose push is **1,110,204**; July's three campaign days
were 12.4M, 15.1M and 9.4M. Nothing now distinguishes any of these from a daily
cron.
</details>

**Partition digests: a campaign costs what it CHANGED, not what it touched.**

This is the mechanism that survived the guard, and with nothing refusing a push
it carries the whole load: a campaign is no longer *declared*, only *cheap*. The windowed
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
disagree" was wrong: two remote calls cannot be made atomic. (The cost-guard half
of that argument is moot since 2026-08-12 — nothing refuses a push now — but the
atomicity half stands on its own, and a SQL error or a cancelled runner between
two calls is just as destructive as a refusal was.)

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
   the data is correct, and only the bill moves. Seven ingestion paths have
   carried it:

   | Lane | Why it re-fetches | Waste before the fix | Fixed |
   |---|---|---|---|
   | `evds_scraper.fetch_one` | no incremental endpoint — pulls each series back to 2018 every run | 52,828 of 53,521 rows looked new **daily**, ~17M rows/month | 2026-07-27 |
   | `weekly_api_scraper.fetch_and_store` | the BDDK weekly API only serves a trailing **13-week** window | ~26,600 rows a run, of which 12/13 (~24,550) unchanged; 4 runs/week ⇒ **~1.5M billed writes/month** | 2026-08-04 |
   | `tefas.loader.upsert_day` | `update_tefas.py` re-fetches a trailing **7-day** window every day | ~2,150 rows/day, 6/7 unchanged ⇒ **~0.2M billed writes/month** | 2026-08-04 |
   | `tbb.loader` | newest quarterly workbooks and the cumulative monthly workbook overlap stored history | identical TBB rows were re-stamped on the Saturday catch-up | 2026-08-06 |
   | `tkbb.loader` | newest-quarter revision check + rolling 12-month acquisition window | identical TKBB rows were re-stamped on the Saturday catch-up | 2026-08-06 |
   | `update_tuik.write_db` | each workbook carries previously stored history | every returned TÜİK row was re-stamped on the Saturday catch-up | 2026-08-06 |
   | `kap.loader.replace_bank_rows` | each bank's complete ownership partition is re-fetched | every unchanged KAP partition was deleted and reinserted | 2026-08-06 |

   All seven now compare the stored tuple before writing, so an unchanged row
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

   ⚠️ **A freshness check cannot see data you never acquired.** Every threshold
   above asks whether data we *hold* has gone stale, and all of them stayed
   green through 2026Q2 while thirteen banks published filings the audit lane
   never fetched — `new=0 changed=False` is indistinguishable from a quarter in
   which nobody filed. The check that closes this is a **comparison between two
   lanes**, not a threshold on one: `healthcheck.filing_gap_problem` joins KAP's
   `results_filing` in `bank_earnings` against `bank_audit_extractions` for the
   newest period anyone has filed, and names any bank that filed ≥
   `FILING_GAP_GRACE_DAYS` (4) ago and is still missing. The grace exists
   because KAP genuinely precedes a bank's own IR page — TEB filed 07-23 and its
   PDF appeared 07-26 — so a zero-grace version would fire on every bank every
   quarter and get muted. **When you add a lane that acquires documents from
   third parties, ask what would tell you it stopped acquiring**; the answer is
   usually a second, independent signal of what *should* exist.

   ⚠️ **This class is the flat daily baseline, not the overage.** Together the
   first measured weekly + TEFAS fixes took ~1.7M/month off a ~14.6M/month quiet
   baseline. The four Saturday-path fixes above reduce it further; that saving
   has not yet been measured against a live D1 run. The
   50M is blown by **campaign days** (Jul 15/17/26 alone were 36.9M of 68.1M) —
   backfills, re-extractions and override pushes. Fixing scrapers does not
   address those; budgeting the campaign does.
2. **Full-rebuild tables carry a content hash.** `api_series` (19,787 rows,
   rebuilt locally only after changed BDDK/full refreshes) and the two audit
   registry tables emit `DELETE` + `INSERT` for every row. `bank_audit_coverage`
   graduated to row-delta syncing in migration 0040. `push_to_d1` hashes the local contents
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
board (that is the freeze, not a break), no Telegram bulletin pings, and a
month-end BDDK bulletin is picked up whenever the probe resumes rather than the
day it publishes.

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
| `OPEN_ROUTER_API` | OpenRouter (DeepSeek et al). Added 2026-07-05; **since 2026-08-17 it is the head of every lane's chain** — `generate-reads.yml`, `summarize-regulations.yml` (when `BRIEFING_LLM=deepseek-flash`), the analyst workflows, and the scratch probe `test-openrouter.yml`. ⚠️ Note the name: no `_KEY` suffix, unlike every other provider secret. ⚠️ This is the **Actions** secret; the Worker needs its own copy via `wrangler secret put` |
| `KIMI_API_TOKEN` | weekly regulation briefing (`summarize-regulations.yml`). ⚠️ **Name mismatch**: the repo secret is `KIMI_API_TOKEN`, but the workflow maps it to env `KIMI_API_KEY`, which is what `src/news/kimi.py` reads. Provision the *secret* under the token name |

### Workflow env keys (not secrets, not Worker bindings)

`check_docs_sync.py` covers `secrets.X` and `CloudflareEnv` keys; a plain `env:`
value on a step is invisible to it. AGENTS.md still requires every env key the
code reads to be named here, and this one is load-bearing.

| Env key | Used by |
|---|---|
| ~~`D1_RUN_LEDGER`~~ | **Retired 2026-08-12 with the cost guard.** Was a per-RUN file `push_to_d1.py` debited before each write, so a cap bounded the run rather than each invocation. Nothing reads it now; a leftover value in an environment is inert. Removed from `refresh-audit.yml`, `refresh-bddk-bulletins.yml`, `refresh-data.yml` and `backfill-audit-source-capture.yml` |

Actions **variables** (same screen, "Variables" tab — not secrets):

| Variable | Used by |
|---|---|
| `SITE_URL` | `generate-reads.yml` — the dashboard base URL "The Read" fetches; falls back to the prod URL when empty |
| `BRIEFING_LLM` | `summarize-regulations.yml` — which LLM runs the weekly briefing: `deepseek-flash` (OpenRouter, pinned to the `Baidu` upstream — the default since 2026-08-17) or `kimi`. **Switching the scheduled lane is this one field** — no code change, no deploy. A dispatch `llm` input overrides it for a single run without making it stick. Unset = `deepseek-flash`, which needs the `OPEN_ROUTER_API` secret; set it to `kimi` to revert to `KIMI_API_TOKEN` |

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
| `OPEN_ROUTER_API` (or `OPENROUTER_API_KEY`) | **the bot's primary LLM provider** — OpenRouter. Serves BOTH the head of the chain (`deepseek/deepseek-v4-flash`, PAID, pinned to the `Baidu` upstream, primary since 2026-08-17) and the free nemotron behind it. ⚠️ The identically-named **Actions** secret does not reach the Worker; set it separately with `wrangler secret put OPEN_ROUTER_API`. While unset BOTH OpenRouter providers are skipped and the chain starts at Groq, so the bot keeps answering — for free, on a weaker model, with nothing announcing the downgrade. ⚠️ The `:free` suffix on the nemotron id is load-bearing: the paid twin is a different id and would bill |
| `GROQ_API_KEY` (or `GROQ_API_TOKEN`) | the bot's second fallback LLM provider (first free non-OpenRouter) |
| `CEREBRAS_KEY` (or `CEREBRAS_API_KEY`) | the bot's third fallback LLM provider |
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

### Source-verified anomaly repairs (2026-08-31)

For a verified reporting-unit error affecting a whole filing, `refresh-audit.yml` supports `dry_run=true` only with one `bank`, one `period`, and `skip_scrape=true`. It re-extracts existing PDFs into runner-local SQLite and prints per-table changes and validation failures, without D1/R2 writes or notifications. Review this before a coordinated apply: ordinary single-lane repairs must not update the unit metadata before the rest of that filing has been rescaled. The existing unit-change guard replaces all affected lanes together; unchanged filing kinds retain their passing data.


Migrations `0045_capital_deductions.sql` and `0046_npl_accrual_movement.sql` add nullable amounts; old rows remain null. Apply through the CI-gated deploy before capital/NPL repair pushes or the updated analyst queries. Capital uses `Tier1 + Tier2 - capital_deductions`; NPL accrual is a separate signed movement. Neither is filled from an unexplained residual.

`data/audit_quality_reviews.json` records exact source PDF hashes, pages and values for verified liquidity outliers. Only the same partition, metric and value is treated as an observation; validator failures are never waived. Reconciled P&L sign changes remain printed observations, while incomplete or inconsistent signed statements still alert. The final empty quality scan also clears its R2 alert baseline and reports resolutions.

## Complete-document source corpus (implementation in progress)

`build-document-corpus.yml` runs after completion of `Refresh audit reports` or
`Acquire audit reports` on this repository's `master`, including failed upstream
runs that may still have acquired PDFs. It also accepts manual dispatch. It runs
`scripts/build_document_corpus.py` against
registered sources in R2. `structure=true` adds source-linked numerical and
ruled-table candidates, physical text blocks, paragraph/heading candidates,
section candidates and content issues. Paragraph segmentation preserves source
lines and span occurrences; styles and spacing suggest boundaries and page-local
heading context without certifying them. Document section context is separate;
font-size comparisons do not establish cross-page heading relationships.
The source remains independently accessible.
Source text uses an unbounded extraction region: replacement text associated
with images can have synthetic coordinates outside the page, so ordinary page
clipping can discard visible wording. A separate literal-glyph word view is
retained when ActualText changes the observation. PDF-declared structure keeps
native containers, source-span links and image regions; native table tags may
describe column fragments. None of these tags or coordinates certifies meaning.
`publish=true` writes only `document-corpus/v1/`; no D1, acquired source object or
analytical snapshot is modified. Originals are preserved even when decoding
fails. Artifact uploads are read back, filing indexes use conditional updates,
revisions and failures are retained, and unchanged replay performs no R2 writes.
Large published files are removed from the runner after verified publication.

The compact `document-corpus/v1/catalog.json` retains scoped progress and the
full acquisition denominator; it updates every ten filings and at run end using
conditional writes. A replay with unchanged content does not restamp it. Source
and structured artifacts store per-page SHA-256 lists in their JSONL manifests,
allowing the admin to stream and verify one page without loading a whole report.
The Worker binding `AUDIT_DOCUMENTS` points to `bddk-audit-reports` in
`web/wrangler.jsonc`; it uses the Worker binding, not an exposed R2 credential.
The authenticated `/api/admin/document-corpus` route provides the catalog,
filing metadata, original PDF, compressed full evidence/structure downloads and
`artifact=source|structure&page=N` previews. It never writes storage or D1.

After byte-verified publication, a per-filing resume receipt records the acquired
object and artifact versions (ETag, size and modification time). An unchanged
source, evidence engine, structure engine, annotation set and successful receipt
can reuse those artifacts using metadata reads only. A changed or missing object
or failed attempt disables that shortcut. Download metadata comes from the same
response as the hashed PDF bytes; a source changed during processing is retried.
Manual `recheck_bytes=true` / CLI `--recheck-bytes` reads all selected bytes again
without rewriting identical objects. Metadata reuse is storage continuity,
never a claim of fresh semantic verification.

Manual `publish=false` runs have independent concurrency groups, so bounded
read-only probes can run while a publishing fleet continues. Publishing runs
share one queue. For a read-only probe with `limit` between 1 and 4, Actions
retains original PDFs and capture artifacts for seven days as
`audit-document-probe-evidence`, enabling independent review of the runner's
output. The compact inventory/outcome report remains available for 30 days.
Full-scope runs (`banks=ALL`, `limit=0`, or automatic follow-up) use four parallel
groups within that publishing queue. A stable SHA-256 of the filing filename
assigns each filing exactly once; additions to the inventory cannot move existing
filings between groups. CLI `--shard-count` and zero-based `--shard-index` expose
the same partitioning, applied after scope filters and the global limit. Each
report records selected and assigned counts while retaining the full inventory
denominator. Empty assigned groups succeed explicitly; an empty requested scope
is an error. Report artifacts are named `audit-document-corpus-report-0` through
`-3`; bounded single-job probes retain `audit-document-corpus-report`.
One group's failure does not cancel the others. Conditional catalog writes retry
contention with a short randomized delay and merge the latest saved progress;
filing artifacts remain disjoint. A repeated completed run still writes nothing.
Annotation reuse is scoped to the filing; another bank's new test does not
invalidate that filing. Source-text cases gate source-only capture before its
evidence is published. Source receipts bind their separate annotation identity;
table-case changes do not invalidate an otherwise unchanged source-only receipt.

Manual `kind=BOTH|consolidated|unconsolidated` narrows the filing basis. A bounded
visual-text probe also accepts `ocr_pages` (one to four distinct, one-based PDF
pages), `ocr_dpi=300|450|600` and `ocr_language=eng+tur|tur+eng|eng|tur`. It requires
`publish=false` and `limit=1..4`; it cannot write recovery candidates to R2 or D1.
The CLI equivalents are `--ocr-pages`, `--ocr-dpi` and `--ocr-language`.
The probe downloads only the English/Turkish model files pinned by revision,
size and SHA-256 in `src/audit_reports/document_ocr_models.json`. Cached or
downloaded bytes with a different hash are rejected. The cache is local to the
output directory and is not included in the retained evidence artifact.

For each selected page, PyMuPDF renders the original and uses its bundled OCR
to create an image-bearing derivative PDF. The adjacent `.ocr.json` keeps raw
word/span occurrences in original display coordinates, source and pixel hashes,
derivative hash, resolution, language/model identities and native runtime hashes.
Retention checks re-read that PDF and compare its embedded image to a fresh
source render. These checks reject missing/changed words, wrong sources and
changed pixels; they do not certify recognition accuracy. OCR candidates remain
separate from native source evidence and structured tables. Both files are kept
inside the existing `audit-document-probe-evidence` artifact for independent review.
`tests/fixtures/document_ocr_annotations/` gates only explicitly transcribed
tokens in their source regions; punctuation and sign/association questions remain
visible, and a matching token is never full-cell approval. A failed token check
retains the probe evidence, names the failure and fails the run.

Manual `vector_pages` / CLI `--vector-pages` selects one to four pages for a
separate outline-reader probe, also requiring `publish=false` and `limit=1..4`.
`src/audit_reports/document_vector_anchors.json` records the reference filing,
PDF hash, source regions and transcriptions used to rebuild character templates.
In R2 mode the builder reads that registered reference if the target is another
PDF; a hash mismatch fails the probe. For a local target that is not the reference,
provide the reference PDF with `--vector-reference`. Glyph contours are rebuilt
on the runner. The retained artifact includes the atlas and reference original.

Matching uses contour commands, normalized coordinates and bounded horizontal
scaling. Each filled path must match every glyph unambiguously; an unknown or
conflicting glyph leaves its text null and retains the partial observations.
Printed dashes remain dashes. Outlines have no inherent row/column or visibility
guarantee, so candidate transcriptions carry explicit unverified status.
`.vector.json` observations retain source drawing/glyph references and unresolved
paths; checks reproduce these against the original PDF and atlas. The separately
registered `tests/fixtures/document_vector_annotations/` cases check transcribed
words/regions and abstention on unrecognized negative signs. Seed records can
restrict `learn_characters` to selected punctuation, keeping numeric evaluation
independent of new punctuation examples. Source regions must contain the whole
path; background shapes centered inside a cell are excluded. Failed checks retain
the named probe and fail the run. This probe does not update production recovery
data or existing analytical lanes.

`recover-document-corpus.yml` runs `scripts/recover_document_corpus.py` as a
separate manual workflow and follows completed `Build audit document corpus`
runs on master. Inputs are `banks`, `period`, `kind`, `limit`, `pages`
(`flagged` or up to four explicit page numbers), `publish`, `dpi` and `language`.
It uses the same three R2 secrets and optional `R2_BUCKET` override. Full-scope
runs use four stable filing groups; publishing shares the separate
`audit-document-recovery` queue. It does not change native capture engines,
filing indexes, the core catalog or D1. Automatic follow-up reads only capture
reports from the completed same-repository run using the built-in `GITHUB_TOKEN`
with `actions: read`. `SOURCE_RUN_ID` and `SOURCE_HEAD_SHA` identify that upstream
run. `src.audit_reports.document_recovery_followup` selects only successfully
published filing/PDF hashes; failed and read-only rows remain named exclusions.
Quality-only runs have no capture reports and trigger no recovery. The manifest
is retained as `audit-document-recovery-scope`; `GITHUB_OUTPUT` carries only the
validated has-sources flag and group list. Up to four filings use one job, larger
scopes use four. The worker's `FOLLOWUP` flag adds `--scope-manifest`; manual
filters cannot be combined with it. Missing acquisitions receive named failures,
and a changed source hash is refused even if it has a valid current receipt.
This processes successful publications from partially failed capture runs without
claiming that excluded sources succeeded. Cross-run reports are scope evidence,
not executable inputs or content approval. Cloud follow-up validation is pending.

The source classifier records its per-page observations and selected-page list.
It transforms image/word boxes into display coordinates once, keeps the already
rotated page bounds, and counts native words inside images. Overlapping image
areas are summed as a heuristic, not asserted to be a measured content union.
Its image/outline flags are a heuristic, not proof that other pages contain no
unreadable text. Explicit pages are always recovered. Each selected page keeps
full-page OCR, source pixels, line/word references and, for outlined pages, the
source-rebuilt atlas and every matched/unresolved path. OCR/outline comparisons
retain both raw strings and disclose differences without changing either value.
Even exact agreement is not semantic approval.

Recovery artifacts are immutable under `document-corpus/v1/sources/<PDF hash>/recovery/`.
Separate `recovery/<bank>/<period>/<basis>/<PDF hash>.json` indexes retain page
revisions, selections and failed attempts. Read-back verification precedes index
publication. Reuse verifies retained bytes and source pixels with the current
recognition inputs; source/model/atlas changes or missing/corrupt artifacts
invalidate reuse. A derived-view implementation change rebuilds that view from
verified raw observations without running OCR again. Artifact keys must agree
with both source identity and the indexed content hash.
Matching annotations are rerun even when OCR is reused. Failed source annotations
retain candidates for review and fail the named page/run. Successful published
page files are removed individually from the runner; failures remain in its
run report. Artifacts `audit-document-recovery-report-0` through `-3` retain
inventory and named outcomes for 30 days; bounded read-only runs keep originals
and recovery evidence for seven days as `audit-document-recovery-evidence`.

Local recovery requires explicit `--pages` and `--limit 1..4`; unbounded recovery
and all publication require Actions. No local OCR fleet is permitted.
The private `/api/admin/document-recovery` reader accepts a validated filing and
page, finds only that current source revision's recovery, and verifies checksums.
`artifact=ocr-pdf` opens the retained source image with its recognition layer.
Missing recovery, failed attempts and unreviewed readings stay explicit.

Recovery now also proposes grids from the retained source pixels. Thin vertical
rules suggest columns; repeated numeric baselines suggest rows. Light gray rules
and OCR border punctuation must not hide those boundaries. An OCR `o` may suggest
a baseline but is never changed into zero. Each cell keeps its raw image reading,
matching outline reading and word/path references. Unresolved outlines inside a
numeric cell make the selected candidate null while retaining the raw OCR text.
Headers are preserved as source text; units, column roles, continuations and
financial meaning are not inferred as fact. These grids remain candidates.

The pixel/rule/table view is recomputed during retention verification, and the
matching source annotations also check that their words land in the corresponding
cells. Changed layout code rebuilds from the retained OCR PDF and observations;
it does not require new OCR recognition. The artifact records the layout-code and
NumPy identities separately from recognition inputs. Read-only cloud runs
`34042466701` and `34042468735`, followed by independent source reconstruction,
pass all 59 selected cell-association checks. The running recovery fleet
`34040878532` is at `8cb6b60` and contains raw observations only; candidate-layout
publication follows completion of that run.

Successful publishing runs now issue `recovery-receipts/<bank>/<period>/<basis>/`
receipts after reading back the original, selected page artifacts and recovery
index. Receipts bind metadata from the exact acquired PDF download, source hash,
request scope, code/runtime/model identities and per-filing annotations. An
unchanged publishing replay reads the receipt and recovery index and checks
object versions without downloading or classifying the PDF. Changes, missing artifacts or a later recovery-index failure
invalidate reuse. Explicit page scopes cannot stand in for automatic selection.
No-page selections still retain source and selector evidence and never certify
that a report needs no recovery. `recheck_bytes=true` / `--recheck-bytes` bypasses
filing receipts while retaining verified raw-OCR reuse. Read-only probes always
process retained bytes so their evidence remains downloadable. The runner
`RECHECK_BYTES` input carries the option; it is not a secret. Local unit and
end-to-end no-write/changed-input tests pass; receipt cloud validation is pending.

Native candidate structure also records `positioned_text` when replacement text
changes the word view. Literal glyph words remain separate from uniquely paired
image replacement spans. Each position cites the declared parent/image/text
nodes plus source span and image IDs; clipped image geometry must be contained
in the observed source image. Ambiguous pairs remain issues. Additional
`native_image_replacement_geometry` tables refer to positioned pieces through
`word_view=positioned_text`; ordinary tables still refer to source words. These
views do not move the original source spans or certify visual/semantic accuracy.
Retention and source-annotation checks recompute the pair links before checking
selected row/column associations. The native source-evidence fingerprint is
unchanged; candidate structure has a new implementation identity. The 5f6fd48
cloud samples and Akbank/Albaraka publishing sample pass independent byte,
source-association and live-admin checks. The remaining fleet awaits that version.

For an independent read-only review, dispatch `build-document-corpus.yml` with
`quality_only=true`. This mode ignores the publication input, has separate
read-only concurrency and runs `scripts/review_document_corpus.py`; it never
captures new data or writes R2/D1. Filters and stable filing groups work as in
capture. The normal report artifacts include `quality-results.json` and inventory.
The review hashes both the acquired and archived PDF copies, verifies the
compressed evidence/structure artifacts and their page inventories, and records
opening-page bank, quarter-end date and consolidation-basis claims with source
span references. Only registered names and explicit configured aliases are
matched. A missing name, image cover or competing dates remains unresolved or
ambiguous. Findings do not establish semantic accuracy. Text-mapping signals and
recovery selection/pending/failure counts are retained separately; a missing
recovery index never means recovery is complete. Conflicting source identity or
artifact failures fail the review run without changing source data. Local use
requires `--limit 1..4`; full byte reviews belong in Actions.

Contextual identity reviews live in
`data/banks/audit_document_identity_reviews.json`. The read-only review accepts
`--identity-reviews` to select a registry and records its byte hash plus the
review module's hash. Reviews apply only to the exact PDF revision and checked
source spans/text/geometry. They add a separate `contextual_identity_review`
field and summary; automatic findings are preserved. A contradictory cover
requires its own source witness. This is source-binding evidence, never whole
text, table or financial approval.

Source-byte review verifies the acquired R2 PDF and retained copy. For older
acquisitions, `source_url` is a configured lookup URL, not proof that the current
HTTP response has the same bytes. New acquisition manifests retain the actual
response/transport/member chain. Comparing older stored PDFs with current
official-source downloads remains a separate source-origin review.

Identity review joins adjacent font spans on the same physical source line;
font boundaries do not insert spaces into bank names. Explicit `source_names`
contain corroborated legal-name aliases. Text-review signals retain the source
span IDs and character offsets of nontext controls, as well as replacement
characters and suspicious tokens. Automatic recovery selection now uses
`source_content_detector`, including these text signals alongside image/outline
geometry. Historical `image_outline_detector` selections remain readable. The
request/selector hashes include `document_quality.py`; the raw OCR engine is
unchanged, so existing OCR observations can be reused when derived views change.

Recovery tables use printed vertical rules first. When no ruled table is
found on a page, repeated right-aligned OCR amounts supply an unruled physical
grid candidate. Mixed ruled/unruled pages, wrapped logical rows and headers
remain review work. An unobserved cell is `null`, never zero. Recovery packets
also retain OCR text blocks and source word/line/table associations.
`tests/fixtures/document_recovery_text_annotations/` supplies complete,
source-transcribed regions. Comparison preserves accents, punctuation, signs
and word order. `source_disagreement` means retained OCR differs from that
transcription; it remains visible in the packet, revision and read-only quality
report. It does not fail preservation or approve/correct the reading. Structural
or artifact failures still fail the run. Receipt identity binds these modules
and filing-specific text annotations; raw OCR remains reusable.

To fill explicitly registered source gaps, dispatch the same workflow with
`acquire_missing=true` and `publish=true` (not `quality_only`). This runs
`scripts/acquire_document_corpus.py` before capture, with the same bank, period,
basis, limit and stable filing groups. Every acquisition group completes before
any capture group snapshots inventory. It only downloads missing acquisition keys. It retains transport bytes, selected originals and content-addressed
acquisition manifests under `document-corpus/v1/`, rejects ambiguous multi-PDF
archives and conflicting leading-page claims, and uses conditional creation plus
byte readback for the acquisition key. An unresolved or damaged cover remains
explicitly unresolved; it is not excluded or silently approved. Existing source
keys are never overwritten. Java byte-array wrappers are recorded and removed
from direct downloads or selected ZIP members while original transport bytes
remain intact. For a reviewed multi-PDF package, `archive_selection` in the bank
URL config is keyed by canonical basis and period and requires an exact member
name plus its SHA-256. A changed or missing member fails selection. Unselected
PDF members remain named and hashed, with related text capture explicitly pending;
a successful primary-PDF acquisition does not claim its attachments are processed. No D1 writes, analytical extraction or notifications
occur. Successful acquisitions are captured even if another source needs review;
the run then reports the acquisition failure. `acquisition-results.json` retains
each named outcome in `audit-document-acquisition-report-N` artifacts, where N
is the stable group number. This CLI is Actions-only.

For a light local sample (no remote writes):

```powershell
python scripts/build_document_corpus.py --from-r2 --capture --structure --bank QNBFB --period 2026Q1 --kind unconsolidated
```

Local R2 reads require the existing R2 credentials in the process environment.
Without `--capture`, the command only reconciles the inventory. Without an R2
query or `--inventory-json`, remote acquisition is recorded as unknown. The local
output defaults to `data/audit_capture/corpus-v1/`; source originals and evidence
are addressed by PDF and artifact SHA-256. `capture-results.json` is the current
run's outcomes; durable per-filing history lives in R2's `filings/` indexes.

The builder runs the matching source-revision cases in
`tests/fixtures/document_annotations/` when structuring. A failed annotated case
fails that filing and the run. No matching annotation is explicitly unverified.
`source_preserved` and `structured_candidates` are not semantic approval. Never
use the number of detected tables as the denominator for complete capture.
Fleet processing belongs in Actions; use `banks`, `period` and `limit` to select
an initial sample or a repair scope. See [AUDIT_DOCUMENT_PLAN.md](AUDIT_DOCUMENT_PLAN.md).

Recovery also derives an optional `font_mapping` observation from the original
PDF using PyMuPDF only. Eligible Type0/Identity-H fonts have an empty Unicode
CMap and an embedded TrueType character map. A replacement requires unique
font/trace/origin/fallback-glyph agreement. Native characters and all alternatives
are retained; ambiguous non-whitespace mappings abstain. `font_text_regions`
checks the same independently transcribed regions using font-word references,
without rewriting OCR. Packet verification recomputes the complete font view
from the original. Its implementation participates in recovery engine and receipt
identities; changing derived font code still reuses verified raw OCR. The admin
reader validates the source/page binding and exposes text blocks and alternatives.

### Independent official-source comparison

`review-document-origins.yml` runs `scripts/review_document_origins.py`. Inputs
are `banks=ALL`, optional `period`, `kind=BOTH`, `limit=0`, and `publish=false`.
Full registered scopes use four stable filing groups. This manual workflow uses
existing `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` credentials;
publication is serialized in `audit-document-origin-reviews`, separately from
source capture. Local samples require `--limit 1..4` and cannot publish.

The review reads acquired PDF bytes, downloads the registered URL afresh, retains
transport and selected PDF hashes, observes the first three source pages and
compares exact bytes. Only an explicitly observed Java stream wrapper may be
removed for a separate wrapper-equivalence result. A changed PDF, unavailable
URL, invalid/ambiguous transport or missing acquisition stays a named outcome.
Byte agreement and source identity are separate findings; a conflicting cover
still fails the review even when both copies have identical bytes.

`publish=true` retains transport/PDF evidence and immutable comparison receipts
under `document-corpus/v1/`; independent `origins/<bank>/<period>/<kind>/index.json`
keeps revision history and the latest observation. Publication recomputes the
observation from acquired bytes and retained transport, checks source versions,
verifies immutable artifact bytes and reads back the comparison index. Replaying
the same observation writes nothing; a fresh HTTP observation has a new timestamp.
This path never changes acquired objects, core filing indexes, D1 or approval.

Artifacts `audit-document-origin-report-0` through `-3` retain every assigned
filing, status and source identity summary for 30 days, including failed runs.
Differences and unavailable sources make the job fail for review while other
filings continue. Bounded read-only samples (`limit=1..4`) retain downloaded bodies
in `audit-document-origin-evidence` for seven days; full read-only runs retain
reports only. Use publication for durable full-scope original-byte evidence.

The authenticated `/api/admin/document-origin` reader accepts validated filing
identity plus optional `artifact=origin_pdf|transport`. It verifies the retained
comparison receipt and artifact hashes, rejects arbitrary storage keys and keeps
`private, no-store` responses. The admin displays missing comparisons, observed
revision differences, source identity and pending archive attachments separately
from capture/semantic status. Artifact previews use the existing bounded
24 MB verified-byte reader; larger responses require direct operator R2 access.

### Other PDFs bundled with a report

`capture-related-documents.yml` runs `scripts/capture_related_documents.py` for
one required `filing=BANK|YYYYQn|consolidated` (or `unconsolidated`), with optional
`publish=false`. It requires a retained official-origin comparison; it never
redownloads an arbitrary URL. Existing `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and
`R2_SECRET_ACCESS_KEY` credentials provide private corpus access. Publishing
runs share `audit-related-documents`; read-only probes have independent groups.
All capture/recovery runs belong in Actions.

The runner verifies the origin receipt, exact archive transport, complete member
inventory and primary PDF selection. Every remaining PDF member, including
activity reports and signed declarations, gets a named outcome. No archive path
is used as a local output path. Canonical PDF bytes, native page evidence and
structure use the existing source-hash artifacts; separate indexes live at
`related/<bank>/<period>/<kind>/<transport SHA>/<raw member SHA>.json`. The index
retains the exact member name, bytes/hash and primary-report association. It
cannot update the primary filing index or acquisition object.

Every related-document page receives the pinned `eng+tur`, 300 dpi OCR reading,
source-pixel table candidates, physical text blocks and eligible embedded-font
readings; cached raw OCR is byte/source verified before reuse. Native text and
signature images remain intact. All recognition and semantic states are unverified;
independent complete text-region disagreements stay in the recovery record. Page
failures remain named and make the run fail while the other documents continue.
`audit-related-document-report` retains every outcome for 30 days. Read-only
`audit-related-document-evidence` retains source/native/structure/recovery files
for seven days. Existing source/structure and OCR artifacts are immutable and
unchanged replays do not rewrite their indexes.

The admin official-source comparison lists every related PDF as an expandable
document with its own page selector, original/source/structure links and recovered
text. `/api/admin/document-corpus` and `/api/admin/document-recovery` accept an
optional `related=<raw member SHA>` selected from the verified origin archive.
The reader validates transport, member name/bytes/hash, parent report and filing
bindings before resolving the separate native index. Missing or ambiguous
members and mismatched indexes fail explicitly; it cannot borrow the main report's
page or recovery. Pinned OCR model files are kept outside uploaded source artifacts.

Related-document admin access also requires the captured PDF hash to match the
raw member hash retained by the origin review. A valid primary-report revision
cannot be substituted under an attachment relationship. Wrapped related members
whose canonical bytes differ from their raw member hash remain inaccessible until
an explicit wrapper byte binding is verified; ordinary PDF members are supported.

Rendered-source identity witnesses may supplement native-span reviews when a
cover is scanned or has a damaged text encoding. Each binds the PDF hash, entire
canonical source-page hash, display-space region and exact reviewed transcription.
The reader verifies those bindings and the transcription's bank/date/basis claims;
it does not independently prove the transcription. The result explicitly labels
reviewer transcription, never creates native span references, and leaves automatic
identity findings and semantic approval unchanged. Only an introduction witness
is supported through this path; existing native cover contradictions stay intact.

Structured pages may include `table_context` with source-heading witnesses,
ordered column identifiers and physical merged-cell slots. A shared-grid result
requires every cell rectangle and empty slot to agree; otherwise no span is
inferred. Adjacent-page continuation candidates require an explicit continued
heading and identical ordered column identifiers. Competing earlier fragments
remain ambiguous; no rows, headings or original cells are dropped or merged.
These derived contexts participate in the structure engine and are recomputed
by validation. The admin displays merged slots and links to earlier fragments.
No relationship certifies financial meaning, units or full table completeness.

For independent visual review, `build-document-corpus.yml` accepts
`review_pages` (passed as `REVIEW_PAGES` / `--review-pages`): up to four ordered
page numbers with `limit=1..4`, or `ALL` with `limit=1` in Actions. This requires
`publish=false` and `quality_only=false`. The source is checked against its PDF
hash and byte count, then rendered at 150 dpi without OCR or text extraction.
`review-pages/review-manifest.json` inside each source folder records every
selected page, PNG/pixel hashes, display geometry, engine identity and named
failures. A failed page does not hide later pages and makes the capture fail.
The existing `audit-document-probe-evidence` artifact retains the pack for seven
days. These images are review inputs, never proof that content has been reviewed.

`complete_physical_table` source annotations name an entire table region, every
row/column slot (keeping null distinct from blank or zero), expected merged-cell
spans and separate contextual text witnesses such as units. The benchmark checks
every cell against its source-word occurrences and accounts for every source word
inside the independently reviewed region; omissions, duplicate references,
changed units and swapped identical-valued cells fail. This is bounded physical
transcription/association evidence, not whole-filing or financial-series approval.

A capture manifest's `source_url` is the registered locator supplied at capture
time. For an older acquired object it is not, by itself, proof of the URL that
originally delivered those bytes. Use the separately retained official-origin
receipt and timestamp to establish a fresh download/byte relationship. Language
editions and changed revisions remain separate evidence; do not overwrite an
acquired English translation merely because the registered BDDK URL serves a
Turkish PDF. Both exact originals must remain traceable.

Ambiguous multi-PDF downloads can use reviewed entries in
`data/banks/audit_document_origin_selections.json` (CLI override:
`review_document_origins.py --archive-selections <path>`). Each entry binds one
registered filing and exact HTTPS URL to the complete transport SHA-256, selected
member name/hash and either acquired-byte agreement or an independently reviewed
financial-report cover. The latter rechecks literal cover text; the former
rechecks the acquisition hash. Changed archive bytes, member bytes, URL, filing
or review evidence produce a named review outcome with the raw response retained.
The registry is validated before any source access. A selection for another URL
does not apply, including a bank URL versus its regulator alternative. Unselected
PDFs stay inventoried for separate attachment capture; previous failed origin
observations and acquired filings are preserved. Fourteen source-reviewed entries
cover Anadolubank/TSKB two-PDF archives; publication `34076924747` has independently
verified eight matches and six different PDF editions. Capture the other PDF in
each archive through `capture-related-documents.yml`.

EXIM 2025Q3 solo and HALKB 2026Q2 solo use independently checked bank-listed PDF
locators. `_source_url_history` in the bank registry retains the previous URL,
replacement listing and review context. Updating a locator does not replace an
existing acquisition: run an exact official-origin comparison and retain different
PDFs through `capture-document-edition.yml`. The previous unavailable response or
DOCX-only regulator archive stays in origin history.

Source-line structure for tall ruled cells is derived from retained word positions,
with exact original-cell word inventories and unambiguous baseline bands. Original
physical cells remain intact; note references are text, not newly parsed figures.
The TOMK 2023Q3 source annotations cover the complete shareholder grid/unit and
three source lines in the profit/loss statement, plus the complete six-slot
prior exchange-rate table with its currency headings and literal TL units.
Matching segmented top and bottom rules support this single-row table;
unmatched rules and missing value columns do not produce a candidate.
These checks do not certify the whole
report. The reviewed Anadolubank 2026Q2 solo archive selection is bound to its
86-page primary PDF hash; capture its separate signed member only after a fresh
origin observation has published that exact selection.

The separate `reading_layout` view partitions retained narrative-element boxes
into bands and columns. A standalone bullet is linked only to one adjacent
first source line, with a unique reverse association; aligned list items preserve
their physical order. Every original element occurs exactly once in the tree.
Areas without a unique partition remain explicitly unresolved in stored order.
The original narrative and its source span order are not rewritten. Layout
benchmarks bind expected order, list pairs and column groups to an exact PDF,
and independently recheck the referenced native wording. These checks do not
certify logical paragraph boundaries, signatory roles or full-document meaning.

Official-origin downloads from the exact ICBC hosts `www.icbc.com.tr` and
`icbc.com.tr` use the existing certifi-plus-GlobalSign intermediate bundle also
needed by BDDK. Certificate and hostname verification remain enabled; no fallback
to unverified transport is allowed. Origin response metadata names the verification
method. Other hosts keep the default trust store. A local source-byte probe
matched the 2026Q2 solo acquisition; the registered-bank follow-up runs in Actions.

Related-document captures now preserve an immutable identity review under the
source revision's `related-identity/` namespace. Its receipt binds the PDF hash,
native evidence digest, archive filing and exact identity rules. Related indexes
keep both the current receipt and history without restamping identical values.
A related source's inherited bank/period/basis fields label its archive context;
use its own opening-page claims to assess identity. A conflict is retained with
the source, not suppressed or relabeled. The private reader checks the receipt
bytes and native/container bindings before exposing its period observations.

Source annotations may include `source_review` cases with open notes and multiple
exact source passages. Source-only regression checks retain these in the resume
receipt; changes to notes or their validator invalidate annotation reuse. The
private corpus endpoint accepts `artifact=reviews`, rechecks the current native
revision and each passage, and returns source-bound open findings. It does not
resolve discrepancies or modify extracted values.

`review-document-origins.yml` also accepts `origin_source=bddk` (the
`ORIGIN_SOURCE` workflow input adapter / CLI `--source bddk`). The default stays
`registered`. BDDK mode posts the observed bank-listing search form, retains its
response under `document-corpus/v1/origin-listings/`, and requires one exact
registered bank/period/basis row. Bank identities use committed literal names in
`data/banks/bddk_audit_registry_names.json`; no guessed file URLs or fuzzy name
matching are used. The listing, transport, selected PDF and comparison remain
linked in the immutable origin receipt. Earlier observations and acquired PDFs
remain retained. A missing/ambiguous listing row or archive is a named failure.
The admin can download the retained listing through `artifact=source_listing`;
it is served as an attachment after its byte checksum is checked.


`capture-document-edition.yml` runs `scripts/capture_document_edition.py` in
Actions. Inputs are `filing` (BANK|YYYYQn|basis), `observation` (the exact SHA-256
of a retained `different_pdf_revision` origin receipt) and `publish` (default
false). The shell adapters are `FILING`, `OBSERVATION` and `PUBLISH`; existing
R2 secrets supply access. No acquisition lookup or D1 write is performed.

Before capture, the edition reader verifies membership in retained origin
history, the immutable receipt, actual transport/ZIP selection, selected PDF
and optional regulator-listing row. Native/structured artifacts remain under
`sources/<pdf_sha256>/`; the independent index lives at
`document-corpus/v1/editions/BANK/PERIOD/basis/<pdf_sha256>.json`. It retains all
origin-observation references attached to that edition. Matching bytes are
reused; unchanged publication leaves object versions alone. Acquisition objects,
main filing indexes and prior origin observations are not replaced.

The existing recovery selector scans every edition page and names each selected
page outcome; source-pixel OCR and table candidates remain unverified. No flagged
pages means only that the detector did not flag a page. The report artifact is
`audit-document-edition-report` (30 days); read-only captures also retain
`audit-document-edition-evidence` (7 days). A named processing failure fails the
run while preserving successfully written evidence.

The private origin route returns all verified observations and accepts
`observation=<receipt_sha256>` for an exact historical receipt or artifact. The
corpus/recovery readers accept `edition=<receipt_sha256>` for a separate edition,
or `related=<member_sha256>&origin=<receipt_sha256>` for an attachment in that
historical archive. Ambiguous source selectors are rejected. An edition is not
inferred to be a correction, translation, authoritative version or replacement.


The source decoder accepts the observed ZIP spanning marker (`PK 07 08`) before
a valid ZIP local header. It retains the marker and exact container bytes. A
single nested ZIP is automatic only when the outer archive contains one ZIP
and the inner archive contains one report PDF; both complete member inventories
and selections are retained. Extra inner members, member overrides, deeper
nesting, damaged end records or inconsistent local-header positions require
source review. This prevents a truncated outer archive from being silently read
as its inner archive. Historical origin outcomes remain unchanged; rerun the
specific filing comparison to retain a new observation after a decoder repair.


An origin follow-up may supply `filings` (workflow adapter `ORIGIN_FILINGS`, CLI
`--filings`): a comma-separated exact BANK|YYYYQn|basis list. Keep `banks=ALL`,
blank `period` and `kind=BOTH`. Every identity must be registered and unique;
conflicting broad filters, unknown filings and a limit that truncates the list
fail before source access. The report retains the complete requested filing list
in every worker, with a disjoint assigned count. This allows unresolved source
comparisons to be retried without downloading already resolved bank histories.


A tall physical body cell may span amount columns despite a printed partial
divider. `table_source_rows` can retain a separate `column_projection` only with
a complete earlier header grid, text on both sides of each missing boundary,
retained thin vertical-rule boxes covering at least 95% of the body's height,
no gap exceeding 2.5 median glyph heights and unique whole-word containment.
The projection stores header-row and drawing-occurrence witnesses. It does not
alter physical cells or parse figures. Isolated value/dash lines remain separate;
logical accounting rows are still unverified. Source benchmarks recheck literal
column text and full word occurrences against independently transcribed regions.

Vertical cell spans may connect multiple physical rows into one source-line group.
The derived `row_group` retains the exact source-row IDs and spanning-cell
witnesses. All words must occur exactly once inside their original columns and
unambiguous source baseline bands; horizontal merges in the group are rejected.
The admin displays each grouped source line once, including a closing balance
whose label cell spans an earlier row. Turning off the line view restores the
original row/column spans. These relationships do not certify logical rows.

`segmented_rules_and_source_lines` is a separate table alternative for a repeated
cell-width horizontal-rule chain with a preceding period-header rule. Complete
native heading blocks must cover the amount columns exactly once; blocks are
never truncated to fit. Original words must fit unique columns and disjoint
source-line bands. The result retains all rule, header-block and word occurrence
witnesses, original candidates, blank cells and merged heading slots. New page
records carry `segmented_tables_schema`; validation recomputes every alternative
from retained source geometry, including detection of a removed table. Older
captures remain readable. Complete-table annotations separately check every
slot, source word and contextual unit against independently transcribed regions.

`table_notes` preserves candidate links from numbered column identifiers to a
complete adjacent sequence of standalone numbered markers and paragraphs. All
markers and paragraphs must have unique source-line alignment, fit the table's
horizontal extent and remain close and ordered. Competing table interpretations,
duplicated markers or missing notes leave the sequence unlinked. Links retain
header word IDs, marker/paragraph span IDs, literal text and source rectangles.
Validation recomputes these references; independent `table_note_links` annotations
check exact numbered occurrences and complete transcribed paragraphs. Original
narrative and header cells remain unchanged, and meaning remains unverified.

New structures carry `navigation_schema=document-navigation-1` and a source-bound
`navigation` view. Native word occurrences retain body banners, complete contents
entries and printed footer observations; each link retains literal text, page,
word IDs and bounding boxes. Only a unique, complete, ordered body-section sequence
defines section ranges. Declared contents folios map directly to observed footer
occurrences, never inferred page offsets. Missing or competing matches remain
unresolved. Exact folded title matches retain their source lines; pages dominated
by three or more listed titles are marked as section-index candidates. Contents
targets outside the body section or differing from a unique body-title candidate
retain explicit disagreements. Validation recomputes the view and paragraph
section assignments from native evidence. Independent `document_navigation`
annotations check full contents titles, section boundaries, footer pairs and
source conflicts. This affects only the separate complete-document corpus;
legacy analytical sectioning and settled D1 partitions are unchanged. The initial
navigation regression is TOMK 2023Q3; broader coverage remains open.

Body headings also recognize literal CHAPTER banners. Where explicit banners are
absent, a standalone section numeral can bind to an exact, complete contents
title on the same physical baseline, with adjacent wrapped lines. Word boxes
must overlap vertically and remain close horizontally; dotted subsection numbers,
extra prose, changed titles and duplicate candidates do not resolve a section.
The complete ordered sequence requirement still applies. A distant Page-No
column on a contents-banner baseline is retained as source evidence without
hiding that section. `navigation_source_selection` annotations check reviewed
section boundaries, counts by section, selected full contents titles, selected
footer pairs and literal body markers; passing is only a selected-case result.
The admin exposes the contents section titles separately, including wording that
differs from the body. GARAN 2022Q4 consolidated and ALBRK 2026Q1 consolidated are
the initial selected-source regressions for these formats.

Narrative classification uses the native numerical and ruled candidates.
Overlapping `horizontal_rule_cells`, `segmented_rules_and_source_lines` and
positioned-text alternatives remain in the table views but do not split or
reclassify source paragraphs. Their inferred header rectangles can extend into
nearby prose; they are not authoritative paragraph boundaries. Aligned Roman
headings on the same page are treated as siblings despite small font-size
differences, while indented heading candidates can retain a parent. These remain
source-layout candidates and do not certify semantic hierarchy.

Publishing captures can replay the exact `c6e429ce49dad46d4217c68d0ea35d8c5fe4acc6b508ea690f03c55bed83a463`
to `9d4a83ae8331be87f793b2fd9878463f35178a4f40f70766f2e6010a81a4b438`
structure transition under PyMuPDF 1.27.2.3 without rerunning table detection.
`document_corpus_upgrade.py` is an adapter outside the extraction fingerprint;
both exact fingerprints must match its separately tested transition. It reads
only immutable-byte-verified retained structure for the same native evidence,
checks the original PDF identity before and after, inspects glyphs only on
ruled-table pages with source-reference mismatches, and recomputes dependent
source-row/header/note references. Full structure and source benchmarks still
gate publication. A corrupt eligible cache fails; an unavailable base or any
different extraction/library version takes normal full extraction. Default
read-only probes remain fresh and supply an independent comparison. Capture
results name `structure_build.method`, inspected glyph pages and changed tables;
an unchanged-object receipt can still skip a previously completed publication.
No figure or semantic approval follows from successful reuse.

The next exact transition is `9d4a83ae8331be87f793b2fd9878463f35178a4f40f70766f2e6010a81a4b438`
to `ca66890e81ae8c2d52a87a701193d3ea46f73ac5d7819e5f2e3d3d8ab5cd12e4`,
also under PyMuPDF 1.27.2.3. `document_region_upgrade.py` restores the retained
first-pass word cells, observes their separate PDF regions, and rebuilds
underline/segmented alternatives, narrative, reading layout, source rows, context
and note links. Native evidence, numeric candidates, original PDF bytes and
prior artifacts remain unchanged. Its result method is
`retained_table_region_upgrade`. Unsupported fingerprints use full extraction.

Region isolation prevents distant table rows from shifting another table's
columns during page-wide line snapping. A second observation includes the
detector's three-point boundary tolerance; overlapping/competing table regions,
changed native word inventories or lost/duplicated characters are not accepted.
Each accepted `region_refinement` retains the original bounds/shape, clip and
complete source-word IDs. Validation checks these source relationships. This
improves physical cells without certifying their financial meaning.

Fresh read-only R2 structure probes also attempt this exact retained-region
replay. `retained_structure_comparison.status=matched` requires equality of the
whole fresh/replayed JSON, not only successful validators. Missing bases report
`no_supported_retained_base`; other target fingerprints report
`unsupported_target`. Neither is a successful comparison. A disagreement fails
the probe with its fresh source artifacts retained. These comparison reads do
not publish, alter acquired PDFs or change analytical partitions.

The region replay also accepts exact `c6e429ce49dad46d4217c68d0ea35d8c5fe4acc6b508ea690f03c55bed83a463`
as its base. That version has the same initial grids, native evidence and numeric
candidates, before the character-link step. The combined replay reobserves the
regions first and then applies character links, matching fresh target extraction.
It prefers a retained 9d4a83ae revision when both exist. This can avoid an
intermediate corpus-wide publication solely to change word references. Other
source or extraction versions remain unsupported, and complete fresh/replay
comparison is still required before publishing a new transition across the fleet.

Complete physical-table source annotations can explicitly name `absent_slots`
for spaces outside a printed grid. The benchmark checks the exact transcribed
slot inventory, merged spans, nonoverlapping cell rectangles and common edges,
along with every source character occurrence and date/unit/title witnesses.
This is an annotation-backed check; general grid inference still abstains when
the candidate does not cover a complete rectangle. A null outside the grid,
a null covered by a merged cell, a printed empty cell, a dash and zero remain
different source facts. Global unit witnesses do not convert count, percentage,
rating or explicitly different-currency cells into financial amounts.

The next derived view is `source-period-headers-1`. It groups the original words
above witnessed table columns when every amount column has its own explicit
current/prior-period phrase. Physical cells and figures are unchanged. Crossing
words, incomplete source occurrence inventories, inconsistent grids and missing
labels cannot produce a band; multiple valid bands remain competing candidates.
New artifacts retain `table_period_headers_schema` and page-level
`table_period_headers`; validation recomputes the full view and rejects missing
pages, altered text/geometry/references and removal of the schema marker.

`document_header_upgrade.py` supports only PyMuPDF 1.27.2.3 and the exact
`ca66890e81ae8c2d52a87a701193d3ea46f73ac5d7819e5f2e3d3d8ab5cd12e4` to
`dda3201c09e2f487cd437283bdc53388217cc9982a3fc7db9a41a7a2fbcdf82a`
transition. It verifies the original/native/retained structure, adds the header
view and checks the full result without opening or extracting any PDF pages.
Capture results name `retained_period_header_upgrade` and zero
`pdf_pages_extracted`. Exact cache reuse remains first; unsupported/missing bases
use normal extraction and corrupt eligible bases fail. Read-only probes compare
the complete replay JSON to complete fresh extraction when the base is retained.
Cloud proof and publication are required before claiming this transition is live.


Complete physical-table annotations may carry `logical_rows` only for explicitly
source-reviewed rows. `document_table_review.py` requires whole source-word
occurrences in the reviewed row and column, exact independently transcribed
wording/order, and equality with the physical row's entire character inventory.
It rejects missing, duplicated or borrowed occurrences. Physical cells remain
unchanged. The review code participates in annotation receipt identity, so its
changes invalidate table-review reuse. Source-only receipts are unaffected.
These views do not rewrite series, convert units or automatically join pages.


Passed complete-table checks now include `reviewed_tables` records in the
existing capture receipt. Each record binds the native and structured page
hashes, the complete transcribed physical grid, merged/absent slots, source
context and explicit logical rows. Failed benchmarks do not emit reviewed
views. The private `/api/admin/document-corpus?artifact=table-reviews` endpoint
requires a filing and PDF page; it rechecks both pages and the receipt before
returning logical rows, provenance and original physical cells. It does not
promote a report to fully verified or assign financial meaning.

Use `build-document-corpus.yml` input `annotated_only=true` to publish only
filings named in the registered source annotation directory. Its nonsecret
step variable `ANNOTATED_ONLY` passes `--annotated-only` to the capture CLI;
the CLI requires `--capture`. Bank, period, basis and limit filters still apply,
followed by the existing stable shards. The inventory denominator remains the
full corpus. No matches is an error. The workflow rejects combination with
`acquire_missing` or `quality_only` and excludes acquisition before that job
can start. Identical retained structures are reused; this input does not force
extraction or alter D1. Publishing runs keep the existing serialized queue.

The narrative repair upgrades an exact retained `dda3201c` structure to
`35500cc8` with `retained_narrative_upgrade`. It reclassifies source prose
when a legacy numeric envelope encloses multiple separate ruled tables, retains uncertain
table-candidate links, and rebuilds narrative elements, reading layout, table
context and table-note links. It keeps original/native bytes and physical
tables unchanged and extracts zero PDF pages. Both original source identity
and complete structure accounting are checked before reuse. Read-only probes
compare the entire replay with fresh extraction when that exact base exists;
unsupported revisions continue through the established fresh path. Publish
this version after the period-header fleet has supplied its exact
base, without restarting the earlier corpus runs. Source-review annotations
may explicitly retain unassigned printed marks; they do not infer a financial
row association or certify the entire report.

Fresh cloud probes at `c6e4a90` independently match all 384 retained sample
pages, and the full eight-filing source benchmark passes all 85 cases. Combined
publication `34133467871` queues this version for all registered filings after
region `34112697713` and period-heading `34116379265`. It supersedes pending
review-only publications `34124160052` and `34127300076`; neither had started
a job when cancelled. Do not dispatch duplicate runs while this queue drains.
Receipt: `narrative-cloud-independent-verification.json` under
`docs/knowledge/2026-09-06-document-corpus/`.

Region fleet `34112697713` completed with 1,145 successful updates and one
R2 read timeout on ZIRAAT 2023Q4 solo. All 1,146 outcomes are reconciled, with
that filing's previous published source retained. The running period fleet
and queued narrative fleet already select it, so no duplicate publication was
dispatched. Fresh read-only probe `34133959596` succeeds; its downloaded
artifacts independently pass all 151 pages of source/structure accounting and
match the prior original/native digests. The timeout does not establish a source
defect. Receipt: `ziraat-timeout-independent-verification.json` in the same
internal evidence directory.

A complete-table annotation may contain `reviewed_grid` with independently read
literal rows, exact source-word occurrences, merged spans and explicit x/y
transcription boundaries. These boundaries must refine all original physical
boundaries, remain inside the original table and retain each source character
exactly once. They do not assert additional physical PDF rules. Covered slots
remain null; blank cells, dashes and literal zero remain distinct. Reviewed
word membership uses centres, allowing independently checked adjacent printed
lines whose font boxes overlap. Ambiguous baseline order fails. The annotation
cannot combine this full-grid view with other row assignments. Both the Python
benchmark and private Worker reader validate the same source-bound view.
Changes to its validator invalidate table-review receipts, without changing
native/structure extraction versions or source-only receipts. Publish updated
review receipts with the existing scoped capture controls after source proof;
there is no need to restart either full-corpus extraction fleet.
