# Architecture & live-page review — 2026-07-02

A dated snapshot: the live dashboard and the end-to-end architecture (web/ +
Python pipeline) checked after the Editorial theme ship (#88, a645b8c).

> **Scope: report only. No code was changed.** These are verified findings and
> a ranked backlog to decide on, not edits made. The two "urgent" items below
> are open defects until someone takes them.

## Method (read-only, repeatable)

1. **Live site** — HTTP status of 10 key routes on
   `turkish-banking-dashboard.incesalim10.workers.dev` (`/`, `/sector`,
   `/cross-bank`, `/economy`, `/banks/GARAN`, `/admin`, `/pipeline`,
   `/market-risk`, `/non-bank`, `/valuation`).
2. **CI / deploys** — last ~12 GitHub Actions runs (`gh run list`), last 3
   deploys, open PRs.
3. **Web survey** — structure/patterns/theming/caching/tests across
   `web/app` (~28.2k LOC: 34 pages, 8 API routes, 55 lib modules, 101 tsx).
4. **Pipeline survey** — module map, extraction subsystem, scraper
   consistency, `push_to_d1.py`, test shape, workflow hygiene across `src/` +
   `scripts/` + `.github/workflows/` (~32k LOC Python).

**Headline:** all routes 200, crons green, and the architecture is
**fundamentally sound** — clean 3-layer web app (server pages → lib data
layer → design-system components; zero client pages), disciplined two-lane
pipeline with validators and a coverage spine. The debt is concentrated, not
diffuse: one live theming regression, one silent-CI gap, one brittle sync
chokepoint, and a short list of consistency cleanups.

---

## Urgent (open defects)

### 1. P&L Sankey paints its dark palette in light mode — live regression

`web/app/banks/[ticker]/PlSankeyChart.tsx:209` infers dark mode with

```ts
const resolvedDark = t.tooltipBg !== "#ffffff";
```

The Editorial theme changed the light `tooltipBg` from `#ffffff` to `#FBFAF7`
(`web/app/lib/chart-theme.ts:36`), so the sniff is now **always true** → the
Sankey's node/ribbon fills (`nodeFill(n, resolvedDark)`) use the dark map even
on the light theme, on every `/banks/[ticker]` page.

**Fix when taken (one line):** `const resolvedDark = t.mode === "dark";` —
`ChartTheme` already exposes `mode`, and `NimComponentsChart.tsx` /
`BopFlowChart.tsx` already use that idiom correctly.

### 2. Dependabot PR #90 red — lockfile out of sync

`npm ci` fails with `EUSAGE` (package.json / package-lock.json mismatch) on
the grouped web-deps bump (recharts 3.9.0→3.9.1, tailwindcss +
@tailwindcss/postcss 4.3.1→4.3.2, wrangler). **No eslint in the group**, so
the ESLint-10 drop rule doesn't apply — mergeable once the lockfile is
regenerated (`@dependabot rebase` comment, or `npm install` on the branch).

---

## Web backlog (ranked)

1. **Off-theme chart palettes (pre-Editorial blues), 4 files.** Hardcoded hex
   maps never migrated to `chart-theme.ts` / `--chart-*`:
   `banks/[ticker]/PlSankeyChart.tsx` (`FILLS_BY_ID`/`FILLS_BY_KIND`, 24 hexes),
   `economy/economic-growth/page.tsx` (`MAROON`/`AMBER`/`ORANGE`/`NAVY`/`INK`
   consts fed into `BopFlowChart`), `components/BopFlowChart.tsx`
   (`FALLBACK_FILLS`), `profitability/NimComponentsChart.tsx` (`FILLS`). They
   render off-theme against the Editorial navy/terracotta system.
2. **`app/lib/audit.ts` is the main D1-cost hotspot.** ~13 raw
   `getDB().prepare()` reads (only `bankSummaries()` is cached) fire
   per-request on **public** pages — `/banks/[ticker]` (via `bankPeriods`,
   `balanceSheet`, `profitLoss`, …), `/banks`, `/liquidity`, `/capital`,
   `/ownership`. `cachedAll` keys by SQL+binds, so the parametric queries can
   be cached as-is. (Post-refresh staleness is already handled by the KV-purge
   recipe; the account is on Workers Paid so the old KV write-cap concern is
   gone.)
3. **`app/sector/page.tsx` inline SQL.** The only page that talks to D1
   directly (`fetchSectorTotalAssets()` in the page), bypassing lib + cache —
   move into a lib module.
4. **`app/lib/metrics.ts` god-module** — 1,222 LOC, 27 `cachedAll` queries,
   imported by most sector pages. Split by sub-domain when convenient.
5. **Data-layer tests are zero.** The 5 vitest files cover only pure utils
   (`pl-sankey`, `valuation`, `chart-csv`, `chart-range`, `period-math`); the
   SQL-shaping modules (`metrics`, `audit`, `heatmap`, `growth`, `bop`,
   `economy`, `market-risk`, `funds`, `non-bank`, `digital`) have none —
   exactly the code that regresses silently.
6. **Consistency nits:** three dark-mode idioms coexist (`t.mode` — correct;
   the `tooltipBg` sniff — buggy; raw `resolvedTheme` in
   `PipelineFlow`/`theme-toggle`/`toaster`); ~20 local `new Intl.NumberFormat`
   across 11 pages despite the `chart-format.ts` convention in `web/CLAUDE.md`.

What's healthy and worth keeping as-is: page shape is uniform (async server
page → `Promise.all` lib fan-out → `PageHeader`/`Section`/`ChartCard`);
`'use client'` (47 files) is *not* overused — every one is genuinely
interactive; the ui barrel (`components/ui/index.ts`) and Editorial tokens in
`globals.css` (+ the deliberate `chart-theme.ts` JS mirror for SVG) are clean.

---

## Pipeline backlog (ranked)

1. **CI never runs the audit-extraction tests.** `ci.yml` installs only
   `ruff pytest lxml requests`, so every `pytest.importorskip("fitz")` /
   `importorskip("pdfplumber")` test — most of the largest subsystem's suite —
   is **silently skipped on PRs** (they "pass" by skipping). Highest-leverage
   fix: a second CI job (or extended install) with `pymupdf`+`pdfplumber` that
   actually exercises the suite.
2. **`scripts/push_to_d1.py` is the brittle chokepoint.** Registering a new
   table needs 3 disconnected hand-edits (the 44-entry `SYNC_TABLES` list, the
   ~40-line timestamp-column if/elif ladder in `fetch_recent`, the hard-coded
   `init_schema` block) — and an unmatched table falls into the `else` and
   **silently never syncs**. A declarative per-table registry (name, timestamp
   column, rebuild-vs-incremental, batch size, schema-init) collapses all
   three and kills the silent-skip mode; add a test asserting every table is
   registered.
3. **~9 copy-pasted HTTP session+retry loops** across
   `src/scrapers/{bist_client,bddk_api_scraper,weekly_api_scraper}`,
   `src/tbb/{client,acquisition}`, `src/tefas/client`, `src/news/sources/*`,
   `src/tuik/client`, `src/kap/client`, `src/faaliyet/client` — each with its
   own headers/timeout/backoff. One shared `get_with_retry()` + session
   factory in `src/scrapers/_http.py` (which already exists for the BDDK TLS
   fix and is properly reused) is the natural home.
4. **Dead code in `src/audit_reports/extractor.py`** (zero callers, verified
   by grep across src/scripts/tests): `_safe_repaired_text` (~l.100),
   `_page_text` (~l.1121, the `(pdf, idx)` variant), `_n_pages` (~l.52). Safe
   deletes; already flagged in the engine-strategy notes.
5. **pdfplumber remaining outside the frozen BS/P&L path:**
   `src/audit_reports/profiler.py:114` (`_build_profile`) and all of
   `src/faaliyet/extractor.py`. Finishing these completes the fitz-only rule.
6. **Domain logic living in `scripts/`:** `check_audit_quality.py` (561 lines
   of quality rules), `compute_bank_metrics.py`, `metric_knowledge.py`,
   `apply_overrides.py` behave like library code (two have dedicated tests) —
   belong in `src/`. Also duplicate discovery:
   `scripts/discover_audit_urls.py` (454) vs `src/audit_reports/discovery.py` (240).
7. **Untested ingest front door:** `src/scrapers/` (BDDK monthly/weekly, EVDS,
   BIST) has zero test imports; `push_to_d1.py` itself has no test.
8. **Minor:** near-identical `backfill-*`/`refresh-*` workflow scaffolds could
   share a composite action; stray `.next/` dir at repo root.

Workflow hygiene is otherwise good: Python 3.12 + checkout@v6/setup-python@v6
uniform across all 16 workflows, and the `check_pipeline_graph_sync.py` gate
keeps `/pipeline` topology honest.
