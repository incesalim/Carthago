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

Regulator-sourced origin observations retain the original search result and
exact bank/period/basis row. The source comparison labels these links explicitly
and offers the retained listing as a checked download. Earlier bank-site
observations stay in the origin history, and acquisitions are unchanged.

## Broader extraction scope (2026-09-08)

Equity and capital are examples; the repair scope includes all 19 registered
extractors plus structured prose and unserved report tables. See the all-lane map
in [AUDIT_DOCUMENT_PLAN.md](AUDIT_DOCUMENT_PLAN.md#all-lane-repair-map-2026-09-08).
Credit-quality coverage refers to closing balances; liquidity, FX and repricing
refer to selected ratios or summary rows. A passing cell does not certify a
complete source table. The deployed liquidity increment preserves LCR current/prior
headings and literal/page evidence. Its two verified filings are TOMK 2024Q1 solo
and GARAN 2022Q4 consolidated; complete liquidity tables remain outside this lane.
Production D1 readback is verified; authenticated visual confirmation is pending
because the admin browser session expired on reload.

## Code map

The existing audit coverage matrix measures predefined analytical lanes. A green
cell does not certify that every table or passage in the filing was captured.
The matrix now states explicitly that summary lanes cover selected disclosures;
the capital registry label also says “selected figures”. The equity parser can
retain a complete source row that fails arithmetic, which remains a validation
problem rather than disappearing from the statement. Capital-buffer percentages
have field-level literal/page evidence in `buffer_source_json`. Migration 0048
and the TOMK 2023Q3 solo pilot are live (2026-09-07); the five buffer disclosures
were checked in both period columns against the original PDF. Other historical
capital disclosures have not been populated or certified by this pilot.
The separate complete-document corpus is under active implementation in
[AUDIT_DOCUMENT_PLAN.md](AUDIT_DOCUMENT_PLAN.md). Its source preservation and
candidate structure run through `build-document-corpus.yml`. The **Complete audit
documents** panel reads its private R2 catalog, with separate registered,
acquired, source-preserved, structured, failed, stale and fully-verified counts.
Choose a bank, filing and PDF page to inspect table candidates, paragraph and
heading candidates, every source text block, review flags, the original PDF and
source-evidence JSON. Narrative candidates retain source span references and
tentative page-scoped heading paths; document section context is kept separately.
Text inside detected tables is labelled explicitly.
The prose reading view can arrange text by its source position, connect uniquely
aligned list markers and preserve column groups. Areas without a unique order
are flagged. The stored-order view remains available; missing, duplicate or
unknown layout references automatically fall back to every original text element.
Heading context and paragraph boundaries still require source review.

**Report sections and printed contents** shows source body-banner links alongside
the complete printed contents entries. A printed folio is linked only when a
unique footer occurrence is found; missing or repeated folios remain unresolved
or ambiguous. Wrapped titles and declared page ranges stay literal. Matching
body titles and repeated section-index titles are identified separately. When
contents references disagree with body locations, both remain visible with
links to their source pages. The section headings printed in the contents are
also available separately, preserving wording that differs from body headings
even when body boundaries remain unresolved. These are navigation candidates, not approval of
the report's meaning. Earlier captures without this view remain readable.

Alternative table interpretations remain available for review without cutting
the source paragraphs beneath their inferred header rectangles. Roman headings
aligned on a page remain sibling candidates even when their font sizes differ.

Content review notes retain open questions about figures printed in the report.
Each passage links to the original page; PDF/native revision, exact page bytes,
span occurrences, wording and bounding boxes are checked before display.
These checks validate source references, not the reviewer's interpretation or
a choice of corrected value. The private `artifact=reviews` response includes
the full references for analyst use. No notes means no registered review, not
no source discrepancies.

Tall ruled body cells can expose a separate source-line view with the original
column positions and merged headers. Use the checkbox to return to physical
cells. Blank positions mean no text on that line; no zero is inferred. Wrapped
labels remain separate lines and accounting-row associations require review.
When a label cell spans several physical rows, the line view keeps the group
together in its original columns and displays its closing balance once. Turning
the checkbox off restores the original cell spans.
When one PDF word crosses a ruled cell border, character ranges retain the exact
pieces belonging to each cell. Hover over the cell to inspect those references.
**Boundary review** lists the original words and the affected rows and columns.
It remains visible even when every character has a source reference: a row
number touching a label and a clipped alphabetic word require different review.
The source-line view carries these same fragments without restoring the whole
word into both cells. Earlier captures keep their original word references.
**Printed period headings** separately shows explicitly printed period labels
at their original column positions, including a header whose missing dividers
put both dates into one physical cell. Original cells remain visible below and
source-word references are retained. Competing heading bands require review;
this view does not fill missing dates from a neighbouring page. Empty printed
cells and positions with no physical cell have distinct labels, alongside
literal dashes and disclosed zero.
**Source-reviewed tables** shows registered complete-table transcriptions above
the candidate views. The API rechecks the current PDF identity, exact native
and structured page hashes, literal grid, merged/absent slots, context text and
each explicit logical-row assignment. A reviewed table may split one large
physical cell band into its printed rows; every source character must be retained
exactly once, and split rows keep their original physical-row reference. A complete
reviewed grid can also separate combined period columns and assign wrapped or
displaced source lines to explicitly checked rows. It retains all original grid
boundaries and source-word coordinates; the displayed column count describes
this reviewed view. The original physical table remains in the download. Numbered
row groups are also checked against the independent literal transcription.
Reviewed source anomalies may retain otherwise empty rows with unassigned marks.
The source-review explanation is displayed with each named table; these marks
are not silently assigned to an adjacent financial row.
It exposes only named reviewed tables;
the whole-report verification count remains separate. Hover a cell to inspect
source-word/character references. **Download reviewed tables and source
references** returns this page's logical rows alongside its original physical
tables. Blank cells, absent cells, dashes and zero remain distinct. A changed
source or capture fails review loading instead of borrowing an older review.
Some partially ruled tables also offer a **Printed rules and text positions**
alternative with complete grouped headings and literal period columns. It keeps
blank cells separate from covered merged-header slots; all earlier candidates
remain available for comparison. This reconstruction still requires source review.
Where printed column numbers match a complete adjacent note sequence, **Numbered
source explanations** shows each full paragraph and its column reference beneath
the table. These are suggested source relationships; ambiguous matches remain
unlinked, and the original markers and paragraphs stay in the text view.
The complete physical text remains accessible underneath. Table counts
are detector candidates, potentially overlapping; they are never a completeness
denominator. Reading order, headers and narrative roles remain unreviewed.

The added TOMK 2023Q3 equity review displays 20 rows and 17 columns, with six
numbered explanation columns and the original four physical rows retained.
The daily exchange-rate review shows both currencies and all six body rows.
FX exposure retains current/prior row groups; liquidity reviews preserve the
bank's literal values and blank slots. The large current-liquidity table's
clipped row numbers remain unresolved. These are named table reviews, not
whole-report approval. Updated receipts must finish publication before the
additional tables appear live.

The narrative repair identifies oversized numerical envelopes containing two or
more separate ruled tables. Such envelopes cannot claim the prose between those
tables. Numerical and other speculative rectangles remain visible as
**Overlapping table candidates**. Standalone numerical tables keep their existing
membership pending source review. Roman heading prefixes stored separately from their titles stay with
the title when supported by the source style and block. These are candidate
relationships: uncertain table overlaps remain visible for review.

`AUDIT_DOCUMENTS` binds the existing `bddk-audit-reports` bucket to the Worker.
`/api/admin/document-corpus` requires the existing admin session before any
storage access and returns private, uncached responses. Storage keys are derived
from validated filing indexes and PDF hashes, never accepted from a request.
Page previews stream compressed JSONL and verify the exact page bytes against
their stored manifest. A missing connection, missing artifact or invalid checksum
is an unavailable/error state, never zero coverage. Large full-report artifacts
are streamed as downloads. Older captures remain downloadable but need a new
capture before page previews are available.
New source evidence also retains PDF-declared structure and a separate literal
glyph word view when image replacement text changes extraction. These are in the
page evidence JSON. Replacement-text coordinates and native table boundaries
remain unverified; the source's table tags can describe only column fragments.
The candidate table viewer also supports **PDF-linked label positions**: an
alternative for replacement text explicitly paired with an image in the PDF's
structure. It keeps raw labels and source piece IDs; full JSON retains the
original span/image/node links. These positions and table headers remain
unverified. Akbank and Albaraka 2026Q1 solo samples were published and independently
checked; live Akbank page 9 review confirms the alternative labels and figures.

The page viewer also reads separately stored image/outline recovery through
`/api/admin/document-recovery`. It shows source-linked OCR lines, differing or
missing OCR/outline readings, retained image-bearing OCR PDFs and full evidence.
The API accepts only the current source revision and checks artifact bytes before
returning them. A failed latest attempt remains visible alongside earlier retained
candidates. Recovery does not clear source review flags or mark values verified.
`recover-document-corpus.yml` runs manually and is configured to follow completed
source capture, limited to its successfully published filing/PDF revisions. Published FIBA 2025Q3 solo
pages 10/11/13 and ISCTR 2025Q1 consolidated page 11 have passed independent
artifact/source checks and live admin review. Whole-document accuracy, broader
recovery coverage remain pending; the automatic trigger still needs cloud validation.
The new recovery-table view keeps image and outline alternatives in each cell,
shows unresolved outlines explicitly and preserves unassigned header text.
Its source-pixel columns and inferred rows remain candidates. Independent
checks of four cloud sample pages pass the 59 selected cell associations.
Publication is independently verified for the four FIBA/ISCTR sample pages;
live FIBA page 13 shows the 64-row/six-column grid and the retained 717.417 versus
7.417 disagreement. Earlier packets still expose their original lines.
For pages without a ruled grid, a further candidate uses repeated amount
alignment. Its wrapped lines remain separate physical rows; absent text is
shown as `[no text observed]`, distinct from zero and unresolved outlines.
Recovered OCR blocks keep their line/word IDs and table membership. Full text
comparisons show the source transcription beside differing OCR, including
Turkish diacritics. Takasbank pages 1/13 are published and independently checked;
all three sample filings pass unchanged receipt replays with 25 object versions
unchanged. Neither a matching passage nor a receipt approves the rest of a page.
A further view shows text recovered from embedded fonts whose PDF Unicode maps
are empty. Source font/glyph/character/position bindings, original text and
alternatives remain in full evidence; the viewer exposes physical blocks and
side-by-side original/font readings. Unbound or ambiguous characters remain
unresolved. Font and OCR comparisons against complete source transcriptions are
separate; a matching font reading does not erase an OCR disagreement. The new
font view has passed independent cloud and publication checks on Takasbank pages
1/13. Live page 1 shows dotted İstanbul, the original image-reading disagreement
and 60 source-bound recovered characters; eight object versions stay unchanged
in the filing-receipt replay.

The audit vitals label is **Audit core statements / Loaded**: it reports the
balance-sheet and income-statement extraction flag. It does not certify all
lanes or a complete document. The former **Audit reports / Clean** wording was
misleading and has been corrected in code (2026-09-06).

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

The report view also exposes an independent official-source comparison through
`/api/admin/document-origin`: observation time, exact-byte agreement or revision
difference, opening-page identity, missing acquisitions and related archive PDFs
still awaiting capture. Links open the retained official PDF, raw HTTP response
and comparison receipt. The reader checks receipt hashes, filing/source bindings
and artifact checksums; anonymous access is forbidden. A source comparison can
be read before core capture exists. A mismatch with the currently displayed source
revision remains explicit. Byte agreement never clears semantic review. Other PDFs
in the same archive expand into their own page reader, with original/native
structure links and the same recovered-text/disagreement display. The member's
name, byte hash, transport and parent-report relationship are verified before
reading its separate index. An absent attachment never falls back to the primary
report. The signed Anadolubank declaration's two independently found OCR
word/diacritic differences remain visible.

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

The complete-document viewer preserves merged ruled-table cells when the stored
cell geometry supports one complete grid. It shows the source heading and,
where an explicit continued title and ordered column identifiers agree, offers
a link to the preceding physical fragment. Competing fragments remain labelled
ambiguous. Continuation links are candidates for review and do not combine rows
or approve header meanings, financial values or units.

Related PDFs expose their own source-period observations when an identity receipt
has been captured. The archive's reporting period is context, not a substitute for
the attachment's date. A retained conflicting claim remains visible alongside the
original PDF and source pages. Receipt hashes and exact native/container bindings
are checked; malformed or substituted reviews fail instead of clearing a conflict.


The official-source comparison has a retained-observation selector. A later
matching download does not hide earlier different PDFs or unavailable sources.
Each observation opens its own verified receipt, original response, official PDF
and regulator listing when present. Related archive members are resolved through
that exact observation rather than whichever download happened most recently.

A different-PDF observation offers a separate edition browser when capture exists:
original PDF page, native page evidence, page/full structure and selected recovered
text. It displays capture absence explicitly, never substituting the acquired
filing. The version difference still needs interpretation; this view does not
label it a correction, translation or replacement or promote its tables to series.


The source-line toggle also identifies columns projected across merged body
cells using printed headings and borders. The expanded view shows each projected
column separately; switching it off restores the original merged-cell display.
Isolated amounts or dashes keep their physical line instead of acquiring an
inferred row label. Header and numerical meanings still require review.


Delivered repair `e7c4770` passes CI `34142657725`; deployment `34142801505`
succeeded. All five fresh read-only probes (`34142688368`, `34142698600`,
`34142707866`, `34142716947`, `34142726635`) succeeded. Independent
downloaded-artifact checks pass all 93 registered cases across eight reports
and reproduce 47 unique complete-table reviews. Every original/native byte
and the entire fresh structure equal retained replay on all 384 pages of
the four comparison reports. Proof: `underline-cloud-independent-verification.json`
under `docs/knowledge/2026-09-06-document-corpus/`. Scoped publication
`34143241702` queues TOMK 2023Q3 unconsolidated (62 cases / 37 tables)
behind the existing corpus runs. Its live display remains unverified.


TOMK 2023Q3 source review now also covers the complete leverage table on PDF
page 36 and risk-weighted-assets table on page 37: 49 additional physical
rows / 223 slots. Their original 1.670.348 leverage assets, six section rows,
25 risk row numbers, grouped headings and every blank/dash are retained.
Ten complete risk-management and hedging paragraphs on those pages have
independent wording, source-bound and nearest-heading checks. The readable
`output/audit-corpus/TOMK_2023Q3_unconsolidated/risk-prose-reviewed.html`
and JSON include retained text, original spans, heading spans and page links.
Full heading hierarchy remains open. Narrative annotations with stored text
now reject a mismatch between that text and its expected fingerprint.
The local collection has 49 unique reviewed tables / 781 reviewed rows /
4,100 slots (488 original physical rows / 2,128 slots). There are 105
registered source cases across eight reports; TOMK has 74 cases / 39 tables.
This adds annotations without changing extraction engine c9134d44. The
earlier cloud proof and queued publication keep their 93-case / 47-table
snapshot. All 105 current cases pass locally against identical, independently
verified fresh cloud artifacts from the earlier e7c4770 probes. This is an
annotation replay against those sources, not a new cloud extraction. Receipt:
`risk-prose-cloud-source-verification.json` in the internal evidence directory.
The isolated staged source passes 2,927 Python tests (two skipped), 865 web
tests, all nine standalone gates, Python/web lint, web types and mobile
lint/types/design-token checks. Delivered review code is `370da26`; scoped
publication `34144411936` queues its TOMK 2023Q3 unconsolidated receipt
(74 cases / 39 unique complete tables) behind the existing corpus jobs. The
local prose output was visually checked through its final hedging paragraph.
The new receipt remains unverified live, and no whole report is certified complete.
