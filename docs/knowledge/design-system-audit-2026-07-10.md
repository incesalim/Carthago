# Design & style audit — Carthago (2026-07-10)

**Status:** Reference / descriptive. A code-grounded walkthrough of the site's design
**language** and the **style of every one of the 34 pages**, plus a consistency map of where
pages honour the system and where they drift. Companion to the subjective
[design-critique-2026-07-10.md](design-critique-2026-07-10.md) (opinion/verdict on 3 live pages)
and [ft-visual-journalism/](ft-visual-journalism) (chart references). This doc is the "what is
actually there" inventory; the critique is the "what to change."

Method: read `globals.css`, `layout.tsx`, `Nav.tsx`, the `components/ui/*` primitives and
`chart-theme.ts` for the foundations, then analysed all 34 `app/**/page.tsx` + their route-local
components. Not acted on — inventory only.

---

## 1. The design language

**Concept: "editorial / print-magazine finance."** Warm cream paper, navy ink, a single
terracotta accent, flat hairline-bordered surfaces, serif headlines over letter-spaced mono
labels. It reads as *FT / old-money broadsheet*, deliberately unlike the generic
Tailwind/shadcn SaaS-dashboard look. This identity is real and consistent at the token level;
the drift is all at the page-composition level (§4).

### Colour (tokens in `app/globals.css`, both themes)
Light `:root` → dark `.dark`, toggled by `next-themes` (class strategy). Everything is a
semantic token; **no page should hard-code colour** (a few do — see §4).

| Role | Light | Dark | Notes |
|---|---|---|---|
| `background` | `#ECE8E0` warm cream | `#181712` warm near-black | page surface |
| `card` | `#FBFAF7` near-white | `#211F1A` | raised surfaces (only ~1 value above bg → the "flatness" the critique flags) |
| `foreground` | `#16243B` navy ink | `#ECE8E0` cream | body text |
| `muted` / `muted-foreground` | `#ECE8DF` / `#6A7384` | `#2A2722` / `#B0A893` | subtotal fills, secondary text |
| `border` | `#E2DCD0` warm hairline | `#36322B` | the app-wide default border |
| `primary` | `#C2603A` terracotta | `#D7794F` | brand: eyebrows, links, active toggles, focus ring |
| `faint` | `#9AA1AD` | `#8A8472` | captions, chart axis ticks |
| `positive`/`negative`/`warning`/`info` | `#2E7D5F` / `#B23A3A` / `#B07D1A` / `#1C3A60` | brightened | data semantics (also used as `/10`–`/15` tints) |
| `chart-1…6` | `#1C3A60` navy · `#3E6098` · `#88A0C0` · `#B98A5E` tan · `#6E4B6E` plum · `#9AA1AD` gray | lightened set | categorical series — navy-led, warm/cool spread |

**Fixed bank-type colour slots** (`chart-theme.ts` `BANK_TYPE_COLOR_INDEX`): Sector→navy(0),
State→(1), Private→(2), Foreign→tan(3), Participation→plum(4), Dev&Inv→gray(5). A group keeps
one hue across every chart. **Note:** brand terracotta (`primary`) and semantic `negative` are
both warm reds — they can collide (critique issue #6).

### Typography (role-based, `layout.tsx`)
Three Google fonts, three jobs:
- **`font-serif`** = Source Serif 4 → all headings + chart titles (the editorial signature).
- **`font-mono`** = IBM Plex Mono → all labels, eyebrows, and **every number** (tabular-nums).
- **`font-sans`** = IBM Plex Sans → body copy.

Type scale in use: page `h1` serif `text-3xl`; section `h2` serif `text-xl`; chart/card titles
serif `text-[15px]`; "The Read" lead serif `text-[21px]`; eyebrows/labels mono `text-[9–11px]`
uppercase `tracking-[0.06–0.18em]`. The mono-caps label is applied to eyebrows, section indices,
*and* every KPI label — the "over-applied signature" the critique flags.

### Surfaces, spacing, motion
- Flat: `--radius` = **10px** cards, hairline borders, **no shadows** (shadows only sneak in on a
  few drawers/tooltips — §4). Figure-ground rests on the ~1-step cream→near-white card lift.
- Standard page shell: `<main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">`;
  sections `space-y-4`; chart grids `grid grid-cols-1 lg:grid-cols-2|3 gap-4`; KPI grids
  `grid-cols-2 lg:grid-cols-3|4 gap-3`.
- Motion is minimal: `transition-colors` hovers, `hover:border-primary/40` on cards, drawer
  slide-ins. No decorative animation.

### Navigation (`Nav.tsx`)
Left sidebar `w-56`, sticky full-height, `bg-card` with a hairline right border; brand lockup
(logo + serif "Carthago" + mono terracotta "TURKISH BANKING SECTOR" microline) pinned top,
`ThemeToggle` pinned bottom. Four mono-labelled groups — **Sector · By Bank · Markets & Macro ·
More** — with collapsible sub-groups (chevrons) that auto-open on the active route. Below `lg`
it collapses to a sticky top bar + slide-in drawer (scroll-locked, backdrop-blurred). Active
link = `font-semibold text-foreground`; nested children indented under a `border-l` rail.

### The signature components (`components/ui/*` + a few shared)
- **`PageHeader`** — the editorial masthead: optional mono terracotta `eyebrow`, serif `text-3xl`
  title, muted `description`, a green-dot **"Data through …"** `Badge`, an optional **global
  range selector** (1Y/3Y/5Y/YTD/All), and action `children`. Frosted `backdrop-blur` band that
  pins to `top-0` on `lg` so the range control stays reachable on long pages.
- **`Takeaway` ("The Read")** — the product's differentiator. Terracotta left rail + mono kicker
  ("THE READ · Carthago analysis · {date} computed") + serif `text-[21px]` lead sentence + a
  joined-cell grid of tone-glyph drivers (▲ positive / ◆ warn / ● neutral) that link to the tab
  proving each. Computed deterministically from D1 (`lib/insights.ts`), optionally LLM-reworded
  (`withLlmHeadline`) only when the rewrite still matches the live numbers.
- **`Section`** — labelled block: optional mono numbered `index` ("01") + serif `text-xl` title +
  muted description + right-aligned `actions`. The intended heading spine (under-used — §4).
- **`Stat`** — KPI tile: mono `text-[10px]` uppercase label, large mono `text-2xl` tone-coloured
  value, muted hint, optional `Sparkline` child + `DeltaBadge` (period-over-period, `goodDirection`
  colours NPL/OPEX-down as green). Tones: neutral/positive/warning/negative.
- **`ChartCard`** — shared chart chrome: serif title, muted description, hover-revealed export
  pills (Copy-image / PNG / **CSV** / Expand-to-modal, via `ChartExport`+`ChartData`), optional
  mono `source` footer. Every chart wrapper renders inside it.
- **`Card` / `Table` / `Badge` / `DeltaBadge` / `Sparkline` / `Separator` / `Skeleton`** — the rest
  of the kit. `Table` is token-styled + horizontally scrollable (but hand-rolled `<table>`s
  bypass it in many pages — §4).
- **Chart wrappers** (`components/`): `TrendChart` (period-keyed multi-series line),
  `TimeSeriesChart` (EVDS date-keyed line), `StackedArea` (+`percentStack`, `colorKeys`),
  `BarByBank` (horizontal ranked bars), `BopFlowChart` (signed/grouped bars ± overlay line).
  Colours come from `useChartTheme()` (Recharts can't read CSS vars from SVG attrs).

### Editorial devices (the "structure-as-information" layer)
Mono eyebrows, numbered `Section` indices, the green-dot freshness pill, "The Read", figure
numbering ("Şekil N ·") preserved on economy pages, mono source footers, rank chips ("3rd of 28
by assets"), Yahoo-style period-end statement columns with an amber ⚠ on validation-failed
quarters. JSON-LD (`Organization`/`WebSite`/`Dataset`) is injected site-wide + on the home page.

---

## 2. Per-page catalogue (34 pages, by nav group)

Legend for each page: **Header** (PageHeader config) · **Read** (Takeaway y/n) · **Body** ·
**Character**.

### Sector
- **`/` Overview** — *the cockpit.* Header: eyebrow "Banking Sector", range, freshness; **Read: yes**.
  Body: `Section 01 "Snapshot"` (a `?type=`-switchable `BankTypeFilter` over a 4-up size/growth KPI
  grid + 6-up Table-15 ratio grid, every tile a `KpiCard` = Stat + Sparkline + DeltaBadge) →
  `Section 02 "Sector dynamics"` (2×2 by-group `TrendChart`s). *The most dashboard-dense stat
  surface; fully on-system with numbered sections. Only page with an eyebrow-led masthead + JSON-LD Dataset.*
- **`/credit`** — Read: yes. Five numbered Sections / ~14 charts (growth, real-terms twin,
  FX-adjusted, public-vs-private, consumer mix `StackedArea`s, SME). *Densest sector page; textbook
  system conformance, visually plain.*
- **`/deposits`** — Read: yes. Four numbered Sections; alternates dense multi-chart grids with
  deliberately spare single full-width charts (`height={320}`) as breathing room. `colorKeys`
  locks stack hues to the sibling line chart.
- **`/liquidity`** — Read: yes. **Sections drop the `index`** (serif titles, no numbers). Mixes
  `TrendChart` (weekly) and `TimeSeriesChart` (EVDS) heavily; long methodology-heavy descriptions →
  "report-note" texture. *Tier-2 heading treatment.*
- **`/asset-quality`** — Read: yes. Numbered Sections; §02 is conditional and embeds a mid-page
  3-up `Stat` scenario row ("X% of Stage-2 migrates → +₺Xbn provisions", warning tone + "not a
  forecast" disclaimer) — a sizing device, not a header KPI row.
- **`/capital`** — Read: yes. **Major deviation: no `Section` primitive** — bespoke
  `<h2 class="text-base font-semibold">` **sans** headings, no serif, no index. Contains the new
  `CapitalByBank` league table (hand-built bar-in-row, not the `Table` primitive) + a "Headroom"
  Stat row. *Tier-3 heading treatment.*
- **`/profitability`** — Read: yes. **Same no-Section deviation.** Two signatures: a 6-tile
  **DuPont "return equation"** row (labels literally read `ROA × Leverage = ROE …`), and the
  `NimComponents` **signed-stack NIM chart** — the single most bespoke viz, with its **own 8-colour
  palette** outside `chart-theme.ts`, luminance-aware in-bar labels, a halo net-line, a fully custom
  grouped tooltip, and pill toggles (group / annual-vs-TTM).

### By Bank
- **`/banks`** — index. Header: title only + a custom cross-link row; **no Read**. Bespoke small
  uppercase group headers (not `Section`) over a 3-up grid of hand-rolled `<Link>` cards (logo +
  terracotta ticker chip + name + type badge). *Quiet catalogue; the critique's blank-logo bug lives here.*
- **`/banks/[ticker]`** — *the richest, most bespoke page.* Header: eyebrow=ticker, logo+serif name
  title, `sticky={false}` because the page pins **header + `BankSectionNav` pill-jump-nav as one
  group**; narrow **`max-w-5xl`** document column. Anchored sections: Overview (rank chips +
  `BankCard` 3-col profile + listed-bank valuation KPI row & price line) → Performance → Market Risk
  (custom `DivergingBars`) → Capital (Stat grid) → **Financials** (4 segmented pill toggle-groups +
  Yahoo-style statement `<table>` with muted subtotal bands, ⚠ flags, `CopyTableButton`; IS view
  appends the **hand-rolled SVG `PlSankeyChart`**) → Ownership (shareholder progress bars) → News →
  Earnings & Disclosures. *A "report" feel; two custom in-file data-viz.*
- **`/cross-bank` Compare** — Header: title + computed description, **no green-dot badge** (period
  folded into text); no Read; `space-y-6`. Body: `HeatmapView` (Snapshot/Over-time toggle) — dense
  CSS-grid **heatmaps** with sticky axes, rank-coloured cells (green better/red worse), clickable
  sort headers — + `MarketShareSection` (HHI Stat row + league `<table>` with signed share-shift &
  ▲/▼ rank moves). *"Trading-terminal density" inside the warm palette.*
- **`/ownership`** — Header: eyebrow "KAP"; narrow `max-w-5xl`; no `Section`. Renders `OwnershipNetwork`
  — a full-immersive **zoom/pan d3-force SVG node-link graph** (ego-highlight, focus-mode radial fan,
  URL-synced state). *Most graphically ambitious page; colours from the chart palette.*
- **`/earnings`** — **Off-system.** No `PageHeader` (sans `text-2xl` h1); `max-w-5xl`; per-bank
  `<section>` of `EventRow` cards with **raw indigo/emerald/amber** kind badges (not tokens);
  `rounded-md`. *Feed-family look, least-migrated.*
- **`/franchise`** — **The most on-system page.** Full `PageHeader` (eyebrow + freshness), two proper
  `Section`s, `Stat` grid, and the shared **`Table`** primitive + a dashed empty state. Clean,
  low-density reference table. No deviations.
- **`/disclosures`** — **Off-system.** No `PageHeader` (sans `text-2xl` h1); narrowest columns
  (`max-w-4xl`/`3xl`); `DisclosureCard` = `rounded-xl` card with a terracotta `border-l-primary` rail.
  Feed-family with /earnings.

### Markets & Macro
- **`/rates`** — Header on-system (eyebrow "TCMB EVDS", range). **No Read; no `Section` at all** —
  bare `<div>` grids with ad-hoc `mb-*` on `space-y-6` main. KPI `Stat` row + 6 charts (corridor,
  transmission, deposit-rate ladder, spreads, FX, sterilization). *Structurally the barest page.*
- **`/market-risk`** — *cleanest textbook example.* Header: eyebrow "CAMELS S" (no range — quarterly);
  **Read: yes**; on-system Sections; `TrendChart` + `ChartCard`-wrapped `BopFlowChart`; conditional
  NII-scenario `Stat` row (tone-coloured). Fully token-compliant.
- **`/funds`** — Header: eyebrow "TEFAS", range; no Read. Five Sections of `StackedArea`/`TrendChart`
  + three `TopFundsTable` (shared `Table`). Minor: sub-table headings are sans `text-sm` not serif;
  local `nf` re-declared.
- **`/digital`** — Header: eyebrow "TBB & TKBB", range; no Read. Longest page — 7 Sections of
  adoption/transactions/acquisition/demographics. On-system except **raw hex `MOBILE_FILL`/
  `INTERNET_FILL`** for grouped bars (intentional, to match line colours).
- **`/non-bank`** — Header: no eyebrow, range; no Read. 3-up `Stat` row + `StackedArea` + a
  **hand-rolled `<table>`** (`bg-accent/40` header, `rounded-lg` — radius drift).
- **`/non-bank/share-of-banking`** — Header: no eyebrow, range; no Read. `Stat` row +
  `TimeSeriesChart` + a **bespoke div-bar chart** (`bg-primary/70` fill on `bg-accent/40` track,
  `rounded` 4px, no card chrome).
- **`/economy` (hub)** — Header: title, range; no Read. Family outlier: the **only page with a
  `MarketTicker` band**, no KPI Stat row, and **only `TimeSeriesChart`** (no BopFlow, no Şekil
  numbering). Ends in a hand-rolled BBVA baseline `<table>`.
- **`/economy/economic-growth · balance-of-payments · budget · inflation · foreign-trade`** — a
  **near-templated Albaraka-outlook family**: 3-up cover `Stat` row → Sections of `TimeSeriesChart` +
  `ChartCard`-wrapped `BopFlowChart` with **"Şekil N ·" figure numbering** → hand-rolled summary
  `<table>` → footer source line chaining to the next page. Each re-declares local hex colour
  constants + number formatters. BoP is uniquely dense (16 charts, two Stat rows). *Strong shared
  convention; drift is in back-link styling, footer placement, and the repeated hand-rolled tables.*

### More
- **`/regulation`** — **Off-system.** No `PageHeader` (sans `text-2xl` h1). AI "regulatory snapshot"
  `BriefingWidget` (`rounded-[10px]` category cards) + client `RawFeeds` two-column feed of
  `rounded-md` cards with **hardcoded hex left-borders** (`#1f4068`/`#0f7b6c`) and **light-only
  pastel pills** (`news-tags.ts` — break dark mode) + a `shadow-2xl` slide-in drawer.
- **`/news` · `/news/google`** — **Off-system feed pages.** No `PageHeader` (sans `text-2xl` h1);
  `MarketTicker` band; `space-y-6`; shared `PressFeed` = outlet filter chips + `rounded-md` `PressCard`
  grid with raw pastel topic pills + `bg-primary/10` bank chips. Google is a data-source clone of News.
- **`/pipeline`** — Header on-system (eyebrow "Data lineage"). React Flow lineage graph **wired into
  the token system** (semantic tone dots, chart-palette left-border accents, CSS-var edges,
  theme-bound `colorMode`); caveats are third-party-imposed (`shadow-sm` nodes, `rounded-lg`,
  MiniMap/Controls chrome, sans labels).
- **`/admin`** — Header on-system (eyebrow "Internal" + Sign-out button). Built from primitives but a
  **denser utilitarian register**: off-shell `max-w-6xl`; Data-health `Stat` cards, `CoverageMatrix`
  (bespoke `text-[10-11px]` table + `HealthBar` + drawer with `shadow-xl`), `PipelinePanel`,
  `TrafficPanel` (clean `Table` usage). Own narrow `LoginForm`/`Forbidden` card states off the shell.
- **`/sector` · `/sector/ratios`** — **not pages**: hard `redirect()` stubs to `/` and `/#by-type`
  (folded into Overview; kept for old deep links).
- **`/_valuation`** — **un-routed** (leading-underscore private folder; archived, code intact). One of
  the *most* on-system pages when it existed: `PageHeader`, multiple `Section`s, `Stat`/`ChartCard`/
  `Table`/`Badge`/`Button`, token-styled form controls (slider `accent-primary`, `focus-visible:ring-ring`).
  Stale: metadata still claims `canonical:"/valuation"`.

---

## 3. Consistency map — adherence tiers

Every page shares the **foundations** (tokens, fonts, `PageHeader` where used, chart theming,
`space-y` rhythm). Divergence is in page composition, on a spectrum:

- **Tier A — fully on-system** (PageHeader + `Section` + shared primitives, incl. `Table`):
  `/franchise`, `/market-risk`, `/economy` family, `/_valuation` (hidden), `/pipeline` (+ token graph),
  `/admin` (utilitarian but primitive-built). Plus the numbered-Section sector pages `/`, `/credit`,
  `/deposits`, `/asset-quality`.
- **Tier B — PageHeader + bespoke/relaxed body** (Section without index, or no Section, or custom
  viz): `/liquidity`, `/funds`, `/digital`, `/non-bank`, `/share-of-banking`, `/cross-bank`,
  `/ownership`, `/banks`, `/banks/[ticker]`, `/rates` (no Section), `/capital` & `/profitability`
  (sans `text-base` headings).
- **Tier C — off-system feed pages** (no `PageHeader`, sans `text-2xl` h1, raw pastel pills,
  `rounded-md/xl`): `/news`, `/news/google`, `/regulation`, `/earnings`, `/disclosures`.

### Drift dimensions (the concrete inconsistencies)

| Dimension | Standard | Where it drifts |
|---|---|---|
| **Section `index`** numbering | mono "01/02…" | used on **only 4/34** pages (`/`, credit, deposits, asset-quality); unused everywhere else |
| **Heading spine** | serif `Section` title | sans `text-base` (capital, profitability, regulation); sans `text-2xl` h1 (feed pages); no heading (rates) |
| **`PageHeader`** | masthead everywhere | **absent** on earnings, disclosures, regulation, news, news/google |
| **`eyebrow`** | mono terracotta kicker | present on ~10 pages, absent on the rest (no clear rule) |
| **Container width** | `max-w-[1440px]` | `max-w-5xl` (banks/[ticker], ownership, earnings), `max-w-4xl/3xl` (disclosures), `max-w-6xl` (admin) |
| **`<main>` spacing** | `space-y-8` | `space-y-6` (cross-bank, rates, news×2, pipeline, valuation); rates also mixes `mb-*` |
| **Active-toggle colour** | — | `bg-primary/10 text-primary` (banks/[ticker], BankSectionNav, ownership) **vs** `bg-accent` (cross-bank, PlSankey, HeatmapOverTime, NimComponents) |
| **Card radius** | `rounded-[10px]` | `rounded-lg` (heatmaps, ownership, pipeline, non-bank/economy tables), `rounded-md` (feed cards, inputs), `rounded-xl` (disclosures, statement toggles) |
| **Tables** | shared `Table` primitive | hand-rolled `<table>` on economy ×6, non-bank, capital league, cross-bank league, banks/[ticker] statements, valuation peers (Table used only on franchise, funds, admin-traffic, valuation-RI) |
| **Raw non-token colour** | semantic tokens | `news-tags.ts` pastels (regulation/news — **break dark mode**), RawFeeds hex borders, earnings indigo/emerald/amber, digital MOBILE/INTERNET, economy per-page hex, NimComponents palette |
| **Shadows** | none (flat) | drawers (`shadow-xl`/`2xl` on regulation, admin), pipeline nodes (`shadow-sm`), hover tooltips (`shadow-md`) |
| **Local formatters** | `chart-format.ts` `nf` | economy family + funds re-declare `nf`/`pct`/`bnTL` |
| **`Takeaway`** | narrative sector tabs | on 8 pages (`/`, credit, deposits, liquidity, asset-quality, capital, profitability, market-risk); correctly absent elsewhere |

---

## 4. Strengths & the distinctive point of view

- A **genuine, coherent identity** (editorial serif + mono-caps + warm palette) that separates the
  product from cookie-cutter dashboards — held rigorously at the token/type level.
- **"The Read"** — a deterministic-insight narrative layer most data sites don't have; always
  matches the charts because it's computed from the same D1 series.
- **Per-bank depth** (`/banks/[ticker]`): Yahoo-grade statements, Sankey P&L, diverging-bar
  repricing ladder, ownership bars — a real analytical product, not a chart dump.
- **Bespoke-but-on-palette data-viz**: heatmaps, the ownership force graph, the signed-stack NIM
  chart, the CAR league table — all draw from the chart theme, so they read as one family.
- **Theme system done right**: semantic tokens, dual themes, chart theming that survives Recharts'
  SVG-attribute limitation.

## 5. Chart craft vs the FT benchmark

The stated chart benchmark is [ft-visual-journalism/](ft-visual-journalism) (FT house style — *not*
a mandate to copy, a bar to measure against). Scoring the real charts (`TrendChart`,
`ChartCard`, `chart-theme.ts`) against its eight house-style principles:

| FT principle | Dashboard reality | Verdict |
|---|---|---|
| 1. **Title = the finding**, not the topic | Titles are topic+units ("Capital Adequacy Ratio (%) — by group"). The *finding* is stated at page level by **"The Read"**, never on the chart. | ✗ per-chart · ✓ at page |
| 2. Subtitle carries metadata | `ChartCard` has a `description` slot, but charts fold units into the title string and leave the slot empty. | ~ merged into title |
| 3. **Direct labelling** over legends | Draws an **end-dot** at each series' last point + emphasises Sector + hover/pin isolation — but still renders a **bottom legend** and no end-of-line *text* labels. | ~ partial |
| 4. **Annotate on the chart** (event bands, callouts) | Only `zeroLine`/`ReferenceLine`. No shaded bands, no pointer-note callouts. | ✗ |
| 5. Restraint: horizontal gridlines only, no axis line, no border | `TrendChart`: `CartesianGrid vertical={false}`, `axisLine={false} tickLine={false}` on both axes; card is the only frame. | ✓ strong |
| 6. Disciplined palette + one highlight vs greyed context | Muted palette ✓; Sector line is heavied + hover fades others to 0.18 ✓ — but at rest the 5 group lines are equal-weight → the "spaghetti" the critique flags. | ~ partial |
| 7. Source line at the bottom | `ChartCard source` footer exists but few charts pass it (economy folds source into the section description). | ~ under-used |
| 8. Static-first / "makes its point without hover" | Good nearest-series tooltip, but by-group legibility still leans on hover. | ~ partial |
| — Chart *selection* (Visual Vocabulary) | lines / bars / stacked / diverging / Sankey / heatmap / network — sits squarely in change-over-time · magnitude · ranking · deviation · part-to-whole · flow; no pies, no exotic forms. | ✓ on-vocabulary |
| — "House style as tooling" (the FastCharts insight) | `ChartCard` + `chart-theme.ts` + the shared wrappers enforce one chart look regardless of who built the page — the exact pattern FT gets from FastCharts/`g-chartframe`. | ✓ already embodied |

**Where it already meets FT:** gridline/axis restraint, muted palette, on-vocabulary chart choice,
and — structurally — *house-style-as-tooling* (the single most transferable FT lesson) is baked in.
**The three real gaps** — finding-as-title, direct end-of-line labels, and on-chart annotation —
are the same "at-rest legibility" theme the [critique](design-critique-2026-07-10.md) raises as
"spaghetti charts." All three design docs converge here: the charts are *clean* but don't yet
*argue* on their own; the argument currently lives one level up, in "The Read."

## 6. Gaps & design-pass candidates

Ordered by structural impact (composition-level; the *visual* levers — surface layering, spaghetti
charts, over-applied mono-caps — are in the companion [critique](design-critique-2026-07-10.md)):

1. **Bring the feed pages onto the system** — `/news`, `/news/google`, `/regulation`, `/earnings`,
   `/disclosures` all skip `PageHeader`/`Section`, use sans `text-2xl` h1s, and rely on **raw
   light-only pastel pills** (`news-tags.ts`) that break in dark mode. Biggest single consistency win.
2. **Decide the heading spine.** `Section` `index` numbering is on only 4/34 pages; `/capital` &
   `/profitability` abandoned `Section` for sans `text-base` headings. Either commit to numbered
   serif Sections everywhere or drop the index — right now it reads as half-migrated.
3. **Consolidate tables.** Economy (×6), non-bank, and others hand-roll the same
   `rounded-lg + bg-accent/40 header + text-negative cell` `<table>`; factor into `Table` (also fixes
   the 8px-vs-10px radius drift and the per-page formatter re-declaration).
4. **Pick one active-toggle treatment** (`bg-primary/10` vs `bg-accent`) and one card radius.
5. **Normalise container width & `space-y`** — the `1440/6xl/5xl/4xl/3xl` and `8/6` sprawl is mostly
   incidental, not intentional per-page.
6. **Separate brand terracotta from semantic red** so a red eyebrow and a red negative aren't the
   same hue (critique #6).

Nothing here is a bug (except the known blank-logo issue on `/banks`, critique #5) — it's a mature,
opinionated system whose main debt is **composition consistency**, not visual direction.
