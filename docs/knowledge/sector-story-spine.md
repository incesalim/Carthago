# The sector-story spine — dashboard editorial rationale

The "why" layer for the Carthago dashboard. It states, for every tab, the one
analyst question it answers, where it sits in the story, and how much editorial
weight it carries; and for every chart, the role it plays. This is the foundation
the owner asked for before any narrative is added — so the dashboard *tells a
story* by design instead of accreting charts (and later, prose) into an
undisciplined pile.

> **Audience:** professional banking/finance analysts — optimize for
> completeness, rigor, methodology transparency, and peer/standard
> comparability, not for teaching basics.
>
> **Grounded in** (adapted, not invented): CAMELS · CBRT/IMF Financial Stability
> Report (FSR) ordering · IMF Financial Soundness Indicators (FSIs) · the
> Garanti-BBVA monthly *Banking Sector Outlook*.

## The three files of this layer

| File | Role |
|---|---|
| `docs/knowledge/sector-story-spine.md` (this) | The **stable framework**: spine, tiers, rubric, tab rationale. |
| `docs/knowledge/dashboard-audit.md` | A **dated audit** of the current dashboard against the spine (findings + P0/P1/P2). Re-runnable; the framework stays put. |
| `data/dashboard_rationale/rationale.json` (+ `schema.json`) | The **machine-usable** form: every tab + every chart with role, priority, mappings, and audit verdict. Cross-checked (metric ids → `metric_knowledge/registry.json`, routes → `Nav.tsx`, catalog ids → `chart-specs.catalog.json`). The third vertex of the knowledge triangle. |

This closes a triangle the project half-built: **registry.json** (what each metric
*is*) ↔ **chart-specs.catalog.json** (which charts are *reproduced*) ↔
**rationale.json** (what each chart is *for*).

---

## 1. The four authorities — each does a distinct job

They are complementary, not averaged. Each answers a different question:

- **CAMELS** — the *completeness checklist*. Capital, Asset quality, Management,
  Earnings, Liquidity, Sensitivity to market risk. Proves no vital is missing.
- **CBRT/IMF FSR** — the *narrative ordering*. Macro → credit → funding/liquidity
  → asset quality → solvency → profitability → market risk → outlook.
  A chart-level reproducibility map of the FSR 2026-I edition lives in
  [`external-reports/cbrt-fsr-2026-1-chart-inventory.md`](external-reports/cbrt-fsr-2026-1-chart-inventory.md).
- **IMF FSIs** — the *comparability standard*. Fixes *which exact ratios* are
  internationally peer-comparable (regulatory capital/RWA, NPL/gross loans, NPL
  net of provisions/capital, ROA, ROE, interest margin/gross income,
  non-interest expense/gross income, liquid assets/total assets and /short-term
  liabilities, net open FX position/capital). Directly serves the analyst
  audience's demand for standardized numbers.
- **BBVA monthly outlook** — the *Türkiye-specific emphasis & cadence*. What a
  recurring TR sector note actually leads with: TL/FC loan growth, deposits &
  dollarization, net CBRT funding, cost of risk, real ROE, CAR.

> **Spine = FSR ordering as the backbone, CAMELS as the completeness audit over
> it, FSIs as the per-theme metric standard, BBVA as the local weighting.**

## 2. Two orthogonal axes (the key design decision)

Most IA confusion comes from conflating *where a theme sits in the story* with
*how much editorial weight it deserves*. Keep them separate:

- **Story sequence (S0…S15)** — reading order in the arc (macro first, ops last).
- **Priority tier (T0…T4)** — editorial investment / essentiality, independent of
  position.

> Economy opens the story (S0) but is only **T3** context an analyst mostly
> owns. Overview is **S1** but **T0** — the single most load-bearing tab. "Order
> = importance" would wrongly demote Overview behind Economy. It doesn't.

### Priority tiers

| Tier | Meaning | Tabs |
|---|---|---|
| **T0** | Headline — the executive answer to "how is the sector doing?" | Overview |
| **T1** | Core CAMELS spine — the irreducible analyst sequence; heaviest editorial investment | Credit, Deposits, Liquidity, Asset Quality, Capital, Profitability *(+ the unhomed Sensitivity)* |
| **T2** | Applied / comparative — turns the sector view into named, actionable comparison | Ratios, Banks, Compare, Valuation |
| **T3** | Context / structure — drivers and adjacency | Economy (+5 sub-pages), Rates, Ownership, Non-Bank (+share), Funds, Digital |
| **T4** | Reference / ops — outside the analytic narrative but valued for transparency | Regulation, News (+google), Disclosures, Pipeline, Admin |

## 3. The spine (master mapping)

| S# | Theme | Tab(s) | Tier | CAMELS | FSR chapter | IMF FSI (core unless noted) | BBVA section |
|---|---|---|---|---|---|---|---|
| S0 | Macro & policy backdrop | Economy (+Rates) | T3 | — | Macro-financial environment | (macro context) | Macro/policy snapshot |
| S1 | Sector headline — size & growth | **Overview** | **T0** | all | Overview/summary | digest of core set | Headline dashboard |
| S2 | Credit / asset growth | Credit | T1 | A | Credit developments | sectoral loan distribution; credit growth (enc.) | Loan growth (TL/FC, retail/comm.) |
| S3 | Funding & deposits | Deposits | T1 | L | Funding structure | deposits/funding; FX share | Deposits & dollarization |
| S4 | Liquidity | Liquidity | T1 | L | Liquidity | liquid assets/total assets; /ST liabilities | FX, reserves, net CBRT funding |
| S5 | Asset quality / credit risk | Asset Quality | T1 | A | Credit risk | NPL/gross loans; NPL net of prov./capital; provisions/NPL | Asset quality (NPL, Stage 2, CoR) |
| S6 | Capital / solvency | Capital | T1 | C | Solvency | reg. capital/RWA; CET1/RWA; leverage (enc.) | CAR |
| S7 | Profitability / earnings | Profitability | T1 | E (+M) | Profitability | ROA; ROE; int. margin/gross income; non-int. exp./gross income | NIM, real ROE, fees |
| **S8** | **Sensitivity to market risk** | **— (unhomed)** | T1 | **S** | Market/FX/rate risk | net open FX position/capital; duration (enc.) | FX sensitivity, securities MtM |
| S9 | CAMELS scorecard / ratios | Ratios (`/sector/ratios`) | T2 | all | (cross-cutting) | the core set as one surface | (Table-15 recap) |
| S10 | Bank-level comparison | Banks, Bank detail, Compare | T2 | per-bank | Dispersion & concentration | per-bank core set; HHI | (peer tables) |
| S11 | Valuation | Valuation | T2 | — | Market discipline | (market data) | (valuation context) |
| S12 | Ownership & governance | Ownership | T3 | M (proxy) | Structure/governance | (structural) | (ownership) |
| S13 | Structural / adjacent | Non-Bank (+share), Funds, Digital | T3 | — | NBFI interconnections | (NBFI; structural) | (sector structure) |
| S14 | Rules & catalysts | Regulation, News (+google), Disclosures | T3/T4 | — | Policy/outlook | — | Regulation/outlook |
| S15 | Provenance / ops | Pipeline, Admin | T4 | — | Methodology | — | — |

**The single highest-value structural finding:** CAMELS **"S" (Sensitivity to
market risk) has no home (S8).** FX net open position and interest-rate
repricing/duration gap — the standard market-risk lenses for a dollarized
banking system — are not a tab. They are exactly the Tier-B groundwork already
scoped in [`data-gaps-roadmap.md`](data-gaps-roadmap.md)
(`fx_net_open_position`, `repricing_gap`). The spine both *names* the gap and
*connects it to work already planned*. See the audit (P0).

## 4. Tab-by-tab rationale (summary)

The single guiding question per tab — the test being "if it needs two sentences,
the tab is doing two jobs." Full fields (takeaway, FSI/CAMELS mapping,
dependencies, known gaps, per-chart roles, narrative hook) live in
`data/dashboard_rationale/rationale.json`.

### Sector (the CAMELS spine)
| Tab | S# · Tier | Guiding question | Verdict |
|---|---|---|---|
| Overview `/` | S1 · **T0** | How is the sector doing right now — size, growth, headline vitals? | keep (narrative home) |
| Credit | S2 · T1 | How fast is credit growing, in what currency, to whom — and public vs private? | reorder |
| Deposits | S3 · T1 | Where is funding coming from — growing, sticky, dollarizing? | reorder |
| Asset Quality | S5 · T1 | Is the credit actually good — and where is deterioration concentrated? | add_missing (Stage 2) |
| Capital | S6 · T1 | Can the sector absorb losses — capital over the minimum, and why moving? | add_missing (CET1) |
| Profitability | S7 · T1 | Is the sector earning its cost of capital — and what drives the margin? | merge (fee ratios) |
| Ratios `/sector/ratios` | S9 · T2 | What does the official ratio scorecard look like per bank-type? | clarify_purpose |
| Liquidity | S4 · T1 | Can the sector fund itself — TL/FC pressure, dollarization, CBRT backdrop? | add_missing (LCR/NSFR) |
| Digital | S13 · T3 | How fast is banking migrating to digital channels? | relocate (nav group) |

### By Bank
| Tab | S# · Tier | Guiding question | Verdict |
|---|---|---|---|
| Banks `/banks` | S10 · T2 | Which banks exist, how big, where to drill in? | keep (directory) |
| Bank detail `/banks/[ticker]` | S10 · T2 | For this bank: how does it perform, how built, who owns it? | add_missing (C/L sections) |
| Compare `/cross-bank` | S10 · T2 | How does each bank rank vs peers across the full set? | keep (best comparability surface) |
| Valuation | S11 · T2 | Are the listed banks cheap or expensive vs fundamentals? | keep |
| Ownership | S12 · T3 | Who owns the banks and where do ownership webs connect them? | keep (CAMELS-M proxy) |

### Markets & Macro
| Tab | S# · Tier | Guiding question | Verdict |
|---|---|---|---|
| Rates | S0 · T3 | What monetary-policy / rate backdrop do banks operate against? | keep |
| Funds | S13 · T3 | How much savings migrated into funds, and what do they hold? | keep |
| Non-Bank (+share) | S13 · T3 | How big are non-bank lenders / how much credit is disintermediated? | keep |
| Economy (hub +5) | S0 · T3 | What macro backdrop are the banks operating in? | keep (**the narrative model**) |

### More (reference / ops)
| Tab | S# · Tier | Guiding question | Verdict |
|---|---|---|---|
| Regulation | S14 · T4 | What macroprudential rules are in force / changed? | keep (**narrative precedent**) |
| News (+google) | S14 · T4 | What's the press/long-tail saying? | keep |
| Disclosures `/disclosures` | S14 · T4 | What have listed banks filed on KAP? | **add_to_nav** (orphaned) |
| Pipeline | S15 · T4 | Where does each number come from, how fresh? | keep |
| Admin | S15 · T4 | (ops) Is the pipeline healthy? | keep |
| `/sector` (root) | S1 · T4 | (unclear) sector total-assets over time | **merge** (orphan, dup of Overview) |

## 5. Within-tab chart-priority rubric

Score each chart 0/1/2 on seven criteria; criterion 1 dominates.

1. **Question-fit** *(dominant)* — does it answer the tab's guiding question at a glance?
2. **Standard-view** — is it the canonical analyst view (FSR/BBVA/peer) or a bespoke cut?
3. **Comparable & reproducible** — from registry: `standard_across_banks` true AND `reproducible` direct/derived? Non-standard metrics (franchise, ESG, bank-defined) cap at supporting/depth + a caveat.
4. **Decision-relevance** — does it change an analyst's read (signal) or just confirm/decorate?
5. **Non-redundancy** — does it show something no other chart (this tab or a sibling) shows?
6. **Scroll-position earned** (bool) — headline above the fold; depth below.
7. **Sourced** (bool) — cited authoritative source (BDDK table / EVDS code / audit line / catalog `verify`)?

**Class:**
- **Headline** — question-fit 2 ∧ standard 2 ∧ comparable 2 ∧ decision 2. ≤2 per tab, top of page.
- **Supporting** — adds a needed dimension (breakdown / peer split / driver).
- **Depth** — granular expert cut; low question-fit, high rigor value; below the fold.
- **Cut-candidate** — question-fit 0 ∧ non-redundant 0, or decoration + redundant.
- **Orphan** (flag) — renders but no spine theme owns it, or no registry metric, or no source.

## 6. Validating the spine

A spine is "correct" when all four checks pass:
1. **CAMELS completeness** — every letter C/A/M/E/L/S maps to ≥1 tab. *Today: S is unhomed (P0); M is an external proxy via Ownership.*
2. **FSI coverage** — every IMF FSI *core* indicator maps to a tab + a registry metric. *Today: LCR/NSFR and net-open-FX-position have no sector surface (P1).*
3. **FSR order preserved** — story sequence S0…S8 matches the FSR chapter flow. *Holds.*
4. **BBVA emphasis reflected** — BBVA's lead themes (loan growth, dollarization, net CBRT funding, CoR, real ROE) are T0/T1 and high in their tabs. *Partly: dollarization & public/private growth sit too low in their tabs (reorder).*

## 7. Maintenance — re-running the audit

The audit is read-only and repeatable (see `dashboard-audit.md` §method):
enumerate tabs from `Nav.tsx`; enumerate charts per `page.tsx` (top-to-bottom =
scroll order); reconcile against `chart-specs.catalog.json` (`placement`) and
`metric_knowledge/registry.json`; score with §5; emit findings. A future
`scripts/dashboard_rationale.py --validate` (mirror of
`scripts/metric_knowledge.py`) could assert every `route` exists in `Nav.tsx`,
every `metric_ids` resolves in the registry, and every `catalog_spec_id` resolves
in the catalog — **reserved, not built this round.**

## 8. The seam to a future narrative layer (out of scope now)

The narrative layer renders **nothing** this round. The hooks are already in the
data: `guiding_question`, `analyst_takeaway`, and `future_narrative_hook` per tab.
The dashboard already renders `<Section description>` strings (richest on
`/economy`, with report-page citations) and `/regulation` already renders a
weekly LLM briefing from `regulation_briefings` with *no LLM on page load*. A
later phase would populate per-tab takeaways/callouts **from** the rationale
file — but only after the audit confirms each chart earns its slot. Holding the
intended takeaway as inert structured data now is exactly what prevents "piling
narrative like graphs."
