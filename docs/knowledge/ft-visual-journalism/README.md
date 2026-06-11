# FT visual journalism — chart-design reference point

How the **Financial Times** makes charts: their team, tooling, chart-selection taxonomy, and house
style. Kept as a **design reference point** for our dashboard's charts — a benchmark for what
"professional" financial data visualisation looks like, not a mandate to copy it.

> ⚠️ **This is NOT a data source for any dashboard.** Nothing here feeds `data/`, D1, or R2. It's
> background reading for chart-design discussions, same role as the other folders under
> [`docs/knowledge/`](../).

**Links verified to resolve on 2026-06-11.** Legend: 🟢 free/verified · 🌐 live but blocks automated
checks (opens normally in a browser) · ❓ could not verify.

---

## 1. Who makes FT charts, and with what

- **Visual & Data Journalism team** — long led by **Alan Smith** (author of the *Chart Doctor*
  column); **John Burn-Murdoch** is the best-known practitioner (his COVID trajectory charts ran
  in this style).
- **Bespoke interactives** are hand-built in **D3.js**; Burn-Murdoch prototypes heavily in
  **R/ggplot2**.
- **Routine charts** come from **FastCharts**, an internal browser tool that lets any reporter
  produce an on-brand chart in minutes without code.
- The key insight: FT quality is **not one charting library** — it's a *house style enforced by
  tooling*. Templates and frame components (`g-chartframe`) bake in the title/subtitle/source
  structure and styling, so every chart looks FT regardless of who made it.

## 2. The Visual Vocabulary — relationship-first chart selection

FT's open-sourced chart-selection taxonomy. Pick the **relationship in the data first**, then the
chart form. Nine categories:

| Relationship | Typical FT forms |
|---|---|
| Change over time | line, column, slope, area, fan |
| Magnitude | column, bar, paired bar |
| Ranking | ordered bar/column, slope, lollipop, bump |
| Deviation | diverging bar, spine, surplus/deficit line |
| Distribution | histogram, dot plot, boxplot, beeswarm |
| Part-to-whole | stacked column, waterfall, treemap (pies rare) |
| Correlation | scatter, connected scatter, bubble |
| Spatial | choropleth, proportional symbol |
| Flow | sankey, chord, network |

Deliberately a **small vocabulary** — mostly lines, bars, dots; very few pies, no exotic forms.
Our dashboard's needs sit almost entirely in *change over time*, *magnitude*, *ranking*, and
*deviation*.

## 3. House-style principles (the part worth stealing)

1. **Title states the finding, not the topic.** "Turkish banks' margins are recovering", not
   "Net interest margin, 2022–2026". The chart is an argument; the title is its thesis.
2. **Subtitle carries the metadata** — measure, units, period (e.g. "Net interest margin, %,
   quarterly"). Frees the title to editorialise.
3. **Direct labelling instead of legends** — series names sit at the end of each line, in the
   line's colour. No legend box to cross-reference.
4. **Annotate on the chart** — shaded recession/event bands, short notes with thin pointer lines,
   the interesting data point called out. The reader shouldn't have to hover to get the point.
5. **Restraint everywhere else** — horizontal gridlines only; no y-axis line; no chart border;
   no chartjunk. The data ink dominates.
6. **Disciplined palette** — a few muted colours (FT's dark blue, burgundy, teal) on the signature
   paper-pink background (`#FFF1E5`); one highlight colour against greyed-out context series.
7. **Source line at the bottom** of every chart ("Source: …"), plus author credit.
8. **Static-first** — they'd rather annotate well than add interactivity; tooltips are a fallback,
   not the message.

## 4. Links

### Open-source / GitHub
- **chart-doctor repo** (sample files for the Chart Doctor column; MIT code, FT-copyright content) 🟢
  - https://github.com/Financial-Times/chart-doctor
- **Visual Vocabulary poster** (EN/DE/ES/FR/JP/CN PDFs + poster.png + schools edition) 🟢
  - https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary
- **Visual Vocabulary interactive site** (web version of the poster) 🟢🌐
  - https://ft-interactive.github.io/visual-vocabulary/
- **g-chartframe** (D3 frame component: web/print/social/video frames with FT title/subtitle/source
  structure baked in — the "house style as tooling" pattern) 🟢
  - https://github.com/ft-interactive/g-chartframe

### FT pages (bot-blocked, open in a browser)
- **Chart Doctor column** (Alan Smith's series on chart craft) 🌐 — https://www.ft.com/chart-doctor
- **Origami** (FT's design system — components, typography, the colour palette) 🌐
  - https://origami.ft.com/

### Unverified
- **FastCharts** ❓ — https://fastcharts.io refused connections on 2026-06-11; the public instance
  may have been retired. The concept (template tool enforcing house style) is the durable lesson.

## 5. What applies to our dashboard (Recharts mapping)

No library change needed — the style is mostly defaults discipline inside `web/app/components/ui/chart-card.tsx`:

**Cheap wins (plain Recharts props/config):**
- Finding-as-title + metadata subtitle → `chart-card` header convention.
- Horizontal-only gridlines (`CartesianGrid vertical={false}`), no y-axis line
  (`axisLine={false} tickLine={false}`).
- Consistent number/date formatting and a restrained, fixed series palette.
- Source line ("Source: BDDK/TBB/EVDS") in the card footer.

**Awkward in Recharts (needs custom SVG via `<Customized>` or label components):**
- Direct end-of-line series labels with **collision handling** when lines end close together.
- Free-form annotations with pointer lines (event markers beyond simple `ReferenceLine`/`ReferenceArea`).

**Explicitly not adopted (for now):** the paper-pink background (we have our own theme), FT fonts
(Metric/Financier are proprietary), static-first (a dashboard is interactive by nature — but the
"chart should make its point without hover" test still applies).

---

## Maintenance notes

- Verified 2026-06-11. GitHub links are stable; ft.com links are paywalled/bot-blocked but live.
- If FastCharts resurfaces (or FT Labs publishes a successor), update §4.
- If we later add other style references (The Economist, Datawrapper, Urban Institute), give each
  its own folder under `docs/knowledge/` rather than growing this one.
