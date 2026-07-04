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
| **2** | Real-terms convention (CPI-deflate helper + real twins) + decompositions (ROE equation, FX-adjusted credit growth) | **SHIPPED 2026-07-03** |
| **3** | Sized scenarios: NII sensitivity (±250/500bps × repricing ladder) + capital headroom (buffer drift + generation gap). Provision-need scenario MOVED to Phase 5 (needs the sector Stage-2 series first) | **SHIPPED 2026-07-03** |
| **4** | Share-shift columns on the /cross-bank league (Δpp y/y); bank-page rank-in-field strip + per-bank Capital section (CAR/CET1/buffer/AT1-reliance + ranks). Cross-bank CAR/CET1/LCR/NOP columns were ALREADY live (market-risk lane) | **SHIPPED 2026-07-03** |
| 4b | /banks league table w/ metric switcher + ownership-group cards; cross-bank 2–3-bank head-to-head picker (the mock's Compare) | deferred |
| **5** | Forward-credit layer on /asset-quality (sector Stage-2/Stage-3 shares + annual NPL formation-vs-exits + Stage-2 migration provision scenario, new `lib/credit-risk.ts`); Nav restructure (Sector in FSR order, Digital → Markets & Macro, /disclosures orphan → By Bank); rates transmission headline; ratios + funds clarify-purpose reframes | **SHIPPED 2026-07-03** |
| 5b | Chronology lane ("what changed": merged regulation + news + disclosures + rate decisions, tagged & dated); /digital 13→~4 chart compression | deferred |

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

## Phase-2 record (what changed, 2026-07-03)

- `web/app/lib/real-terms.ts` — `cpiYoYByMonth()` (TP.TUKFIY2025.GENEL levels →
  y/y map by 'YYYY-MM') + `nominalVsReal()` (exact Fisher deflation, NOT g−π).
  Honesty rule: weeks whose month has no published CPI are dropped from the
  real line (no nowcast) — the real twin can end ~6 weeks behind nominal.
- Credit §01: "nominal vs real" + "FX-adjusted (constant USD/TRY, 52w,
  TP.DK.USD.A)" loan-growth charts — the BBVA headline credit metric. FX book
  proxied all-USD (BDDK publishes TL-equivalent only; stated on the chart).
- Deposits §01: "nominal vs real" deposit-growth chart.
- Profitability: "The return equation" panel — ROA × leverage(assets/equity)
  ≈ ROE + NIM / fees-to-revenue / OPEX drivers, y/y DeltaBadges.
- Sector NIM bridge: NOT rebuilt — the existing NimComponentsSection already
  is the margin decomposition (income/expense buckets over avg assets).

## Phase-3 record (what changed, 2026-07-03)

- `market-risk.ts niiSensitivity()`: first-order one-year ΔNII from parallel
  shifts (−500/−250/+250/+500bps) off the latest sector repricing ladder —
  Σ gap_b × Δr × (1 − bucket midpoint), ≤1y buckets only; assumptions stated on
  the panel ("a sizing device, not a forecast"). Rendered as a Stat row on
  /market-risk.
- /capital "Headroom" panel: buffer over the 12% floor, 12-month drift (pp/yr),
  straight-line quarters-to-floor (or "buffer holding"), and the capital
  generation gap (equity y/y − assets y/y). No new queries beyond
  `totalAssetsYoY(sector)`.

## Phase-5 record (what changed, 2026-07-03)

- `web/app/lib/credit-risk.ts` — sector aggregation "of reporting banks" over
  `bank_audit_stages` (Stage-2/Stage-3 shares of gross loans, per-column
  both-fields-present guards, ≥5-bank floor) and `bank_audit_npl_movement`
  (annual Q4-YTD formation vs |collections|+|write-offs|+|sold| — Q4-only
  avoids de-cumulation assumptions on interim YTD flows).
- /asset-quality §02 "The forward indicators": staging chart + roll-forward
  chart + the Stage-2→3 migration provision scenario (5/10/20% at current
  cov3 − cov2, ₺bn and % of ECL stock, assumptions stated). Stage-2 share
  feeds the tab Read (`assetQualityInsights` optional `stage2` input).
- Nav: Sector group re-ordered to the FSR story (Credit → Deposits →
  Liquidity → Asset Quality → Capital → Profitability); Digital relocated to
  Markets & Macro; `/disclosures` added under By Bank (orphan fixed).
- /rates: transmission chart promoted next to the corridor and retitled
  ("policy cuts reach deposit pricing first").
- Table-15 by-bank-type scorecard + /funds: purpose stated explicitly in the
  header (deposit-substitution channel). The scorecard was later folded into
  Overview as the "Ratios by bank type" section (2026-07-04); /sector/ratios
  retired.

**Known follow-ups:** rationale.json still describes the pre-Phase-1 chart
inventory (re-run the audit after Phase 5); the mock's Liquidity deletion is
REJECTED (tab stays); Reads are deterministic-only by owner decision.
