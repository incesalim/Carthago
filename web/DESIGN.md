# Carthago design system

Status: **ACTIVE**. Shared identity and tokens date from 2026-07-11. The sector
workspace was redesigned on 2026-09-13; its contract below takes precedence over
the legacy document-sheet rules for all eight sector routes. The previous
"Editorial" (cream + serif + terracotta) system is retired.

## Identity in one sentence

A **document sheet on a desk**: one white sheet of analysis floating on a cool
paper workspace, read top-to-bottom like a briefing — typography and hairlines
do all the work; nothing is decorated.

## Shared identity and legacy document rules

1. **Legacy document routes use an open sheet.** Sector routes instead use the
   analytical panels defined below. On legacy routes, Hierarchy comes from hairlines (`border-hair`),
   two-pixel ink rules (`border-t-2 border-foreground`) and type weight — not
   from nested cards. (Legacy `Card`/`Stat` surfaces are tolerated in evidence
   layers until converted.)
2. **Blue is a verb.** `--primary` (#2757A8) means "this navigates" — links and
   route affordances only. Never decorative, never an eyebrow.
3. **Green/red state data direction only** (`--positive` #187A53 / `--negative`
   #C24847). Amber (`--warning` #B98514) marks thresholds and
   representative-data flags.
4. **Figures use tabular numerals.** Legacy document tables use `font-mono`;
   sector headline figures use the sans face for a consistent reading rhythm. Reader-facing labels and notes use the sans face at 11–14px; reserve mono
   for figures and compact numerical comparisons. Do not shrink prose to fit.
5. **No serif anywhere.** Instrument Sans carries body and display; `--font-serif`
   deliberately resolves to the sans stack so legacy `font-serif` degrades.
6. **Explain the data in the reader's language.** Sources, reporting dates,
   definitions and scenario assumptions stay available. Implementation plans,
   database names, code identifiers and release commentary do not become page
   headings or analytical copy. Research signals live in the admin-only
   `/admin/signals` workspace; their criteria and sources remain inspectable there.
7. **A claim is computed, or it does not print.** A sentence that asserts a
   **direction**, a **level** or a **ranking** is a claim about the data, not a
   label — and the series that settles it is almost always the chart's own `data`
   prop. Build it with `direction()` / `claim()` / `firstClaim()` / `signed()`
   (`lib/prose.ts`) or `seriesFinding()`, and fall back to the **topic** when the
   data won't support a finding: `title={claim(…) ?? "Loan / deposit by group"}`.
   Never type a direction word, a superlative, a universal ("every group"), or a
   `+` in front of a value that can go negative.
   Two gates enforce this — `prose-regression.test.ts` (feeds every insight
   builder sign-inverted fixtures and fails if a falling word survives a rising
   series) and `scripts/check_prose_claims.py` (CI). See
   [docs/knowledge/prose-claims-audit.md](../docs/knowledge/prose-claims-audit.md).
8. **Visual emphasis follows analytical importance.** The main measure, primary
   chart and supporting comparisons must be distinguishable. Do not force every
   chart into the same dimensions or make every heading a long computed claim.

## Tokens (globals.css is the source of truth)

| Role | Light | Dark |
| --- | --- | --- |
| `--background` (workspace) | `#F7F8F6` | `#101318` |
| `--card` (the sheet) | `#FFFFFF` | `#171B21` |
| `--foreground` (ink) | `#12161B` | `#E6E9E6` |
| `--muted-foreground` | `#50565E` | `#9AA3AD` |
| `--faint` (captions/axes) | `#6A6E73` | `#838A93` |
| `--border` (sheet edge) | `#E1E3DD` | `#262C34` |
| `--hair` (row hairlines) | `#ECEDE8` | `#1F252C` |
| `--primary` (links only) | `#2757A8` | `#7FA3D8` |
| `--data` / chart hero | `#2B4E7E` | `#7FA3D8` |
| `--context` (the non-hero mark) | `#C0C8D1` | `#4A525C` |
| `--positive` / `--negative` | `#187A53` / `#BC4645` | `#4FB98A` / `#E0716B` |
| `--warning` (thresholds) | `#8E660F` | `#D9A83F` |

**LOCKSTEP RULE:** `app/lib/chart-theme.ts` mirrors these values in JS (Recharts
can't read CSS vars). Any token change lands in both files in the same commit.
`scripts/check_contrast.py` now enforces the half that matters most — `axis` and
`inkMuted` render TEXT (tick labels, series names), so they must EQUAL `--faint`
and `--muted-foreground`, not merely resemble them.

**A TEXT COLOUR CLEARS 4.5:1, ON EVERY SURFACE IT SITS ON, IN BOTH THEMES.** Not
a taste question and not checked by eye — `check_contrast.py` computes it in CI
for every `text-*` token, against the sheet, the ground AND the muted row fill
(the darkest surface, and the pairing that fails first). `--faint` shipped at
**2.43:1** under 8–10px type on 210 call sites; the 2026-07-12 evaluation scored
accessibility 6.5/10 on the back of it. Two consequences the ramp had to absorb:
raising `faint` to AA squeezed it against `muted-foreground`, so that moved
darker too — the ordering `ink > secondary > quiet`, with a real gap between the
last two, is asserted in `tests/test_contrast.py`. And a colour used as text
needs a declared background, so a **chart series colour can no longer be a label
colour**: the amber chip at 3.27:1 keeps its coloured border and takes ink for
the word. Marks answer to a different rule (3:1, WCAG 1.4.11) and are left
alone.

Charts: hero navy + grey context (`--context`), direct end-labels via
`chart-end-labels.tsx`, hairline grid, no legend boxes.

**Every chart with a time axis drops a hover crosshair** — one vertical hairline
at the hovered date (`crosshairCursor(t)` from `chart-theme.ts`), so the reader
can carry the tooltip's value back to the axis. Recharts draws one by default but
hard-codes `#ccc`, which is off-palette on the light sheet and glaring on the
dark one; pass the helper to `<Tooltip cursor>` instead of taking the default.
Categorical bar charts (`BarByBank`) keep the band highlight (`t.cursor`): a line
down the middle of a bar reads as a gridline, a band reads as "this column".

**The plot starts where the heading starts.** A chart on the sheet has no card to
indent it, so a fat left gutter parks the mark to the right of its own title and
the page loses its left edge. Recharts invites exactly that: a `<YAxis>` has a
DEFAULT width of 60px, and that width sits ON TOP OF `margin.left` — the two
stack. Every value y-axis therefore takes `width={Y_AXIS_WIDTH}` (`"auto"` — the
axis sizes itself to its own ticks) and `left: PLOT_MARGIN_LEFT` (a thin margin,
so the leftmost x-tick label, which is centred on its tick, can't clip at the SVG
edge), both from `chart-theme.ts`. Never hand a value y-axis a hard-coded width:
"₺1,234 bn" and "0%" do not need the same room, and the guess is wrong for one of
them. A CATEGORY y-axis (BarByBank's bank names) is content, not scale furniture —
it keeps its own explicit width.

## Choosing the mark (read this BEFORE adding a chart)

**The mark answers the question the title asks.** A finding the mark cannot draw
is a finding the chart has not made — if the title says "−₺0.40 trn in the week"
and that move is three pixels of the plot, the title is a claim the reader must
take on trust. Pick the form from the question, then check it against these.

- **Composition is a share chart; a stack is not a trend chart.** For "who holds
  the book", default `StackedArea` to shares (bands to 100%): it is the only
  inflation-neutral view — a band can only grow by taking share. Levels stay
  reachable (the size of the book is a real question), but they stop being what
  the reader meets first. Only the bottom band of a stack has a flat baseline, so
  a stack can never show four trends: when each series' own shape is the point,
  use small multiples with a shared scale.
- **Every nominal ₺ level ships with its real twin.** In a ~30% CPI regime a
  nominal level chart is mostly a chart of the deflator (deposits: nominal ×2.86
  since May 2023, **real ×0.91**). Deflate, or index nominal-vs-real on one axis,
  and print the deflator's lag rather than hiding it.
- **A weekly Δ gets a Δ mark**, not a level chart with a Δ in the title: a signed
  strip (per group, zero-centred) beside the level, with the 4w/13w columns that
  say whether one week is noise.
- **Colour follows the entity, never the code table.** One group, one colour, on
  weekly and monthly charts alike. (Live bug: the weekly bulletin re-uses the
  bank-type codes with different meanings, so `seriesColor()` currently paints
  State in Dev & Inv's grey — see the register's design debt.)
- **Values live beside the mark, not on top of it.** Prefer a readout rail —
  a fixed column, populated at rest, updated on hover — to a floating tooltip
  that occludes the bands it describes and takes its numbers away on blur.
  Identity is direct-labelled at the band/line end; a legend chip is never the
  only key to a colour.
- **Bands are separated by the sheet, not by a border** — a 2px gap in the sheet
  colour between stacked fills; no outlines.

Worked example, on real rows, with the arithmetic:
`2026-07-12-composition-chart.html`, in the local design archive
(`docs/design/` — kept on disk, not versioned; see the register there).

**Comparison surfaces** (`/cross-bank`, `/banks`) add two rules of their own:

- **Rank is not distance.** A rank-coloured cell hides how FAR apart two banks
  are. Where the page's job is to compare, put the metric on a real value axis
  (the `/cross-bank` scorecard: peer ticks + IQR band + median + the picks as
  dots) and let the grid be evidence, not argument. The heat ramp is therefore
  deliberately quiet (`scoreToColor` caps at 26% / 12%).
- **A rank needs a stated peer set.** Any rank, median or axis must name the
  population it was computed over, and the reader must be able to change it
  (the peer frame). Ranking a ₺11bn digital bank against a ₺8.7trn state bank
  without saying so is a lie of omission.

## Sector workspace (2026-09-13)

The eight routes (`/`, `/credit`, `/deposits`, `/liquidity`, `/asset-quality`,
`/capital`, `/profitability`, `/market-risk`) share a financial analytics workspace
inside the existing navigation shell. This replaces the old no-boxes sector
brief. Use cool neutral ground, white analytical panels, fine full borders and
8–10px corners. Panels identify related analysis; avoid boxes inside boxes.

`sector-report.tsx` owns the report shell, `SectorOpening`, `SectorMetrics`,
`SectorGrid` and `SectorPanel`. Route server components retain the queries and
calculations. `sector-contents.tsx` owns reading position; `SectorTrend` owns chart
interaction. Static topic names and related routes live in `sector-pages.ts`.
Database concepts and implementation plans never become visitor-facing headings.

The opening combines a compact title/date header, topic navigation with one
labelled period selector and current indicators, then leads straight into the
first charts. A single dated assessment follows those charts: a readable lead
paragraph and all supporting notes grouped under short financial-topic headings.
Keep the lead and notes together, never split them into a banner and a later
block. Use a neutral panel, normal-weight prose with a bounded line length and
topic links; do not repeat the KPI row or collapse substantive analysis.
The history selector changes
charts, not the latest-period indicators. Four indicators use
four columns when there is room, six use six only on wide desktop; use two
columns on phones. Align metric labels and figures. Preserve essential dates
and basis notes, but consolidate text that repeats the adjacent indicator.

Each chapter answers a financial question. Loans pair nominal/real growth with
the currency-and-inflation waterfall; deposits separate currency and maturity;
liquidity separates regulatory ratios from funding; asset quality connects
stages, flows and coverage; capital connects adequacy, components and leverage;
profitability starts with returns and margins; market risk separates currency
positions, repricing and scenarios. Use the financial terms themselves, never
internal Now/Drivers/Evidence labels. Cross-links belong after the analysis.

Use 32–36px page titles, 22–24px chapter headings, 17–18px chart titles, 13–15px
explanatory copy and 12px source notes. Instrument Sans carries prose and headline
figures; reserve mono for compact data comparisons. Normal chart axes use 14px,
constrained facets 12px. Full series names and exact values belong in HTML outside
the plot. Do not shrink or truncate them to make a chart fit. Use 20–24px panel
padding and a regular 16–20px gap; choose panel proportions from the actual content.

`SectorTrend` supports combined histories for crossings/comparison and shared-scale
facets for individual bank-group histories. It pairs histories with full-name
current comparisons, using a right rail only when the container has room. All
groups remain available, with keyboard/pointer highlighting, clear null gaps,
lagging disclosure dates, exact values, data tables and CSV/image exports.
Ranges use rounded data-driven ticks. A line axis may crop with readable labels;
bars/areas preserve a zero baseline. Explicit regulatory/analytical references
must appear as labelled drawn lines and be included in the domain. Distinguish
BDDK's 12% capital target from the 8% statutory minimum. Regulatory constants come
from the existing domain definitions; do not invent new thresholds for design.

Signed bars/waterfalls explain contributions and rate scenarios; product
composition uses shares plus an amount view. Credit SME contributions remain a
subset of commercial lending, never an additional summand. Distinct LCR, NSFR
and leverage scales use separate plots. Retain group deltas explicitly when
replacing a chart whose old component supplied them by default.

Preserve every distinct measure, series, breakdown, table, scenario, reporting
basis, source, filter and export. Exact repetitions may be consolidated. Duplicate
historical/high-low tables may use a labelled disclosure while their histories,
latest levels and original comparisons remain available. Substantive analysis
stays in the normal reading flow. Keep daily, weekly, monthly and audited
quarterly bases distinct; `null` never becomes zero. Threshold methodology may
use a disclosure. Signal conditions, observations and evaluation states live
in the admin-only `/admin/signals` research workspace; sector pages retain their analyses.

Validate actual desktop and phone rendering: no page-wide horizontal overflow,
clipped labels, orphan half-rows, narrow value columns or gratuitous empty panels.
Verify real source-backed data, charts, range controls, group filters, tooltips,
exports and keyboard focus. Content preservation and passing tests are necessary;
neither replaces visual inspection. Research rationale and before/after inventory
are private in `docs/knowledge/2026-09-13-dashboard-research/` and
`docs/knowledge/2026-09-13-sector-redesign/`.

**The mark has to fit the data, not the idea.** A decomposition that sums to a
total is a stacked area — *unless a component can go negative*, in which case a
stack silently misstates the total. `/liquidity`'s reserve buffer is the case in
point: the CBRT's own net FX is negative for 42 of 150 weeks, so it is drawn as
three lines (gross / net / net-excl-swaps) with the two gaps shaded and a zero
line (`app/liquidity/ReserveBuffer.tsx`, Recharts range areas). Check the range
of every component before choosing a stack.

**Every figure has an observation contract.** At page level, `<DeskHeader>`
prints an `ObservationRail`; whenever the clock changes inside the page,
`<CadenceBand>` repeats the hand-off. An observation names at least its cadence
and date, and adds the relevant window and basis. Role labels (`current`,
`structure`, `audited`, `early-warning`) say why several clocks legitimately
coexist. Daily, weekly, monthly and quarterly figures must never look like one
simultaneous snapshot merely because they fit in one row.

When unlike-frequency series enter one calculation, use `alignLatest()` from
`app/lib/cadence.ts`: cut all inputs at the earliest latest observation, then
take each input's last value at or before that common cutoff. Preserve `null`;
never convert missing data to zero or nowcast a slower series merely to fill the
latest weekly date.

**Never mix cadences in one Δ column or vital band.** A weekly Movers table takes
weekly rows only; a daily series (net CBRT funding) gets its own daily band. A
monthly published funding ratio and a weekly computed TL ratio are separate
bands even when both are loan-to-deposit measures. Pair the "prev" row off a
SINGLE-series array — long-form rows (`{period, bank_type_code, value}`) put
another group at `.at(-2)`, not last week.

**Compare like with like — the same BASIS, not just the same cadence.** The same
quantity often exists twice: sector CAR is 16.34% in the BDDK monthly bulletin and
16.02% in the audited Σ/Σ filings. Subtracting one from the other (`/capital`: is
the hybrid stack bigger than the buffer?) silently flatters or damns the answer.
Compute both sides on one basis and print which.

**When a metric legitimately has several bases, one module owns them and every
label names its own.** Loan-to-deposit exists three ways here — BDDK's published
TL+FC monthly ratio, our computed TL-only weekly ratio by ownership group, and a
bank's own audited quarterly one — and all three once printed as "Loan / deposit",
so `/deposits` showed a comfortable 91% while `/liquidity`, one click away,
flagged 97%. `app/lib/ldr.ts` now holds the label, the source-and-cadence note,
the threshold and the pointer to the sibling figure for each; surfaces import,
never retype. Different thresholds are fine and often right (the TL book is
judged at 95, the blend at 100) — the flag prints which basis its rule tests.

**One metric, one number — never print a home-made version of a published one.**
If the source publishes the metric, that figure IS the page's figure. A derived
effect is applied to it as a **delta**, not computed as a rival. (`/profitability`
nearly shipped a hand-rolled ROE of 25.8% — net profit ÷ average equity — in the
band beside BDDK's published 24.7%. The demand-book counterfactual is now a cost
in pp *against* the published ratio.) Two numbers for one thing is a bug even when
both are right.

**A cumulative source must be de-cumulated before it is read as a month.** The
BDDK income statement is year-to-date (net profit 0.09 → 0.17 → 0.29 → 0.36), and
every ratio built from it — ROE, ROA, NIM, OPEX — is a YTD figure annualized. For
"what happened this month", subtract last month's YTD, and remember **January IS
the year to date**. A YTD average cannot show that May's net interest income rose
₺98bn while the profit fell.

**Derived aggregates reconcile against the source's own total, and fail loudly.**
A bridge assembled from fixed `item_order` positions drifts silently the day the
source renumbers a line. Check the sum against the reported total on every render
(`|bridge − reported| > tolerance`) and print a data-quality flag INSTEAD of the
chart when it breaks. A page that must survive a cron cannot fail quietly.

**Print the step, don't average it.** A twelve-month "drift" that spans a
discontinuity is not a trend, and extrapolating it is arithmetic dressed as a
forecast. `/capital` detects the break from the series (`detectStep` — a move
3× the typical one), splits the year into the step and everything else, sizes the
buffer against the POST-step slope, and names the window it used. When a page
cannot attribute a break, it says so.

## Shell (do not re-implement per page)

`app/layout.tsx` renders the workspace: quiet rail (`Nav.tsx` — plain text,
mono-caps group labels, ink active bar, no fills) + the sheet wrapper
(`bg-card rounded-[10px] border shadow-sheet`). Pages start directly with
`<main>` as above.

## The brand mark

A **compass** in navy→blue gradient: an open "C" ring, a pointer needle, a centre
hub, two orbital dots that read as an "i", and a lower swoosh. Navigation for the
Turkish banking sector, inside the initial.

Brand palette — used by the mark and the social card **only**. It is not a UI
palette: the Desk's blue-is-links rule still holds everywhere else.

| | | |
|---|---|---|
| `#0D1B2A` | ink navy | wordmark, deepest gradient stop |
| `#1F2E4A` | deep navy | hub, needle |
| `#2D5B8C` | mid blue | ring, swoosh, tagline |
| `#7FA0BF` | light blue | gradient highlight |
| `#E6EEF6` | pale | — |

**The source of truth is a single PNG: [`scripts/brand/carthago-mark.png`](../scripts/brand/carthago-mark.png)**
— the mark keyed to transparency. Every asset (`favicon.ico`, `icon.png`,
`apple-icon.png`, `opengraph-image.png`, `twitter-image.png`, `public/logo.png`) is
**composited from it** by [`scripts/make_brand_assets.py`](../scripts/make_brand_assets.py),
so the mark can never drift between uses. To change the logo, replace that one PNG and
re-run the script — never hand-edit a generated asset. `favicon.ico` must stay RGBA or
the Next build rejects it.

Everything is transparent so the mark blends with whatever is behind it — the browser
tab bar, the paper ground, the graphite nav — rather than sitting in a box. The compass
still has navy elements (ring, hub, needle) that sink into the dark sheet, so the nav
swaps to **`public/logo-dark.png`** in dark mode: the same mark tonally lifted (each
pixel's lightness raised toward white, hue and chroma preserved) so it reads on graphite.
Both variants come out of the generator; the swap is a `dark:hidden` / `hidden dark:block`
pair in `Nav.tsx`. `apple-icon.png` is the one exception to transparency (opaque white
square): iOS renders transparency as black.

## Process

Design work starts from a named direction and this file — not inline tweaks.
For a new direction, produce divergent prototypes on real data first (the
mockup that chose this system: [The Desk, full sector
suite](https://claude.ai/code/artifact/28b72bb4-fade-433b-a2dc-aff39e31860e)).
Iterate by naming the defect, verify by screenshot against this file.

**File the artefact.** Every mockup goes in `docs/design/mockups/` as
`YYYY-MM-DD-<slug>.html` plus desktop/mobile screenshots, and gets a row in
`docs/design/MOCKUPS.md` — the register of what was designed and whether it
shipped — **in the same change**. That whole archive is **local only**
(gitignored): it ran to ~16MB of superseded iterations and serves no reader of
the public code. Filing the artefact still matters — design work is expensive to
redo and cheap to forget — it just lives on your disk, not in the repo. Never put a mockup in
`web/public/`: that directory is served, so it deploys to carthago.app.
