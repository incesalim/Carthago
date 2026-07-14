# Architecture & docs check — 2026-07-14

Read-only audit of `docs/ARCHITECTURE.md`, `docs/PROJECT_STATE.md`,
`docs/OPERATIONS.md`, the root `README.md`, and the prior
[architecture-review-2026-07.md](architecture-review-2026-07.md) (2026-07-02),
each **verified against the code** rather than against each other.

> **Status: ACTED ON 2026-07-14** — findings §1–§4 fixed in commits `bf00951`,
> `0772f40`, `dd02000`, `da24ef4` and the docs pass that follows. The report below
> is preserved **as written**, so the diagnosis can be judged against what was
> actually found. Read it with the correction and the leftovers noted here:
>
> - **§1.1 understated the damage.** The market-risk gap was not merely a future
>   risk — D1 was **already** stranded at the 2026-06-29 backfill: 17 banks held
>   half-size fx partitions (4 rows where the snapshot has 8) and AKBNK's 2026Q1
>   `fx_position` was missing from D1 entirely. **One follow-up remains open: D1
>   still needs a reconciliation push** of `bank_audit_fx_position` /
>   `_repricing` from the R2 snapshot (or a `reextract-statement.yml` run for the
>   two statements) to recover the quarters it missed. The code can no longer
>   *create* the gap; it has not yet *closed* the existing one.
> - **§2.5 had the counts backwards.** D1 proves 1,050 extractions / 1,050
>   core-success / 38 banks — so PROJECT_STATE's "1,050" was right and the "974"
>   mentions were the stale ones, not the reverse. Corrected in the docs.
> - **§1.2 undercounted the dead links: there were two, not one.** `/weekly`
>   (route retired in `fd0400b`) 404'd alongside `/franchise`.
> - **Still open** (all pre-existing, none new): the `push_to_d1` declarative
>   registry (§5 item 8), and the §3 backlog inherited from the 07-02 review —
>   dead code in `extractor.py`, pdfplumber in `profiler.py` + `faaliyet`,
>   uncached `audit.ts` reads, `metrics.ts` at 1,263 LOC, the ~10 duplicated HTTP
>   retry loops, and zero tests on the SQL-shaping lib modules.

**Headline:** the architecture is sound and the repo's own gates are green — but
they are green because they guard the wrong file. `check_docs_sync.py` enforces
only `OPERATIONS.md`; `ARCHITECTURE.md` and `PROJECT_STATE.md` are ungated, and
that is precisely where the drift has collected. Two findings are **live defects**,
not documentation: the per-quarter audit lane never pushes market-risk to D1, and
`/pipeline` links to a route that 404s.

---

## 1. Live defects

### 1.1 The routine audit lane extracts market-risk and then drops it — `/market-risk` cannot see a new quarter

`refresh-audit.yml` is the lane that ingests **every new quarter** (dispatched from
the /admin coverage matrix). It extracts `fx_position` + `repricing` — the
extractor runs both lanes (`src/audit_reports/extractor.py:1322-1334`), the loader
persists both (`src/audit_reports/loader.py:129-130`), and both are registered in
`push_to_d1.SYNC_TABLES` (`scripts/push_to_d1.py:76-77`).

But the workflow's hand-written push list omits them:

```yaml
# .github/workflows/refresh-audit.yml:172  — 14 tables, no fx_position, no repricing
--only-tables bank_audit_balance_sheet,bank_audit_profit_loss,bank_audit_oci,
  bank_audit_cash_flow,bank_audit_equity_change,bank_audit_credit_quality,
  bank_audit_profile,bank_audit_loans_by_sector,bank_audit_npl_movement,
  bank_audit_stages,bank_audit_capital,bank_audit_liquidity,
  bank_audit_extractions,bank_audit_validation
```

So the rows are extracted, written to `data/bank_audit.db`, VACUUMed into
`state/bank_audit.db.gz` — **and never pushed to D1**. They exist in the snapshot
and nowhere the dashboard can read them.

This is currently **masked**: `bank_audit_fx_position` / `_repricing` were last
populated by a *manual* `backfill-audit.yml` run on 2026-06-29 (PROJECT_STATE.md:42-43),
and `backfill_extraction.py` pushes the canonical 16-table `AUDIT_TABLES`
(`scripts/audit_d1.py:39-46`), which does include them. The gap only bites on the
**next quarter**: extract 2026Q2 from /admin and `/market-risk` silently stays at
2026Q1 while every other audit page moves.

**Root cause — the audit table list exists in four divergent copies:**

| Where | Count | Omits |
|---|---|---|
| `scripts/audit_d1.py:39-46` — canonical, used by `backfill_extraction.py` + `apply_overrides.py` | 16 | — |
| `.github/workflows/refresh-audit.yml:172` | 14 | `fx_position`, `repricing` |
| `docs/OPERATIONS.md:90` (manual-push recipe) | 12 | + `cash_flow`, `equity_change` |
| `scripts/seed_audit_db.py:33-42` | 8 | + `capital`, `liquidity`, `oci`, `validation` |

`seed_audit_db.py:31-32` carries the comment *"The full `bank_audit_*` surface —
must match `src/audit_reports/schema.py` DDL and the audit subset of
`push_to_d1.py` SYNC_TABLES"* — an assertion that is **false as written**, which is
how the drift went unnoticed.

**Fix:** import `AUDIT_TABLES` from `scripts/audit_d1.py` at all three other call
sites (workflow via a `python -c` or a small `--audit-tables` flag on
`push_to_d1.py`), so there is one list. Anything less re-creates the same bug the
next time a statement lane is added.

### 1.2 `/pipeline` renders a clickable node to `/franchise`, which 404s

`web/app/lib/pipeline-graph.ts:139` still declares the page node

```ts
{ id: "page-franchise", … sublabel: "/franchise · branch/ATM/customer footprint", href: "/franchise" }
```

plus its edge at `:266`. `/franchise` was parked on 2026-07-12 — the code sits at
`web/app/_franchise/page.tsx` and the `_` prefix means **Next does not route it**.
`Nav.tsx` and `sitemap.ts` were both correctly updated; the pipeline graph was not.
Clicking the Franchise node on `/pipeline` is a 404 today.

(`check_pipeline_graph_sync.py` passes — it validates workflow coverage, not that a
page node's `href` resolves.)

---

## 2. Documentation drift (ranked by how misleading)

1. **`/franchise` is documented as a shipped tab, with the wrong reason for being
   empty.** `PROJECT_STATE.md:388-395` describes it in the present tense among the
   live tabs; `:32` explains the empty table as *"Lane shipped; coverage pending
   per-bank URL curation … + the `backfill-faaliyet` run."* The real reason is in
   the code's own header (`web/app/_franchise/page.tsx:2-15`): the **extractor is
   not fit to publish** — ~75% of non-ATM values are wrong and the confidence flags
   don't correlate with correctness. The doc's implied fix (curate the URLs, run the
   backfill) would **publish known-bad numbers**. Nowhere does PROJECT_STATE say the
   route is parked. Contrast `/valuation`, which is documented correctly as archived
   (`:612-615`) — the pattern was known and simply not applied twice.
2. **`ARCHITECTURE.md` omits 8 of 18 workflows — including 4 scheduled lanes.**
   `refresh-advertised-rates` (Mon 06:00), `refresh-presentations-weekly` (Sat 06:00),
   `summarize-regulations` (Sun 06:00), `generate-reads` (Sun 07:30), and all four
   `backfill-*`. A reader concludes nothing writes `bank_advertised_rates`,
   `bank_earnings`, `regulation_briefings` or `read_headlines` on a schedule.
   *Every cron that **is** documented matches the yml — no schedule is wrong, they're
   just absent.*
3. **The pdfplumber rule is stated more strongly than the code holds.**
   `ARCHITECTURE.md:52` — "fitz only for every lane except the frozen BS/P&L
   extractor". In fact `src/faaliyet/extractor.py:32,420` is a **live production lane
   that is 100% pdfplumber, no fitz at all**, and `src/audit_reports/profiler.py:24,114`
   still opens it too. The audit *statement* lanes really are fitz-only, so the rule
   holds where it matters — but as written the sentence is false, and it is the
   sentence a future extractor author will rely on. (It also cites "~60× slower";
   the code says 85×, 50× and 17× in different places.)
4. **`src/rates/` is missing from the Components table** (`ARCHITECTURE.md:39-61`) —
   11 of 12 subpackages listed, though `refresh-advertised-rates.yml` runs
   `python -m src.rates.scraper` weekly. The BIST lane inside `src/scrapers/`
   (`bist_client.py`) is likewise unaccounted for.
5. **PROJECT_STATE contradicts itself on fleet size.** `:49-50` claims **1,050 PDFs,
   100% core-success**, while `:45` says `bank_audit_extractions` = **974 rows
   (954 ok / 20 partial)**, `:99` says "~975 partitions", and `:1065` repeats 974.
   Bank count likewise: `:49` declares a **38-bank** universe while `:76` ("20 of 31
   banks") and `:92` ("31/31 banks") still describe **31**. `ARCHITECTURE.md:56` adds
   a third number: "~970 quarterly PDFs".
6. **`OPERATIONS.md:90`'s manual audit-push recipe silently drops two tables** —
   `bank_audit_cash_flow` and `bank_audit_equity_change` (see §1.1). Follow the doc
   and two statement tables never reach D1.
7. **Root `README.md:107-110` prints the route tree without the `_` prefix** —
   `valuation/` and `franchise/` are listed as ordinary live routes. The underscore
   is load-bearing: it is exactly what un-routes them. Same file, `:36`, still says
   "32 banks × up to 17 quarters" against the 38-bank universe.
8. **`CHANGELOG.md` never records the franchise unpublish.** Newest entry is
   2026-07-10 (`:8`); the unpublish is 2026-07-12. Meanwhile `:254-264` still reads as
   a launch announcement for the tab.
9. **`/disclosures` is an undocumented live route.** It exists, is in `Nav.tsx:40`
   and `sitemap.ts:50`, and is fed by `news_items` — yet PROJECT_STATE's
   qualitative-data section (`:652`) enumerates only `/regulation`, `/news`,
   `/news/google`, and the route inventory never introduces it.
10. **`PROJECT_STATE.md:13` says "Last verified: 2026-07-08"** while the body carries
    content dated 2026-07-13.

**Verified clean** (checked, no drift — don't re-litigate): every documented cron
schedule; `OPERATIONS.md`'s script references; the 13 auto-discovery banks
(`OPERATIONS.md:101-103` == `discovery.py:47-50`); the `/sector` → `/` and
`/sector/ratios` → `/#by-type` redirect claims; the `/valuation` archived-status
docs; migrations-to-0024.

### The duplicate `0007` migration is safe — and must be left alone

`0007_kap_ownership_subsidiaries.sql` and `0007_tefas_funds.sql` share a number.
Verified against wrangler's source (`web/node_modules/wrangler/wrangler-dist/cli.js:232779-232872`):
`d1_migrations` keys applied-state on the **full filename** (UNIQUE on `name`), and
ordering falls through from the leading number to a lexicographic filename compare —
so both apply, both are recorded, deterministically, on every platform. `migrations
create` next-numbers to 0025 correctly.

**The trap is the cleanup, not the duplicate.** Renaming `0007_tefas_funds.sql` →
`0025_…` hands wrangler a filename it has never seen and it **re-runs that migration
against a database that already has those tables**. Leave it, or rename only with a
manual `d1_migrations` row update. (`check_schema_naming.py` is scoped to ≥ 0022, so
it will never flag this.)

---

## 3. Status of the 2026-07-02 review

Re-verified all 10 items: **2 fixed, 8 still open, and one of its findings was
already false when written.**

- ✅ **FIXED** — the Sankey light-mode palette bug. `PlSankeyChart.tsx` no longer
  exists (deleted in `896d4f5`); the flow chart is now `IncomeShape.tsx`, and
  `ChartTheme` exposes an explicit `mode` (`chart-theme.ts:19`) which every chart uses.
- ✅ **FIXED** — stray `.next/` at repo root.
- ❌ **FALSE WHEN WRITTEN** — "`app/sector/page.tsx` inline SQL". That file is a
  13-line `redirect("/")` stub and `fetchSectorTotalAssets` exists nowhere in the
  tree. `/sector` was retired the same day the review was written.
- 🔴 **STILL OPEN** — CI never runs the audit-extraction tests (`ci.yml:27` installs
  only `ruff pytest lxml requests`; **13 of 35 test files** `importorskip("fitz")`/
  `("pdfplumber")` and pass by skipping — the largest subsystem's suite is silently
  unexercised on every PR). **This is the highest-leverage open item.**
- 🔴 **STILL OPEN (worse)** — `push_to_d1.py` chokepoint: `SYNC_TABLES` now 47 tables
  (was 44), the timestamp if/elif ladder still ends in a silent-skip
  `else` (`:177`), still no test asserting every table is registered. §1.1 is this
  bug's first real casualty.
- 🔴 **STILL OPEN** — dead code in `extractor.py` (`_n_pages:52`,
  `_safe_repaired_text:100`, `_page_text:1145` — zero call sites); pdfplumber in
  `profiler.py` + `faaliyet/extractor.py`; `audit.ts` 13 raw uncached `.prepare()`
  reads vs 2 `cachedAll` on public pages; `metrics.ts` grown to 1,263 LOC; ~10
  copy-pasted HTTP retry loops with no shared `get_with_retry` in `_http.py`;
  zero tests on the SQL-shaping lib modules (17 vitest files, none covering
  `metrics`/`audit`/`heatmap`/`growth`/`bop`/`economy`/`market-risk`/`funds`/
  `non-bank`/`digital`).

---

## 4. Why the gates missed all of this

All three consistency gates pass (`check_docs_sync` 18 workflows / 12 secrets / 17
env keys; `check_pipeline_graph_sync` 18 workflows; `check_schema_naming` 25
migrations). They are healthy — and they are **scoped to the wrong surface**:

- `check_docs_sync.py:11-13` asserts every workflow is named in **`OPERATIONS.md`
  only**. `ARCHITECTURE.md` and `PROJECT_STATE.md` are unguarded — which is exactly
  where findings 2.1–2.5 live. OPERATIONS.md is, as designed, clean.
- `check_pipeline_graph_sync.py` validates workflow coverage in the graph, not that
  a page node's `href` resolves to a routed page (§1.2).
- No gate compares the four copies of the audit table list (§1.1).

## 5. Ranked fixes

| # | Fix | Size |
|---|---|---|
| 1 | Single-source `AUDIT_TABLES`; add `fx_position`/`repricing` to `refresh-audit.yml:172` | one import + 2 names — **prevents silent loss of the next quarter's market-risk data** |
| 2 | Drop the `page-franchise` node + edge from `pipeline-graph.ts` (or restore the route) | 2 lines — kills a live 404 |
| 3 | Extend `check_docs_sync.py` to guard ARCHITECTURE.md + PROJECT_STATE.md; add a gate asserting page-node `href`s resolve | small — stops the whole class |
| 4 | CI: install `pymupdf`+`pdfplumber` (or a second job) so 13 test files stop passing-by-skipping | small — highest test-integrity leverage |
| 5 | PROJECT_STATE: mark `/franchise` parked + state the real reason; reconcile 974/1,050 and 31/38; bump "Last verified" | doc |
| 6 | ARCHITECTURE: add the 8 missing workflows, `src/rates/`, and soften the pdfplumber claim to name `faaliyet` | doc |
| 7 | OPERATIONS:90 recipe → canonical table list; README route tree → `_valuation/`, `_franchise/`; CHANGELOG → record the unpublish | doc |
| 8 | `push_to_d1.py` declarative table registry + "every table registered" test | medium — retires the chokepoint |

Related: [architecture-review-2026-07.md](architecture-review-2026-07.md),
[strategic-review-2026-07.md](strategic-review-2026-07.md),
[2026-07-13-sector-pages-consistency-audit.md](2026-07-13-sector-pages-consistency-audit.md).
</content>
</invoke>
