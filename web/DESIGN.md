# Carthago design constitution — "The Desk"

Status: **ACTIVE** (shipped 2026-07-11). Every design/UI change starts from this
file. The previous "Editorial" (cream + serif + terracotta) system is retired.

## Identity in one sentence

A **document sheet on a desk**: one white sheet of analysis floating on a cool
paper workspace, read top-to-bottom like a briefing — typography and hairlines
do all the work; nothing is decorated.

## Ground rules (the anti-defaults)

1. **No boxes inside the sheet.** Hierarchy comes from hairlines (`border-hair`),
   two-pixel ink rules (`border-t-2 border-foreground`) and type weight — not
   from nested cards. (Legacy `Card`/`Stat` surfaces are tolerated in evidence
   layers until converted.)
2. **Blue is a verb.** `--primary` (#2757A8) means "this navigates" — links and
   route affordances only. Never decorative, never an eyebrow.
3. **Green/red state data direction only** (`--positive` #187A53 / `--negative`
   #C24847). Amber (`--warning` #B98514) marks thresholds and
   representative-data flags.
4. **Every figure is mono** (`font-mono`, tabular). Labels that annotate data
   (record lines, section metas, rules, colophons) are mono-caps 8–10px.
5. **No serif anywhere.** Instrument Sans carries body and display; `--font-serif`
   deliberately resolves to the sans stack so legacy `font-serif` degrades.
6. **Automation honesty.** The site is compiled, not written: flags print their
   rule (`consecutive_rise(npl) ≥ 6m`), metas say how a number was made
   ("transmission computed", "schedule — not a forecast"), and each page ends
   with the `<Colophon/>`.
7. **Boldness lives in one signature element per page** — the vitals band. Keep
   everything else quiet.

## Tokens (globals.css is the source of truth)

| Role | Light | Dark |
| --- | --- | --- |
| `--background` (workspace) | `#F7F8F6` | `#101318` |
| `--card` (the sheet) | `#FFFFFF` | `#171B21` |
| `--foreground` (ink) | `#12161B` | `#E6E9E6` |
| `--muted-foreground` | `#68707A` | `#9AA3AD` |
| `--faint` (captions/axes) | `#A0A7AE` | `#6B747E` |
| `--border` (sheet edge) | `#E1E3DD` | `#262C34` |
| `--hair` (row hairlines) | `#ECEDE8` | `#1F252C` |
| `--primary` (links only) | `#2757A8` | `#7FA3D8` |
| `--data` / chart hero | `#2B4E7E` | `#7FA3D8` |
| `--context` (the non-hero mark) | `#C0C8D1` | `#4A525C` |
| `--positive` / `--negative` | `#187A53` / `#C24847` | `#4FB98A` / `#E0716B` |
| `--warning` (thresholds) | `#B98514` | `#D9A83F` |

**LOCKSTEP RULE:** `app/lib/chart-theme.ts` mirrors these values in JS (Recharts
can't read CSS vars). Any token change lands in both files in the same commit.
Charts: hero navy + grey context (`--context`), direct end-labels via
`chart-end-labels.tsx`, hairline grid, no legend boxes.

**Every chart with a time axis drops a hover crosshair** — one vertical hairline
at the hovered date (`crosshairCursor(t)` from `chart-theme.ts`), so the reader
can carry the tooltip's value back to the axis. Recharts draws one by default but
hard-codes `#ccc`, which is off-palette on the light sheet and glaring on the
dark one; pass the helper to `<Tooltip cursor>` instead of taking the default.
Categorical bar charts (`BarByBank`) keep the band highlight (`t.cursor`): a line
down the middle of a bar reads as a gridline, a band reads as "this column".

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
[the composition chart](../docs/design/mockups/2026-07-12-composition-chart.html)
([register row](../docs/design/MOCKUPS.md)).

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

## The two-layer page skeleton

Every sector tab is a **brief above its evidence**. Components live in
`app/components/desk.tsx`; pure helpers (streaks, window extremes, CPI
transforms) in `app/lib/desk.ts`. The reference implementation is `app/page.tsx`.

```
<main class="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
  <DeskHeader title record="Record May 2026 · vs Apr" right="every figure computed…" />
  <Tape items={…} />                      ← Overview only
  <SecHead title="The vitals" meta … />
  <Vitals> <Vital … /> ×4–6 </Vitals>     ← the signature: type-only cells,
                                            mono value + sparkline + computed note
  [Movers | Transmission]                 ← grid lg:grid-cols-[5fr_7fr]
  [Flags | Standings | Ahead]             ← grid lg:grid-cols-3 (what the page's data supports)
  <Depth action={<GlobalRangeSelector/>}> ← "In depth — carried over, restyled, not removed"
    …the page's full pre-Desk chart/table library…
  </Depth>
  <Colophon />
</main>
```

**Carry-over contract:** converting a page to the Desk NEVER deletes analytical
content. Existing charts, tables and sections move under `<Depth>`, keep their
data wiring (range selector, bank-type filters, findings-titles), and only lose
chrome. Vitals notes and flags must be **computed from series the page already
fetches** — no hand-written claims, no forecasts.

**The evidence layer speaks the brief's language** (shipped 2026-07-12 on
Overview; the pattern the other tabs follow). Below the `<Depth>` rule a page
must not invent a second grid or re-introduce surfaces:

- **No `Stat`/`Card` boxes.** A row of KPI cards becomes the page's own
  `<Vitals rule="hair">` band — the *same cells* as the brief, re-rendered for
  whatever the filter selects, with `<Levels>` carrying the level figures above
  it and `<PeerBar>` marking where the sector sits in the league of groups.
- **`<Takeaway variant="desk">`** — kicker, headline, hairline-ruled drivers.
  The boxed variant survives only on tabs not yet converted.
- **Charts sit on the sheet** (`<TrendChart plain …>`): finding title, mono-caps
  sub-line, and `<ChartFoot>` under the mark (hero latest, Δ 12m, leading and
  trailing group — computed from the rows the chart draws, so the finding
  survives a screenshot). Two per row, so each spans three cells of the band.
- **Controls are mono-caps with an ink underline** (`BankTypeFilter`), never
  pills and never blue — blue is a verb, and switching a band navigates nowhere.
- **A rule prints whether or not it fires.** `<Flags showCleared>` lists the
  tests that did *not* trip, with their thresholds (`/deposits`): a quiet page is
  evidence the tests ran, not an absence of work. Give each `Flag` a `clear` line
  saying what the test measured.
- **A split that IS the page's frame gets a table.** `<Compare a b rows>`
  (`/liquidity`: public vs private) — where the whole analysis rests on two
  populations, print them side by side with the gap, instead of making the reader
  infer it from four charts.

**The mark has to fit the data, not the idea.** A decomposition that sums to a
total is a stacked area — *unless a component can go negative*, in which case a
stack silently misstates the total. `/liquidity`'s reserve buffer is the case in
point: the CBRT's own net FX is negative for 42 of 150 weeks, so it is drawn as
three lines (gross / net / net-excl-swaps) with the two gaps shaded and a zero
line (`app/liquidity/ReserveBuffer.tsx`, Recharts range areas). Check the range
of every component before choosing a stack.

**Never mix cadences in one Δ column.** A weekly Movers table takes weekly rows
only; a daily series (net CBRT funding) goes to the transmission, where its basis
is stated. And pair the "prev" row off a SINGLE-series array — long-form rows
(`{period, bank_type_code, value}`) put another group at `.at(-2)`, not last week.

**Compare like with like — the same BASIS, not just the same cadence.** The same
quantity often exists twice: sector CAR is 16.34% in the BDDK monthly bulletin and
16.02% in the audited Σ/Σ filings. Subtracting one from the other (`/capital`: is
the hybrid stack bigger than the buffer?) silently flatters or damns the answer.
Compute both sides on one basis and print which.

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

## Process

Design work starts from a named direction and this file — not inline tweaks.
For a new direction, produce divergent prototypes on real data first (the
mockup that chose this system: [The Desk, full sector
suite](https://claude.ai/code/artifact/28b72bb4-fade-433b-a2dc-aff39e31860e)).
Iterate by naming the defect, verify by screenshot against this file.

**File the artefact.** Every mockup goes in `docs/design/mockups/` as
`YYYY-MM-DD-<slug>.html` plus desktop/mobile screenshots, and gets a row in
[`docs/design/MOCKUPS.md`](../docs/design/MOCKUPS.md) — the register of what was
designed and whether it shipped — **in the same change**. Never put a mockup in
`web/public/`: that directory is served, so it deploys to carthago.app.
