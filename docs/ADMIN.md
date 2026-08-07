# Admin control center

A protected `/admin` page in the dashboard that consolidates **pipeline/data
health**, **manual refresh triggers**, and **site traffic** into one view.

- URL: `https://<dashboard-host>/admin` (not linked from the public nav).
- **Safe-by-default**: until an auth method is configured the page is locked —
  it is never publicly readable.
- Two auth modes (auto-selected): **password** (default, works on the free
  `workers.dev` URL) and **Cloudflare Access** (only when on a custom domain).
- Everything degrades gracefully: health works as soon as you can log in; the
  Pipeline and Traffic panels show a "not configured" hint until their tokens
  are added.

## Code map

| Piece | File |
|---|---|
| Auth (password session + Access JWT) | `web/app/lib/admin-auth.ts` |
| Login / logout endpoints | `web/app/api/admin/{login,logout}/route.ts` |
| Env reader | `web/app/lib/cf-env.ts` |
| D1 health queries | `web/app/lib/admin-health.ts` |
| GitHub Actions client | `web/app/lib/github.ts` |
| Web Analytics client | `web/app/lib/cf-analytics.ts` |
| Page + panels + login form | `web/app/admin/{page,PipelinePanel,TrafficPanel,PurgeCacheButton,LoginForm}.tsx` |
| Coverage matrix + drawer | `web/app/admin/coverage/{CoverageMatrix,CoverageDrawer,status}.{tsx,ts}` |
| Coverage queries | `web/app/lib/coverage.ts` |
| Runs / dispatch / coverage / purge-cache endpoints | `web/app/api/admin/{runs,dispatch,coverage,purge-cache}/route.ts` |
| Presentation deck (route + data + HTML builder) | `web/app/api/presentation/route.ts`, `web/app/lib/presentation-data.ts`, `web/app/lib/presentation-deck.ts` |
| Telegram webhook self-register | `web/app/api/admin/telegram-register/route.ts` |
| Telegram bot test harness (gated by `BOT_TEST_KEY`; 404s while unset) | `web/app/api/admin/bot-ask/route.ts` |
| Web Analytics RUM beacon (rendered manually — see §3) | `web/app/components/Beacon.tsx` |
| **Agent register** (page + diagram + run controls) | `web/app/admin/agents/{page,AgentFlow,AgentRunControls}.tsx` |
| Agent roster (hand-authored, CI-gated) | `web/app/lib/agents-registry.ts` |
| Agent list / dispatch endpoints | `web/app/api/admin/agents/{route,dispatch/route}.ts` |

### Managing audit reports (the intended workflow)

Audit discovery and extraction run automatically each day during the quarterly filing
windows. `refresh-audit.yml` takes a valid new PDF all the way from the bank site through R2,
extraction, validation, one D1 batch and the snapshot. This panel remains the control surface
for targeted repairs and for manual checks outside those windows.

- **Filing season panel** (`web/app/admin/FilingSeason.tsx`, `web/app/lib/filing-season.ts`) —
  one level above the matrix: per bank, has the **in-window quarter** been published, and in
  what form? Read-time derivation, no new table or workflow. The tracked window mirrors
  `refresh-audit.yml`'s schedule (Q4: Jan 20 → Mar 15; Q1/Q2/Q3: the 20th of month+1 → the
  20th of month+2); between windows the panel keeps showing the last opened one. Each bank's
  expected filing shape (unconsolidated/consolidated) comes from its **prior-period**
  `bank_audit_expected` rows, so a bank that has filed nothing this quarter still appears.
  States, worst → best: **no signal** (nothing anywhere — deliberately *not* "not published";
  unlisted banks may never emit a KAP signal), **results out · audit report pending** (a
  `bank_earnings` KAP `results_filing` row exists for the period but no BRSA PDF is in R2 —
  the bank released results while the audit report is still unpublished or its URL is missing
  from `data/banks/audit_report_urls.json`), **acquired / extraction pending or failed**
  (PDF in R2), **extracted**. The KAP evidence links to the filing. Kind chips mark each of
  unco/cons separately; a failed extraction shows ✕.
- **Coverage matrix** — a **per-statement-type summary table** plus an **errors & missing
  sidebar**, both fed by one `?summary=1` round-trip (`coverageSummary` + `coverageProblems`).
  Each row is a statement type with its cell counts — **ok / manual / error / missing / N/A**
  (present and valid, hand-corrected, present but failing a structural identity check,
  expected-but-absent, or not expected) — and a coverage bar; a `✓` marks a type that has a
  validator. Rows are grouped by the **report section** each table is printed in
  (`registry.section` → §2 financial statements / §5 notes / §4 risk & capital / §1 general
  information / §7 auditor's report), primary statements first.

  > Until 2026-07-17 the groups were **core** vs **"footnotes & §4"**, split on
  > `registry.is_core` — which put OCI, changes-in-equity, cash-flow and off-balance under
  > "footnotes". All four are **§2 primary statements**. `is_core` is a *severity* flag ("an
  > empty lane here means the extraction failed, fail the whole report"), true only for BS
  > assets / BS liabilities / P&L; the other four are `is_core=False` so a single unreadable
  > note-page can't discard a good BS+P&L extraction. Don't read `is_core` as "primary
  > statement" — group on `section`.

  **What the counts do and don't assert.** **error** covers two cases: a structural check
  failed, *or* the validator verified nothing at all (every check skipped). The second used to
  fall through to **ok**, which is how 262 cells read green with nothing checked — see
  `_cell_status` in `scripts/sync_audit_expected.py`. Cells a human has deliberately excused
  (the curated skip lists in `scripts/revalidate_audit_db.py` — a source that genuinely doesn't
  foot, verified against the PDF) also have zero passes but stay **ok**.

  **All 19 registered lanes have a validator.** `free_provision` remains conditional, but is
  no longer unverified: an empty row is **N/A only when no independent evidence contradicts
  it**. A modified audit-opinion basis that names the reserve turns that absence into an
  `error`; existing rows get a value-range check and reconcile their stated comparative to
  the prior year's Q4 current stock. The same matcher feeds the corpus-wide alert check.
  `docs/knowledge/validator-robustness-audit-2026-07-17.md` measures how much each lane's
  green is actually worth.

  Some lanes require more than their own result. `registry.validation_gate()` is the shared
  relationship graph: either balance-sheet side requires `assets`, `liabilities` and `cross`;
  credit quality and derived stages require both `credit_quality` and `stages`. Coverage,
  overwrite protection, targeted-repair rollback and the drawer all consume that same gate.
  For the eight source-captured normalized/summary lanes, the lane's own validation row also
  absorbs the capture checks once a manifest exists. A near-full table with an unfamiliar
  numeric source row therefore becomes an ordinary `error` cell with
  `capture_unmapped_rows` in `failed_detail`; a source table detected while zero normalized
  rows were stored becomes `capture_rows_missed`. Selected-summary detail is retained and
  counted in `bank_audit_capture_manifest` but does not become a false error merely because
  the analytical schema is intentionally narrower. Historical cells acquire this behavior
  as `backfill-audit-source-capture.yml` reaches them.
  The kind control (**unconsolidated / consolidated / both**) re-aggregates the counts; a
  header tally shows total errors + missing for the current mode. Click a row to filter the
  sidebar to that lane. New quarters fold into the counts automatically when acquired (the
  expected universe is the profile census **∪** the R2 PDF list).
- **Errors & missing sidebar** — lists every `error`/`missing` cell (the actionable ones) as
  `bank · period · kind`, errors first, with a status toggle (**error / missing / both**,
  defaulting to errors) and a bank-substring filter. The list is capped at 300 rendered rows
  (the count badge still shows the true total) so the long missing tail (profile, repricing)
  can't bloat the DOM. Click a cell to open the drawer.
- **Cell drawer** — extraction counts/note and every result in the lane's relationship gate
  (including dependent `failed_detail`, not just the lane's own row),
  and a context hint: a PDF-present *missing* cell with **no extraction row** says "acquired, not
  yet extracted — click Re-extract"; one that's been extracted but has an empty statement says
  "likely scanned-image — hand-transcribe." The drawer's **Re-extract** dispatches
  `reextract-statement.yml` for just that `bank` + `period` + `kind` + statement.
- **Pipeline panel** — three audit cards: **Acquire audit PDFs** (`acquire-audit.yml`, no inputs),
  **Extract audit reports** (`refresh-audit.yml`, optional bank), and **Analyst memos**
  (`analyst-daily.yml` — detectors + grounded LLM memos, artifacts-only while the D1 write
  freeze holds; `banks=CALIBRATE` runs the ALBRK+SKBNK feasibility pair).

Data comes from `bank_audit_coverage` / `bank_audit_expected` / `bank_audit_statement_types`,
rebuilt by `scripts/sync_audit_expected.py` (in both the acquire and extract workflows).

Audit **health** remains completeness-based rather than cron-age-based: reports publish
quarterly, so it reads `fresh` when every extracted partition succeeded, else `late`.

## Agents (`/admin/agents`)

The register of every model-driven lane: what question each one answers and for
whom, its workflow stage by stage, and a Run control. Linked from the control
center header; same `requireAdmin()` gate, `noindex`.

**The roster is hand-authored** in `web/app/lib/agents-registry.ts`. One
`AgentDef` per agent carries its audience and question, the `stages` + `edges`
the diagram draws, and the `inputs` that generate *both* the run form and its
server-side validation. Adding an agent is one registry entry — there is no
second place to update.

The diagram colours stages by what they are — **deterministic** (finds and
proves), **model** (investigates and writes), **guard** (decides what survives),
**output** — because where judgment enters is the thing worth seeing at a
glance. Dashed edges are return paths: loop, retry, reject.

### Running one

Press Run. The confirm dialog names the inputs and **what the run persists** —
artifacts, or D1. Dispatch goes to `POST /api/admin/agents/dispatch`, which
validates against the agent's declared inputs (unknown keys rejected, patterns
and option sets enforced, declared defaults filled) before forwarding to GitHub.
Run status is read server-side and refreshes a few seconds after dispatch.

Needs `GITHUB_DISPATCH_TOKEN` (§2) — without it the roster still reads and the
Run controls are disabled with a setup hint.

Two deliberate omissions, both load-bearing:

- **`analyst-daily.yml`'s `push` input is not exposed.** It is a publishing
  decision, not an agent parameter, and it rebuilds three D1 tables wholesale
  (~9,030 billed rows). Dispatch it from Actions when you mean it. A test pins
  this — `agents-registry.test.ts` fails if `push` ever appears in a run form.
- **Worker-resident agents have no Run button.** The Q&A bot answers per
  request; there is nothing to trigger. Exercise it via
  `/api/admin/bot-ask?key=<BOT_TEST_KEY>&q=…`, which returns the reply plus the
  full query trace.

### The gate

`scripts/check_agents_registry.py` (CI, stdlib-only) diffs the registry against
`.github/workflows/`: every `workflowFile` must exist, and every declared input
must be a real `workflow_dispatch` input of that file. Without it a renamed
input surfaces as a GitHub 422 only when someone presses Run — or, worse,
silently stops being sent and the workflow quietly applies its own default.

> Its own first version reported `OK: 3 dispatchable agent(s), 0 declared
> input(s)` — green while parsing nothing, because stage entries carry an `id:`
> too and every agent block ended before its `inputs:` array. The negative tests
> in `tests/test_agents_registry.py` exist so the gate's ability to *fail* stays
> tested.

## Presentation deck (PDF)

The **Presentation** section has two buttons:

- **Generate PDF** — opens `GET /api/presentation?print=1` in a new tab and fires
  the browser print dialog; choose **Save as PDF**.
- **Preview deck** — opens the same deck without auto-printing, to view first.

The route assembles the deck via `web/app/lib/presentation-data.ts` — which
reuses the dashboard's **own** `metrics.ts` functions (the same series the pages
plot) plus the deterministic reads — and renders it with
`web/app/lib/presentation-deck.ts`. The deck is a self-contained 16:9 HTML
document: a dark title slide, a **KPI vitals** slide (stat tiles — assets/loans/
deposits y/y, NPL, CAR, NIM, ROE, LDR), one slide per tab (headline + driver
bullets + an **inline-SVG trend chart**), and a methodology slide. Because every
figure and chart comes straight from the site's metric functions, the deck can't
drift; nothing to configure. The Worker can't run headless Chrome, so the
browser's print-to-PDF is the render step (the CLI `scripts/generate_presentation.py`
just fetches this same HTML and prints it headlessly for an unattended PDF). Query
params: `?tabs=a,b,c` (subset/reorder), `?title=…`, `?print=1`. Not admin-gated —
it returns already-public copy, same as `/api/reads`.

## Purge cache (making a refresh show up immediately)

The **Purge cache** button in the Data-health section header clears the dashboard's
KV cache so a just-refreshed source appears in the graphs right away.

Why it's needed: D1 reads are cached ~1h in KV (`cachedAll` → `unstable_cache`,
`DATA_REVALIDATE_SECONDS` in `web/app/lib/db.ts`) to keep repeat page views off D1.
So when a manual refresh lands a new bulletin / EVDS / weekly row in D1, the charts
keep serving the pre-refresh render until that window rolls over. The data isn't
missing — only the cached page is stale.

The button drops the cached entries (`POST /api/admin/purge-cache`); pages then
re-read D1 lazily on the next view. The endpoint deletes the `NEXT_INC_CACHE_KV`
namespace in batched, cursor-paginated rounds (the client loops until done) — that
namespace also accumulates orphaned entries from past deploys (OpenNext keys by
build id and never GCs old builds), so a purge can clear thousands of keys and
also cleans that cruft. No tag cache is configured, so `revalidateTag` is a no-op
here; deleting the KV entries directly is the lever. Safe — it only clears a cache,
and the Workers Paid plan has no KV write-cap concern on repopulation. A `web/**`
deploy also busts the cache (new build id → new keys) but needs a code push.

## Setup

### 1. Set the admin password (unlocks the page)

This is all that's needed to open `/admin` on the current `workers.dev` URL.

Cloudflare dashboard → **Workers & Pages → `carthago` →
Settings → Variables and Secrets → Add** → name `ADMIN_PASSWORD`, type **Secret**,
value = a password you choose → **Save**. (Or CLI: `cd web; npx wrangler secret
put ADMIN_PASSWORD`.)

Then visit `/admin`, enter the password, and you're in. The session lasts ~12h;
"Sign out" clears it.

### 2. GitHub token (enables run status + trigger buttons)

Fine-grained PAT scoped to `incesalim/turkish-banking-sector`, **Actions: Read
and write** → add as a secret named `GITHUB_DISPATCH_TOKEN` (same Variables and
Secrets screen, or `npx wrangler secret put GITHUB_DISPATCH_TOKEN`).

### 3. Cloudflare Web Analytics (optional — traffic panel)

Enable Web Analytics for the site, create an account API token with **Analytics:
Read**, then set:
- vars `CF_ANALYTICS_SITE_TAG`, `CF_ANALYTICS_SITE_TOKEN`, `CF_ACCOUNT_TAG`
  (in `web/wrangler.jsonc`)
- secret `CF_ANALYTICS_TOKEN`

> Cloudflare returns two different identifiers for one Web Analytics site:
> `site_tag` is the GraphQL filter (`CF_ANALYTICS_SITE_TAG`), while `site_token` is
> the public client-beacon token (`CF_ANALYTICS_SITE_TOKEN`). They are not
> interchangeable: using the token as `siteTag` produces a successful but empty
> GraphQL result. List both with `GET /accounts/{account_id}/rum/site_info/list`.
> Do not turn on Cloudflare's "automatic" edge injection expecting it to cover the
> OpenNext Worker response; the beacon is rendered explicitly in
> `web/app/components/Beacon.tsx`.

### 4. Cloudflare Access (optional — only on a custom domain)

On `workers.dev`, Cloudflare Access can only gate the **whole** subdomain, which
would lock the public dashboard too — so we use the password instead. If you
later put the dashboard on a **custom domain**, you can switch to Access:
create a self-hosted Access app over `/admin` + `/api/admin`, allow your email,
then set vars `CF_ACCESS_TEAM_DOMAIN` + `CF_ACCESS_AUD`. When both are present
the panel uses Access automatically (and ignores the password).

Local dev: set `ADMIN_DEV_BYPASS=1` (e.g. in `web/.dev.vars`) to skip auth.

## Per-bank audit trigger

The **Audit reports** card has a bank dropdown. Leave it on **All banks** for
the normal full sweep (every bank, every quarter — idempotent), or pick a single
ticker to scrape + extract just that bank's **latest published quarter** — handy
outside a filing window or when you do not want to wait for the next daily check.

It forwards a `bank` input to `refresh-audit.yml`. Because a per-bank trigger
means "grab the quarter this bank just published", the workflow also adds
`--latest-period`, so it runs `sync_audit_reports.py --only-bank TICKER
--latest-period` (newest quarter only, not the bank's full history). The ticker
list mirrors `data/banks/audit_report_urls.json` (`AUDIT_BANKS` in
`web/app/lib/github.ts`) and is validated server-side in the dispatch route, so
only a known ticker can ever reach the workflow.

### Auto-discovery

Some banks **auto-discover** new quarters straight from their IR page, so you
just trigger and the newest report is found, scraped, and ingested with no
hand-edit. Currently 13 banks: **ALBRK, ANADOLU, EMLAK, EXIM, FIBA, HALKB, ING,
PASHA, TEB, TFKB, TSKB, VAKIFK, ZIRAAT** (`DISCOVERY_BANKS` in
`src/audit_reports/discovery.py`).

The engine (`discovery.py`) is generic and config-anchored: for each bank it
learns the URL's quarter-end date encoding and a filename "skeleton" from that
bank's existing config entries, then matches new links on the page — which picks
the right document (full report vs tables-only / TR vs EN) and assigns the
consolidated/unconsolidated kind. It's fail-safe: any error falls back to the
static config.

The other banks still need a hand-added URL in `audit_report_urls.json` before
triggering: some are JavaScript-rendered (AKBNK, GARAN, YKBNK, ISCTR, VAKBN,
ICBCT, ALNTF), some serve opaque file-id URLs with no date (HSBC, KLNMA, ODEA,
QNBFB), and a few don't validate cleanly yet (AKTIF, BURGAN, KUVEYT, SKBNK).

**Adding / re-checking a bank:** run `python scripts/diagnostics/validate_discovery.py`
(uses the config as a test oracle — a bank passes when it reproduces its latest
period with no recent-period URL mismatch), then add the passing tickers to
`DISCOVERY_BANKS`. Re-run it if a bank redesigns its IR page.

> Note: to re-process an *older* period for one bank, run the script directly
> with `--only-bank TICKER` (no `--latest-period`).

## How health status is derived

Each source reports its latest data period, last ingest timestamp, and a row
count. The colour (Fresh / Late / Stale) compares time-since-last-ingest against
the source's expected cron cadence (daily for EVDS/news, weekly for
bulletins/audit/regulation): `≤1.5×` cadence = Fresh, `≤3×` = Late, else Stale.

Audit extraction success/failure and per-bank structural-validation detail are
**not** separate panels — they're surfaced cell-by-cell in the **coverage
matrix** (extraction status, failing identity checks per `bank × period × kind`,
with the drill-down drawer). The per-row identities checked are TL+FC=Total,
parent = Σ children, TOTAL = Σ roman sections, assets = liabilities+equity; the
same `bank_audit_validation` data drives the ⚠ markers on `/banks/[ticker]`
period columns.
