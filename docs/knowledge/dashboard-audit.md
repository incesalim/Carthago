# Dashboard audit — 2026-06-27

A dated snapshot: the current Carthago dashboard scored against the
[sector-story spine](sector-story-spine.md). The framework is stable; this audit
is a re-runnable snapshot. Structured per-tab / per-chart verdicts live in
`data/dashboard_rationale/rationale.json`.

> **Scope:** strategy + audit only. **No dashboard code was changed.** These are
> recommendations to decide on, not edits made.

## Method (read-only, repeatable)

1. **Tabs** enumerated from `web/app/components/Nav.tsx` (canonical) and
   cross-checked against the 31 `web/app/**/page.tsx` files.
2. **Charts** enumerated per page top-to-bottom (= scroll order): 215 visuals
   across 31 routes (charts, KPI cards, tables, bespoke viz).
3. **Reconciled** against `web/app/lib/chart-specs.catalog.json` (22 specs,
   `placement` field) and `data/metric_knowledge/registry.json` (162 metric ids).
4. **Scored** with the spine's 7-criterion rubric → class + verdict.

**Scorecard:** 31 tabs (T0:1 · T1:6 · T2:5 · T3:12 · T4:7) · 215 charts
(headline 25 · supporting 112 · depth 76 · cut-candidate 2). Tab verdicts: keep
20 · reorder 2 · add_missing 4 · merge 2 · clarify_purpose 1 · relocate 1 ·
add_to_nav 1.

**Headline:** the dashboard is **comprehensive and the analytics are sound** —
the issues are *editorial* (ordering, redundancy, one structural gap, two orphan
pages), not data-quality. This is a well-built library that has never had a
librarian.

---

## Findings — five buckets

### 1. Gaps vs the spine (the most important bucket)

| Gap | Where | Detail |
|---|---|---|
| **CAMELS "S" (Sensitivity) is unhomed** | no tab (spine S8) | No FX net open position, no interest-rate repricing/duration gap. The standard market-risk lens for a dollarized system is absent. Symptom: an "Off-BS derivatives / total assets" chart hides under *Capital*; FX dollarization is scattered on *Liquidity*. Ties directly to `data-gaps-roadmap.md` Tier B (`fx_net_open_position`, `repricing_gap`). |
| **Liquidity tab has no LCR / NSFR** | Liquidity (S4) | The two standard Basel liquidity ratios — the FSI-core liquidity indicators — are absent at sector level. They exist per-bank in `bank_audit_liquidity`. A "Liquidity" tab with no liquidity-coverage ratio. |
| **Capital tab has no CET1 / Tier-1 series** | Capital (S6) | Shows total CAR only (monthly bulletin carries only item 30). CET1 is the Basel headline and the BBVA capital lead; per-bank CET1 exists in `bank_audit_capital`. |
| **Asset Quality has no Stage-2 / restructured series** | Asset Quality (S5) | The forward-looking credit-stress lens (SICR migration, restructured loans) — BBVA's "financial stress" angle — is missing at sector level. Per-bank Stage 2 exists in `bank_audit_stages`. |
| **No FX-adjusted loan growth** | Credit (S2) | BBVA's headline credit metric is 13-week FX-adjusted annualized growth; we show nominal m/m + 4w-annualized only. |
| **Per-bank Capital & Liquidity sections thin** | Bank detail (S10) | The per-bank page is rich on Earnings (performance/margins) but has no Capital (CET1/CAR) or Liquidity (LCR) section, though the audit lane holds both. The cross-bank heatmap likewise lacks a CAR/CET1 column. |

### 2. Redundancies

| Redundancy | Detail | Suggested action |
|---|---|---|
| **Dollarization shown twice** | "FX share of deposits" on *Deposits* and "Deposit dollarization" on *Liquidity*. | One canonical dollarization chart; cross-link the other. |
| **LDR shown three times** | *Overview* KPI, *Deposits* "LDR by group", *Liquidity* TL/FC LDR. | Assign one canonical home (Liquidity), reference elsewhere. |
| **Sector deposit-YoY duplicated** | *Deposits* chart 9 (sector-only YoY) duplicates chart 2 (by-group YoY already includes the sector line). | cut/merge. |
| **Profitability fee-ratio trio** | Fees/Revenue, Non-interest income/expense, Fees/OPEX — three overlapping cost-coverage cuts. | Keep one headline, fold the rest to depth. |
| **TL deposit growth on Liquidity** | Two TL-deposit-growth charts on *Liquidity* overlap *Deposits*. | Reference, don't repeat. |
| **Total Assets level duplicated** | *Overview* "Total Assets — Level" == the entire `/sector` root page. | Fold (see orphans). |

### 3. Mis-ordering (priority ≠ position)

| Tab | Issue |
|---|---|
| **Credit** | "Total Credit YoY — Public vs Private" — its own caption calls it "the clearest sector signal" — sits **14th**, in section 5. BBVA's lead divergence. Promote toward the top. TL/FX split likewise. |
| **Deposits** | Dollarization (FX share) is the BBVA deposit headline but sits **12th** (section 3). Promote. |
| **Profitability** | Real-ROE (ROE vs CPI) is a BBVA-grade lens but lands last; consider promoting above the fee ratios. |

### 4. Orphans (render but unplaced)

| Orphan | Detail | Action |
|---|---|---|
| **`/disclosures`** | Real KAP-feed page, **not in Nav** — reachable only via `/banks` links or direct URL. Undiscoverable. | add_to_nav (under News or By Bank) or fold into News. |
| **`/sector` (root)** | Real single-chart Total-Assets page, **not in Nav**, duplicates Overview. The `/sector/ratios` child *is* linked; the root dangles. | merge into Overview / remove. |
| **Catalog spec `rates.cbrt_foreign_asset_share`** | Defined in `chart-specs.catalog.json` (placement tab `rates`, "CBRT Balance Sheet") but **not rendered** on `/rates`. | Build the chart or drop the spec — a catalog/UI drift. |
| **"Off-BS derivatives / total assets"** | Lives under *Capital* but is a market-risk (S8) signal. | Relocate once S8 has a home. |

### 5. Unclear-purpose tabs

| Tab | Issue | Action |
|---|---|---|
| **Ratios (`/sector/ratios`)** | Six KPI cards overlapping Overview + Profitability; its ONLY distinct value is the bank-**type** filter. | clarify_purpose: reframe explicitly as the *by-bank-type Table-15 scorecard*, or fold into Overview/Profitability with a type switch. |
| **Digital nav placement** | Strong TBB lane, but grouped under "Sector" between Profitability and Liquidity — it's structural context, not a CAMELS vital. | relocate to a structure/context group with Funds/Non-Bank. |
| **Funds / Non-Bank banking-anchor** | Adjacency tabs whose link to *banking* (deposit substitution, disintermediation) is implicit. | Make the banking anchor explicit so each earns its place. |

---

## Prioritized recommendations

> Decisions for the owner. None executed this round.

### P0 — structural ✅ RESOLVED 2026-06-27
- **CAMELS "S" now has a home.** New **Market Risk** tab (spine S8, Markets &
  Macro group) off two new deterministic §4 extractors —
  `bank_audit_fx_position` (FX net open position, ~99% coverage) and
  `bank_audit_repricing` (interest-rate repricing gap, ~81% — participation
  banks omit it, validated N/A) — plus securities mark-to-market reused from
  `bank_audit_oci`/BS. Closes the `data-gaps-roadmap.md` Tier-B items (now Tier
  A.2). *Rollout remaining: full-history CI backfill, dashboard surfacing
  (tab + per-bank section + heatmap columns), deploy.*

### P1 — completeness & comparability (FSI-core gaps)
- **Surface sector LCR / NSFR** on Liquidity (data exists per-bank).
- **Surface sector CET1 / Tier-1** on Capital (data exists per-bank).
- **Add a sector Stage-2 / restructured-loan series** to Asset Quality.
- **Reframe Ratios** as the explicit by-bank-type regulatory scorecard, or fold it.
- **Resolve the two orphan pages** (`/disclosures` → nav; `/sector` root → merge).

### P2 — editorial polish
- **Reorder** Credit (public/private + FX/TL to the top) and Deposits
  (dollarization to the top) to match BBVA emphasis.
- **Consolidate** the Profitability fee-ratio trio and the Deposits/Liquidity
  dollarization & LDR duplications.
- **Add FX-adjusted loan growth** to Credit; promote real-ROE on Profitability.
- **Relocate** Digital into a structure/context nav group; **drop or build** the
  dangling `rates.cbrt_foreign_asset_share` catalog spec.

---

## What is strong (keep, and use as models)

- **`/cross-bank`** is the best comparability surface in the app and the de-facto
  per-bank FSI core set (heatmap snapshot + over-time + HHI/league). Extend it
  with CAR/CET1 once the per-bank capital lane is surfaced.
- **`/economy`** is the narrative model: multi-sentence section descriptions with
  report-page citations. The future narrative layer should match this voice.
- **`/regulation`** is the existing narrative *mechanism*: a weekly LLM briefing
  read from `regulation_briefings` with no LLM on page load — the reusable
  pattern.
- **`/banks/[ticker]`** is the most complete single surface (profile, valuation,
  margin/return performance, three statements + Sankey, ownership, disclosures).

## Balance observation

The **macro lane is deeper than the banking lanes it contextualizes**: the
Economy hub + 5 sub-pages reproduce external macro reports chart-for-chart
(catalog-backed), while the core CAMELS tabs have the FSI-core gaps above
(LCR/NSFR, CET1, Stage 2, market risk). Not a defect — but for a
*banking-sector* dashboard aimed at analysts, the next editorial investment
should tilt from macro reproduction toward closing the banking-side spine gaps.

---

*Re-run this audit by repeating the method against `Nav.tsx` + the `page.tsx`
tree and re-scoring with the rubric in [`sector-story-spine.md`](sector-story-spine.md) §5.*
