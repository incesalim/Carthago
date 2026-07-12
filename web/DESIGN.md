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
