# Display study — the strategist / C-level lens

Companion to the [sector-story spine](sector-story-spine.md) (framework) and the
[dashboard audit](dashboard-audit.md) (analyst-audience snapshot, 2026-06-27).
This study re-judges *what each page displays* for a second audience the owner
named on 2026-07-02: **a strategist / C-level bank manager**. It is the build
spec for the "editorial IA" phases; the Opus design mockups
(`data/external_reports/Website design revision-editorial.zip`) are its visual
reference, amended per the review below.

## The finding

The dashboard **measures everything and concludes almost nothing**: ~215
display units whose dominant form is the single-metric time series by ownership
group. A strategist consumes *answered questions*, not metrics. ~90% of the fix
is **re-display of data already in D1** (margin engine, npl_movement, stages,
CET1, LCR, FX position, repricing, market share, BIST) — not new extraction.

## The six standing questions

Every display unit must serve one; anything serving none is reference and goes
behind a fold.

| Q | Standing question | Home |
|---|---|---|
| Q1 | What changed, and does it matter? | Overview + per-tab Reads |
| Q2 | Where is the margin cycle going? | Rates → Profitability → Market Risk |
| Q3 | Where is risk building — can we absorb it? | Asset Quality + Capital + Liquidity |
| Q4 | Who is winning, and why? | Banks / Compare / bank pages |
| Q5 | Where is the money going? | Deposits + Funds + Non-Bank |
| Q6 | What rules & events must we react to? | Regulation + News + Disclosures (→ one chronology) |

## The five display-unit swaps

1. **Judgment first** — a deterministic "The Read" (insights.ts; owner decision:
   NO LLM, no hand-written prose) leads every T0/T1 tab: level + delta + rank +
   watch flag.
2. **Growth absorbs level** — level charts die; the level moves to captions /
   Overview KPIs. Every nominal series gets a real (CPI-deflated) twin as a
   sitewide convention.
3. **Decomposition replaces parallel series** — ROE driver tree (margin × fees ×
   cost × risk × leverage), sector NIM bridge (loan yield vs deposit cost),
   deposit growth split volume/FX-valuation/remix.
4. **Dispersion + sizing replace exhaustive lines + raw exposure** — median/IQR
   with named outliers; repricing gap × rate scenarios = NII sensitivity in ₺;
   Stage-2 × coverage = provision need; CAR buffer ÷ RWA growth = headroom.
5. **Share shift replaces static league** — Δpp market share YoY per bank
   (market-share.ts), not just size.

## Phase plan & status

| Phase | Scope | Status |
|---|---|---|
| **1** | Reads on all T1 tabs (credit, deposits, asset-quality, capital, profitability, liquidity, market-risk) + audit-flagged reorders (credit pub/priv ↑, deposits dollarization ↑, profitability real-ROE ↑, capital CET1 ↑) + dedups (level twins, deposits sector-YoY dup, fee-ratio trio → 1, liquidity TL-deposit-growth dups) + retire `/sector` orphan (redirect → `/`) | **SHIPPED 2026-07-02** |
| 2 | Real-terms convention (CPI-deflate helper + real twins) + decompositions (sector NIM bridge, ROE tree, FX-adjusted credit impulse) | pending |
| 3 | Sized scenarios: NII sensitivity (±100/250/500bps × repricing), provision-need (Stage-2 migration), capital headroom (buffer vs RWA growth) | pending |
| 4 | Share-shift leagues; bank-page rank-in-field strip + Capital/Liquidity sections; /banks league table; cross-bank CAR/CET1/LCR columns + head-to-head picker | pending |
| 5 | Structural: fold `/sector/ratios`; relocate+compress /digital; chronology lane (regulation+news+disclosures); rates transmission headline; funds/non-bank reframe; sector Stage-2 + NPL-formation headline (npl_movement) | pending |

Already closed before this study (post-audit, keep): sector CET1/Tier-1 on
/capital and sector LCR/NSFR on /liquidity (both via `web/app/lib/audit-ratios.ts`),
Market Risk tab (S8), Overview re-curation + Sector Pulse.

## Phase-1 record (what changed, 2026-07-02)

- `web/app/lib/insights.ts` — 7 new per-tab generators (`creditInsights`,
  `depositsInsights`, `assetQualityInsights`, `capitalInsights`,
  `profitabilityInsights`, `liquidityInsights`, `marketRiskInsights`) + widened
  `SeriesPoint` input type + `deltaOver`/`growthOver` helpers. All thresholds
  explicit; tone conservative; pages pass PRE-FILTERED single series.
- Every T1 tab renders `<Takeaway>` ("The Read") directly under its PageHeader.
- Credit: pub/priv + TL/FX promoted to section 02; loans/TL/FX level charts cut.
- Deposits: Dollarization promoted to section 02 (canonical sector home; the
  public/private split stays on Liquidity); demand-level + sector-YoY dup +
  TL/FX level charts cut; loans-YoY fetched for the funding-gap read.
- Profitability: Real Returns promoted to section 2; fee-ratio trio → 1
  (kept Fees/Revenue; cut NII/NIE and Fees/OPEX charts + their fetches).
- Capital: audited CET1 section promoted to position 2.
- Liquidity: two TL-deposit-growth charts cut (Deposits owns deposit growth).
- `/sector` root → `redirect("/")`; `TotalAssetsChart.tsx` deleted.
- Net: ~14 charts removed, 0 data loss (all cuts were level-twins or dups).

**Known follow-ups:** rationale.json still describes the pre-Phase-1 chart
inventory (re-run the audit after Phase 5); the mock's Liquidity deletion is
REJECTED (tab stays); Reads are deterministic-only by owner decision.
