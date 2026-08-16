# Architecture

End-to-end cloud stack. Ingestion runs in GitHub Actions; storage is
Cloudflare R2 + D1; display is Next.js on Cloudflare Workers. No local
machine is involved in the production data flow.

## Data flow

```
              ┌─── BDDK API ────┐    ┌─── Bank IR sites ────┐    ┌─── TCMB EVDS ────┐
              │                 │    │                      │    │                  │
              ▼                 ▼    ▼                      ▼    ▼                  ▼
       monthly bulletin    weekly bulletin            audit-report PDFs        macro / rates
              │                 │                           │                       │
              ├─────────────────┼─────────┐                 │                       │
                                          │                 │                       │
                          (Python scrapers, run in GitHub Actions)                  │
                                          │                 │                       │
                                          ▼                 ▼                       ▼
                              data/bddk_data.db         Cloudflare R2          (same DB)
                              (SQLite, ephemeral             │                       │
                               on the runner —               │  bucket: bddk-audit-reports
                               re-built each cron            │                       │
                               from the R2 .db.gz snapshot)  │                       │
                                          │                 │                       │
                                          ▼                 ▼                       ▼
                                    scripts/push_to_d1.py — incremental sync
                                                    │
                                                    ▼
                                       Cloudflare D1 (bddk-data)
                                                    │
                                                    ▼
                                       web/ — Next.js 16 + OpenNext
                                       Deployed to Cloudflare Workers
```

## Components

| Layer | Path | Tech |
|---|---|---|
| **BDDK scrapers** | `src/scrapers/` | Python — monthly + weekly bulletins |
| **EVDS client + scraper** | `src/scrapers/evds_client.py`, `evds_scraper.py` | TCMB EVDS v3 HTTP client |
| **TBB digital-banking** | `src/tbb/` | Python — quarterly `.xls`/`.xlsx` workbook → tidy `tbb_digital_stats` |
| **TKBB participation digital** | `src/tkbb/` | Python — TKBB Veri Peteği (Turboard JSON API) → `tkbb_digital_stats`, `tkbb_acquisition_stats` |
| **TEFAS fund market** | `src/tefas/` | Python — rate-limited tefas.gov.tr JSON client → per-day sector aggregates in `tefas_*` (per-fund rows not persisted) |
| **KAP ownership** | `src/kap/` | Python — KAP Genel Bilgi Formu §5 + §7 → `kap_ownership` (weekly full replace) |
| **News + regulations** | `src/news/` | Python — KAP / TCMB / BDDK / press / Google News → `news_items`; free-LLM clients (`free_llm.py`, `kimi.py`) for "The Read" + `regulation_briefings` |
| **Earnings calendar** | `src/earnings/` | Python — KAP results filings + IR presentation decks → `bank_earnings` |
| **Franchise (annual reports)** | `src/faaliyet/` | Python — Faaliyet Raporu PDFs → `faaliyet_franchise`, `faaliyet_extractions` |
| **Non-bank lenders** | `src/nonbank/` | Python — BDDK non-bank monthly bulletin → `nonbank_balance_sheet` |
| **Advertised rates** | `src/rates/` | Python — doviz.com (loans) + hangikredi (deposits) → `bank_advertised_rates`; the only **per-bank** rate source (EVDS/BDDK publish rates at sector level only) |
| **TÜİK tables** | `src/tuik/` | Python — veriportali cookie-session → `.xls` downloads (series EVDS lacks) |
| **Audit-report extraction** | `src/audit_reports/` | **PyMuPDF (fitz) only** for every lane — pdfplumber was removed entirely on 2026-07-15 (the frozen BS/P&L `extractor.py`, `profiler.py`, and `src/faaliyet/extractor.py`, the last holdouts, moved to `_fitz_page_text`, a strict superset of the old pdfplumber layout-repair). `_fitz_page_text` is the single text reader; don't add another PDF engine. See `docs/AUDIT_EXTRACTION_GUIDE.md` |
| **R2 wrapper** | `src/audit_reports/r2_storage.py` | boto3 against S3-compatible R2 |
| **D1 sync** | `scripts/push_to_d1.py` | incremental push via wrangler. Audit lanes pass `--table-set audit` — the table list is derived from `src/audit_reports/registry.py`, never hand-written (a hand-written copy is what silently kept `bank_audit_fx_position`/`_repricing` out of D1) |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, ~1.6M rows |
| **PDF storage** | Cloudflare R2 (`bddk-audit-reports`) | ~2.2 GB; **~1,100 quarterly PDFs** extracted across the 38-bank universe (1,093 extractions as of 2026-08-13; the 2026Q2 season is filling in) |
| **Dashboard** | `web/` | Next.js 16 + OpenNext + Recharts (charts) + d3-force (/ownership network layout) on Cloudflare Workers |
| **Mobile app** | `mobile/` | Expo SDK 57 + expo-router + React Native 0.86 + react-native-svg. Read-only native client over `/api/app/v1` — see § Mobile app |
| **Q&A bot (Telegram)** | `web/app/lib/bot.ts` + `web/app/api/telegram/webhook/` | public Q&A over the same D1: agent loop behind a read-only SQL gate + grounding guard — see [TELEGRAM_BOT.md](TELEGRAM_BOT.md) |
| **Read cache** | Cloudflare KV (`NEXT_INC_CACHE_KV`) | 1h data cache for D1 reads (`cachedAll` → `unstable_cache`) |
| **Admin panel** | `web/app/admin/`, `web/app/api/admin/` | password-gated control center: data health, refresh triggers, traffic |
| **Quality gates** | `.github/workflows/ci.yml`, `pyproject.toml`, `tests/` | ruff + pytest + eslint + tsc + vitest on every PR |
| **Schema migrations** | `web/migrations/` | hand-authored, version-controlled; applied via `wrangler d1 migrations apply` on deploy |

## Workflows

The ingestion workflows split along **two independent storage lanes**, so a
failure in one can't stall the other:

| Lane | Staging DB | R2 snapshot | Concurrency group |
|---|---|---|---|
| BDDK bulletins + EVDS | `data/bddk_data.db` | `state/bddk_data.db.gz` | `bddk-pipeline` |
| Bank audit reports | `data/bank_audit.db` | `state/bank_audit.db.gz` | `bddk-audit` |

> The whole topology — sources → these workflows → D1/R2/KV → dashboard pages,
> with the two lanes banded apart — is visualized interactively on the **`/pipeline`**
> tab (React Flow; storage nodes show live D1 row counts + freshness, workflow nodes
> their last GitHub Actions run). Source of truth: `web/app/lib/pipeline-graph.ts`.

The two lanes share no snapshot, so the audit workflow runs in parallel with
the bulletin/EVDS workflows. Their only shared sink is D1, where they write a
**disjoint** set of tables (`bank_audit_*` vs everything else) with idempotent
`INSERT OR REPLACE`.

**Most tables sync incrementally** (a time-windowed `INSERT OR REPLACE`). Two of
the coverage-matrix **spine** tables — `bank_audit_expected` /
`bank_audit_statement_types` — are **full-rebuild**: `push_to_d1.py` emits
`DELETE FROM <t>; INSERT …` from the local copy, because those rows are computed
wholesale by `sync_audit_expected.py` (no per-row timestamp). The third,
`bank_audit_coverage`, left full-rebuild on **2026-08-06**
(`_COVERAGE_INCREMENTAL` in `push_to_d1.py`): its cells are windowed on
`derived_at` (migration 0040) and removals travel through the
`d1_pending_deletes` outbox, so a change ships only the cells it moved instead
of restating all ~20,000 rows. Full-rebuild is the one place the shared-D1
design has a footgun: those tables are only populated in `bank_audit.db`; in
`bddk_data.db` they're created-but-empty, so a daily news/EVDS push from the
bulletin lane would `DELETE` the spine and insert nothing — **wiping the /admin
coverage matrix** even though the audit lane never ran. The guard:
`push_to_d1.fetch_recent` **skips a full-rebuild table whose local copy is empty**,
so a push can never wipe a table it has no rows for. (Recovery recipe in
[OPERATIONS.md](OPERATIONS.md) → Troubleshooting.)

One audit table is **derived, not extracted**: `bank_audit_stages` is built from
`bank_audit_credit_quality` (Stage-1/2 loan amounts + the BRSA NPL Stage-3 +
ECLs) by `scripts/build_bank_audit_stages.py`. So re-extracting `credit_quality`
must **rebuild stages**. The routine audit workflow rebuilds afterward; targeted
re-extraction rebuilds the affected partition inside the candidate savepoint,
before acceptance, so source and derived rows cannot disagree after a repair.

### Daily — `.github/workflows/refresh-evds-daily.yml`
Sun–Fri 05:00 UTC. Polls only EVDS series declared daily/workday, keeping FX,
policy/funding rates and sterilization current within 24h. Weekly, monthly and
quarterly EVDS series are polled by Saturday's full refresh. Every unrelated
`refresh.py` lane is explicitly skipped, and a byte-stable DB result skips the
D1 push and R2 upload. A separate daily job, `refresh-news-daily.yml` (04:00 UTC),
refreshes `news_items`.

### BDDK bulletins — `.github/workflows/refresh-bddk-bulletins.yml`
Isolated BDDK-only refresh (`--skip-evds`, no audit), split by schedule via
`github.event.schedule`:
- **13:00 UTC on the first and last five days** — monthly check around BDDK's
  normal month-end publication window. `update_monthly.py` still probe-then-fetches.
- **Friday 13:30 + 15:30 UTC** (16:30 & 18:30 Turkey) — weekly. BDDK publishes the
  weekly bulletin Friday afternoon; two runs bracket the window (~30 min).

The former Saturday 02:00 backstop is removed: the full Saturday workflow runs
at 03:00. Quiet runs stop before D1 and R2.

A positive Telegram ping ("published & fetched", `notify_new_bddk.py`) fires when
a weekly/monthly period newly lands; quiet otherwise.

### Weekly full — `.github/workflows/refresh-data.yml`
Saturday 03:00 UTC. BDDK bulletins + EVDS + TBB digital + TKBB participation
digital + KAP + TEFAS + Faaliyet franchise:
1. Decompress `state/bddk_data.db.gz` (pulled from R2) → `data/bddk_data.db`
2. `scripts/refresh.py` — monthly + weekly + EVDS scrapes + TBB quarterly
   digital-banking refresh + KAP ownership + TEFAS fund market into SQLite
   (TBB/KAP/TEFAS are non-critical steps; an outage in one won't abort the
   BDDK refresh)
3. If SQLite is unchanged, stop. Otherwise `scripts/push_to_d1.py --hours 168`
   pushes the week's rows to D1
   (idempotent via INSERT OR REPLACE; covers `tbb_digital_stats`,
   `kap_ownership` and the `tefas_*` tables too)
4. VACUUM + re-gzip + upload the snapshot back to R2

### The satellite lanes — small, scheduled, one table each
Four crons ride the bulletin lane's snapshot and concurrency group, each writing a
single table. They're listed here because a lane nobody documents is a lane nobody
knows is running:

| Workflow | When | Writes |
|---|---|---|
| `refresh-advertised-rates.yml` | Mon 06:00 UTC | `python -m src.rates.scraper` → `bank_advertised_rates` (per-bank posted loan/deposit rates; the sources only expose "today", so history accretes forward) |
| `refresh-calendar.yml` | 1st of month 06:00 UTC | `python -m src.release_calendar.scraper` → `release_calendar` (TCMB's published calendar — MPC decisions/minutes, Inflation Report, Financial Stability Report; feeds the Ahead strips, retires the hand-typed `MPC_DATES`) |
| `refresh-presentations-weekly.yml` | Sat 06:00 UTC | `update_presentations.py` → `bank_earnings` (IR presentation decks) |
| `refresh-transcripts-weekly.yml` | manual (no cron yet) | `update_transcripts.py` → `bank_call_transcripts` (earnings-call transcripts, 8 listed banks). Ships without a `schedule:` and with `push` defaulting to false — a posture from the 2026-08-01 write freeze; the freeze has lifted, and turning the cron/push on is a decision not yet taken |
| `summarize-regulations.yml` | Sun 06:00 UTC | `summarize_regulations.py` → `regulation_briefings` (weekly Kimi briefing; needs `KIMI_API_TOKEN`) |
| `generate-reads.yml` | Sun 07:30 UTC | `generate_read_headlines.py` → `read_headlines` (free-LLM rewrite of the one-sentence lead on each T1 tab; number-validated, and shown only while its `det_hash` matches the live page) |

Seven more workflows are **manual dispatch only**. Six exist to load or strengthen
history, not to keep it fresh: `backfill-audit.yml`,
`backfill-audit-source-capture.yml`, `backfill-document-capture.yml`,
`backfill-faaliyet.yml`,
`backfill-nonbank.yml` and `backfill-tefas.yml`. The seventh,
`repair-loans-zeros.yml`, is a one-time idempotent correction — it re-derives the
zeros `_save_loans` discarded (falsy `or` chains turned every reported 0 into
NULL) from the raw responses already on disk. Recipes in
[OPERATIONS.md](OPERATIONS.md).

### Audit reports — one automatic path, one manual diagnostic
Standalone audit pipeline on its own DB + snapshot. `refresh-audit.yml` runs
daily only during filing windows and remains manually dispatchable:
1. Pull/seed `data/bank_audit.db`
2. Discover/download new PDFs and extract pending PDFs from R2 (or `--only-bank`
   / `--periods … --force` for a targeted re-extract, passed via the workflow's
   `bank`/`period` inputs from the /admin coverage matrix)
3. If nothing changed, stop with no D1 or snapshot write
4. Build stages, revalidate and rebuild the coverage spine locally
5. One `push_to_d1.py --table-set audit-refresh` batch (registry tables + spine)
6. VACUUM + re-gzip + upload `state/bank_audit.db.gz` (the snapshot WRITER)

`acquire-audit.yml` is now manual-only: an acquisition-only diagnostic for an
operator who deliberately wants a PDF in R2 without running extraction. Both
workflows share `bddk-audit`, so they cannot overlap.

**`reextract-statement.yml`** (dispatch-only) — targeted **single-statement** fix
on the same lane. Registry keys resolve to the extractor token, source table and
complete validation gate. `only_failing=true` selects a partition when any required
relationship is not a proven pass; `require_passing=true` accepts a candidate only
after all required results pass. Balance-sheet repairs require both internal
hierarchies plus A=L+E; credit-quality repairs rebuild and validate stages inside the
same savepoint. Rejected source, derived and validation rows roll back together, and
only factually changed tables are pushed. This is how OCI/CF/NPL/loans_by_stage were
fixed fleet-wide without re-running the frozen BS/P&L extraction.

**`backfill-audit-source-capture.yml`** (dispatch-only) — the evidence-only
historical upgrade for eight normalized/summary lanes. It downloads the existing
R2 PDFs, stores their bounded disclosure-page lines in the local/R2 snapshot, and
pushes only a compact source-count/hash manifest plus changed validation rows to
D1. It never calls an analytical upsert. Near-full lanes fail on an unknown numeric
source row; selected-summary lanes retain/count their intentionally omitted detail.
New extracts do this in the normal transaction; this workflow only closes the
historical gap.

**`backfill-document-capture.yml`** (dispatch-only) — the same idea taken from
lane-scoped to **document-scoped**. It reads every page of every filing and
records each table the bank prints — rows, inferred columns, cells — plus the
footnotes that qualify them, linked to the rows carrying their marker. Its point
is that a table nobody has written a parser for yet is captured anyway, so
adding a lane later is a query against the ledger instead of a fleet re-read of
1,050 PDFs. It writes no analytical row, so it is safe over the settled BS/P&L.
The ledger (5.4M lines / 11.2M cells, measured over the full fleet 2026-08-13)
goes to its own R2 object and its own
local `data/bank_audit_capture.db`, never into the audit snapshot that every
workflow downloads; only `bank_audit_document_manifest` — one row per filing —
reaches D1.

**`measure-free-provision.yml`** (dispatch-only) — the same read-only posture,
aimed at one extractor. It downloads every audit PDF from R2, re-runs
`classify_free_provision`, and diffs the result against the values already in
the snapshot; the diff returns as an artifact and nothing is written anywhere.
It exists because a *page-selection* change is corpus-wide by construction: the
defect that prompted it made TEB 2026Q1 store a free provision of 0 while the
filing states ₺1,108,135k, because the classifier read a later reversal note
whose prior-period parenthetical said `Bulunmamaktadır`. Two more partitions
carried the same fingerprint. Knowing which cells a fix moves — and that it
moves no others — has to come before any re-extraction is authorised.

**`audit-triage.yml`** (dispatch-only) — the *diagnosis* half of the same lane,
and the only one that writes nothing at all. The validator records which identity
broke; `src/audit_reports/triage.py` works out why, by comparing the stored rows
against what the filing actually prints and assigning one of a fixed set of
mechanical causes — a column the extractor never read, a row it never extracted, a
value taken from the wrong column, a cell word-wrapped out of reach, a missed
anchor, a drawn page, a rotated page, the wrong PDF, a unit change, or a source
that genuinely does not foot. Deterministic throughout: no model is consulted and
no figure is produced, so a verdict is a hypothesis with its evidence attached
rather than an assertion. Its companion `scripts/watch_cross_period.py` compares
each partition with the same bank one quarter earlier, which is the only place a
reporting-unit change can be seen — every in-filing identity is a ratio of figures
sharing a scale, so all of them foot when the whole filing moves by 1000×.

**`analyst-daily.yml`** (dispatch-only — the intended daily cron is wired but
commented out; turning it on is a decision not yet taken) — the analyst layer on
top of the same snapshot. Deterministic detectors
(`src/analyst/` — reporting-unit switches, cross-period restatements the
validators deliberately skip-list, opinion-type/category changes via the
basis-text classifier, perimeter changes, and the two
headline-conceals-composition divergences: CAR−CET1 and NPL-vs-coverage), then
per-bank memos: `web/app/lib/analyst/` assembles an 11-section deterministic
view (with the mix-vs-erosion coverage decomposition precomputed), a free-model
LLM writes connective prose, and the bot's figure guard drops any paragraph
whose numbers are not in the data it was shown. Migration
`0037_analyst_signals.sql` is **applied** — `analyst_signals` (455 rows),
`analyst_basis_metadata` (1,050) and `analyst_notes` (2) are live in D1 — and
the workflow carries a D1 push step gated on its `push` input (off by default;
staging in `data/analyst.db`, persisted to R2 as `state/analyst.db.gz`).
Without `push`, signals + memos leave as run artifacts only. (The 2026-08-01
write freeze that originally forced artifacts-only has lifted.)

**`analyst-research.yml`** (dispatch-only, artifact-only, evaluation phase) —
Analyst V2: agentic discovery over deterministic evidence. A story-agnostic
scout surfaces what moved (per-row deltas, own-history z-scores, reconciliation
breaks); a bounded research loop lets the model investigate through typed
read-only tools (full statement matrices, row histories, cross-statement
reconciliations, filing-page text) building a hypothesis ledger; findings are
STRUCTURED claims with evidence ids; a deterministic verifier checks entity/
period/kind association, comparison direction, arithmetic, contradictions,
causal-language and forecast policy — beyond V1's lexical guard. Nothing
reaches D1; abstention is a first-class outcome. Contracts and limitations:
[ANALYST_V2.md](ANALYST_V2.md).

**`purge-partition.yml`** (dispatch-only) — the inverse operation: removes one
`(bank, period[, kind])` from the lane via `scripts/purge_partition.py`, in the
one order that makes it stick — pull snapshot → delete locally → delete in D1 →
**re-upload the snapshot**. Clearing D1 alone does not hold: the snapshot keeps
the rows and the next `push_to_d1` from any later extraction restores them. The
R2 **PDF is left in place**, so the coverage cell returns to `missing` *with*
`pdf_present` — "acquired, awaiting extraction" — and a re-extract brings it back.

It exists for the failure mode no validator can reach: an extraction that is
internally consistent and still wrong. **TEB's 2026Q2 filing switched its
reporting unit from thousands to millions of TL**, so every figure landed 1000×
too small — and because uniform scaling cancels on both sides of every internal
identity (assets = liabilities, subtotal = Σchildren), the balance sheet and P&L
validated *green*. Only `fx_cross_period`, which anchors the prior column against
the independently extracted prior year-end, went red. The lesson generalises: **no
internal identity can detect a unit change; only a cross-period or external anchor
can.**

### Deploy — `.github/workflows/deploy-cloudflare.yml`
**After CI passes on the same commit** (`workflow_run` on `CI`, `conclusion ==
success`, push events on `master`). Applies D1 migrations (`wrangler d1
migrations apply`), builds the OpenNext bundle, and deploys to Cloudflare
Workers.

Until 2026-08-01 this was `on: push` with a `paths:` filter, which meant it
*raced* CI rather than waiting for it — no `needs:`, no branch protection, so a
red CI did not stop a deploy and the D1 migration step ran before any check had
passed. `workflow_run` carries no path filter, so the deploy now builds on every
green CI on master rather than only on `web/**` changes: a few minutes of free
Actions time, traded for never shipping unchecked, and never silently skipping.

### Health check — `.github/workflows/healthcheck.yml`
Daily 06:00 UTC. Queries D1 freshness per source + audit failure count and
alerts (`scripts/notify.py` → Telegram/Discord) when data is stale or
extractions spike. Also asserts the Q&A bot's Telegram webhook still points at
the live origin — Telegram keeps delivering to whatever URL it was last given,
so the bot can go silent with nothing failing on our side.

### Telegram webhook — `.github/workflows/telegram-webhook.yml`
Manual only. `set` / `info` / `check` for the Q&A bot webhook
(`scripts/setup_telegram_webhook.py`). In CI because `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_WEBHOOK_SECRET` aren't available locally. Re-run `set` after anything
that moves the site origin.

### CI — `.github/workflows/ci.yml`
On every PR (and master push): Python `ruff` + `pytest`; web `eslint` + `tsc` +
`vitest` (`npm run test` — unit tests for pure lib code, e.g.
`app/lib/pl-sankey.test.ts`); and mobile `eslint` + `tsc` + `check:tokens` +
a Metro bundle. Dependency updates come via `.github/dependabot.yml`
(pip / npm / github-actions, weekly).

## Mobile app

`mobile/` is an Expo (React Native) client for iOS and Android. It is a **second
view of the same data**, not a second pipeline: it reads `/api/app/v1` on the
same Worker, which reads the same D1 through the same `web/app/lib/` query
modules the website renders from.

### Why a private API rather than `/api/v1`

`/api/v1` is a published product surface — a documented series contract that
third parties build against, so its shapes can only ever be added to.
`/api/app/v1` is the private wire format between our own Worker and our own
client: screen-oriented, denormalised, and free to change whenever a screen
changes. Keeping them apart is what lets the app iterate without freezing the
public API.

| Endpoint | Screen | Reuses |
|---|---|---|
| `GET /api/app/v1` | launch handshake (`minSupportedClient`) | — (no D1 read on the launch path) |
| `GET /api/app/v1/overview` | Overview | `metrics.ts`, `desk.ts`, `insights.ts`, `audit-ratios.ts`, `real-terms.ts`, `ahead-data.ts` |
| — | *(no market tape)* | `market-ticker.ts` is deliberately **not** called here — Yahoo terms forbid redistribution, which a store listing makes formal. USD/TRY comes from EVDS `TP.DK.USD.A` instead. Website unaffected. |
| `GET /api/app/v1/banks` | Banks index | `heatmap.ts`, `audit.ts`, `bank_names.ts` |
| `GET /api/app/v1/banks/{ticker}` | Bank detail | `heatmap.ts`, `audit.ts`, `news.ts` |
| `GET /api/app/v1/economy` | Economy | `economy.ts` |
| `GET /api/app/v1/news` | News | `news.ts` |

Kill switch: `APP_API_DISABLED=1` on the Worker. **Separate** from
`PUBLIC_API_DISABLED` on purpose — that one sheds third-party load in an
incident, and reusing it would black out every installed app at the same moment.

### The invariant that matters

**No metric is derived in the app.** Every ratio, deflation and streak is
computed server-side by the same `web/app/lib` function the website calls, so
the two surfaces cannot print different values for the same metric. The client
formats (`mobile/src/format.ts`) and writes copy around figures; it never makes
them. A new number goes into `web/app/lib` first.

### Deliberate divergences from the website

- **Four tabs, not ~30 routes.** Overview / Banks / Economy / News. The depth
  routes (`/capital`, `/liquidity`, `/cross-bank`, `/regulation`, `/pipeline`)
  stay on the web, and each screen links out.
- **The sheet is the screen.** The Desk's white-sheet-on-paper figure-ground
  needs margins the phone doesn't have, so `card` becomes the screen fill —
  which is what the website itself already does below the `lg` breakpoint.
- **Single-series charts only.** Partly because a multi-series line chart is
  unreadable at 390pt, and partly because the categorical ramp fails the
  colorblind check in dark mode (`--chart-2` vs `--chart-1` scores ΔE 6.1 for
  *normal* vision, below the 15 floor). The website gets away with it via
  direct-labelled chart feet; a phone chart has no room for one. See
  PROJECT_STATE.md § Known issues.
- **Payloads are trimmed server-side.** Sparklines ship 13 points, metric trends
  8 quarters, macro series 48 months. Full history stays on the web.

### ⚠️ `heatmapPanel()` is a RANKING, not the universe

`heatmapPanel()` refuses to hold a peer-excluded bank at all — `ensure()` hands
those callers a throwaway row, because every rank, colour scale and percentile
downstream is computed off that map. Building the bank index off it dropped
Takasbank from the app entirely and 404'd a bank the website lists and serves a
full page for.

The spine of any *universe* query is `bankSummaries()` (unfiltered); ratios are
left-joined from the panel where they exist. `/api/app/v1/banks` returns both
`count` (38, the universe) and `peers` (37, the rankable subset) so a client
cannot rank off the wrong one, and `/banks/{ticker}` carries
`scorecardAvailable` + `scorecardNote` so an absent ratio prints its reason
rather than an em dash that reads as a blank filing.

### Theme tokens

`mobile/src/theme/tokens.ts` is a hand-copy of `web/app/globals.css` (React
Native cannot read a CSS custom property). `mobile/scripts/check-tokens.mjs`
re-reads the CSS and fails CI on any divergence, so the two copies cannot drift.

## Why the SQLite snapshot exists

The cron pipeline uses a local SQLite as a staging area between scrapers
and D1 (it's cheap to query, supports complex SQL the scrapers expect,
and gives us a backup of the canonical numbers). After each run the
gzipped snapshot is uploaded to R2 so the next cron starts from the last
known state without re-scraping from scratch.

The two ingestion lanes persist one snapshot each: the bulletin/EVDS lane
`state/bddk_data.db.gz` (~55 MB) and the audit lane `state/bank_audit.db.gz`
(the `bank_audit_*` tables only). The audit lane bootstraps its snapshot on
first run by seeding from the bulletin snapshot (`scripts/seed_audit_db.py`)
rather than re-extracting every PDF.

Three more staging stores sit beside the two lane snapshots, each with its own
persistence posture: `data/analyst.db` (analyst-lane state — signals + memo
hashes — rides R2 as `state/analyst.db.gz`), `data/bank_audit_capture.db` (the
full-document capture ledger — its own R2 object, never the audit snapshot;
only the one-row-per-filing manifest reaches D1), and
`data/bank_audit_prose.db` (the 369k-row historical prose backfill —
local-only, not yet merged or pushed).

Production dashboard reads go to D1, not this snapshot — the R2 copy is
purely pipeline state.

**Backups & recovery (free):** each run also writes a dated copy
`state/history/<lane>-YYYYMMDD.db.gz` and keeps the last 7, so a corrupt run
can't destroy the only snapshot. For the serving DB, D1 **Time Travel** gives a
7-day point-in-time restore. See [OPERATIONS.md](OPERATIONS.md) → Disaster recovery.

## Dashboard read caching

Dashboard pages are dynamic (server-rendered per request), but the D1 queries
behind them are cached: `web/app/lib/db.ts` `cachedAll()` wraps reads in
`unstable_cache` (1h TTL — it was 12h to stay under the free tier's 1,000 KV
writes/day; the paid plan's 1M/month allowance removed that constraint, so the
window was cut 12× for fresher pages), keyed by SQL + params and backed by the
`NEXT_INC_CACHE_KV` namespace via OpenNext's incremental cache
(`open-next.config.ts`). The hot `metrics.ts` query helpers route through it, so
identical queries hit D1 at most once per hour instead of on every page view —
cutting D1 rows-read sharply.

Pages stay dynamic on purpose: page-level ISR (`export const revalidate`) would
prerender the data pages at build time, which queries D1 against the empty
build-time DB and fails. Caching the *data* (not the page) avoids that. `/admin`
is intentionally uncached (auth-gated + shows live pipeline status).

The `/ownership` sector graph is built server-side off two cached queries
(`sectorOwnership()` in `web/app/lib/kap.ts` for the graph, `bankSummaries()`
for asset-based node sizing — fail-soft to uniform sizes). The force-directed
layout (d3-force, `web/app/lib/ownership-force.ts`) runs synchronously in a
`useMemo` with seeded positions and a seeded random source, so the server
render and client hydration agree; all interaction (zoom, ego-highlighting,
focus, tooltips) is client-side on the serialized graph, so clicking around
costs zero extra D1 reads.

For local dev, `web/next.config.ts` calls `initOpenNextCloudflareForDev()` so
`next dev` resolves the D1/KV bindings against the local wrangler/miniflare
state — seed tables with `npx wrangler d1 execute bddk-data --local --file …`
to work on data pages offline.

## Admin control center

A password-gated `/admin` route (see [ADMIN.md](ADMIN.md)) surfaces data-freshness
per source, audit-extraction failures, GitHub workflow run status + manual
triggers, and Cloudflare Web Analytics — reading D1 plus the GitHub/Cloudflare
APIs through route handlers under `web/app/api/admin/`.
