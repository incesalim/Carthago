# Strategic Review — 2026-07-05

A high-altitude, whole-project assessment (a deliberate zoom-*out* from the
granular self-audits: [dashboard-audit.md](dashboard-audit.md),
[display-study.md](display-study.md),
[architecture-review-2026-07.md](architecture-review-2026-07.md)). It asks what the
project *is*, whether it's good, where it stands, and the big strategic questions —
not what to fix line-by-line.

This is analysis, not a plan of record. **No recommendation here is being acted on**
(decision 2026-07-05). Kept as background for future direction-setting.

Basis: `docs/PROJECT_STATE.md`, `README.md`, `ARCHITECTURE.md`, and a parallel sweep
of the frontend IA, the Python/data backend, and the docs/knowledge/strategy corpus.

---

## What this is (characterization)

A **solo-built, zero-marginal-cost, cloud-native analytics platform for the Turkish
banking sector.** Every layer runs on free infrastructure — GitHub Actions for
ingestion, Cloudflare D1/R2/KV/Workers for storage and serving, keyless/free data
endpoints, deterministic (no-paid-LLM) extraction, free LLMs only for cosmetic copy.
In scope it has grown from "BDDK bulletins" into a comprehensive banking-**and**-macro
terminal: ~50 D1 tables (~1.6M rows), ~975 per-bank BRSA report PDFs parsed into ~20
structured statement tables, ~34 dashboard routes across 4 lanes, 17 CI/cron
workflows, ~69 Python scripts, ~82 extractor files, a public Telegram text-to-SQL
bot, and a documented design system + editorial engine.

**Verdict up front:** genuinely impressive — professional-grade data engineering and
an unusually mature editorial thesis, carried by (apparently) one person. The
weaknesses are not quality weaknesses; they are **strategic**: the project is
supply-rich and demand-thin, its identity is diluting from "banking" into "all of
Türkiye macro," and its single hardest asset (per-bank data no one else has clean) is
under-exploited relative to the effort spent reproducing other people's macro reports.

---

## Strengths — the real moat

1. **The per-bank BRSA extraction is the crown jewel and the true differentiator.**
   32 banks × 17 quarters × consolidated/unconsolidated, deterministically parsed
   into balance sheet, P&L, capital, liquidity, FX position, repricing, OCI, cash
   flow, equity change, NPL movement, loans-by-sector, credit quality — each
   self-validated by accounting identities. Hard, rare, and free. Nobody else
   publishes this as clean structured data.
2. **Engineering discipline is exceptional for a solo project.** Two-lane fault
   isolation, identity-gated validators, coverage-matrix-driven repair, disaster
   recovery (D1 Time Travel + dated R2 snapshots), 40+ tests, CI, chart-spec
   verification, a healthcheck alerter. The 891-line PROJECT_STATE functions as
   external memory that makes solo+AI maintenance viable.
3. **A rare self-auditing knowledge layer.** The registry ↔ chart-catalog ↔ rationale
   "triangle," an IA grounded in CAMELS × FSR × IMF-FSIs × BBVA, and *re-runnable*
   dashboard audits that diagnose the product against its own spine ("a well-built
   library that has never had a librarian").
4. **Deterministic-only turned into an asset.** The no-LLM-in-the-data-path
   constraint (a cost limit) became a trust feature: auditable, reproducible, no
   hallucinated numbers. Gaps always render as "missing," never as wrong numbers.
5. **The trajectory is correct.** "The Read" (deterministic insight engine + a
   faithfulness-gated LLM headline), the Telegram Q&A bot, the Ratios merge, and the
   live IA consolidation all show the project pivoting from *collect everything* to
   *conclude something*. That's the right instinct.

---

## Five strategic tensions

### 1. Breadth vs. banking-core depth (mission drift)
The project's own audit says it: *"the macro lane is deeper than the banking lanes it
contextualizes."* /economy now reproduces Albaraka/BBVA macro reports 1:1 (BoP, GDP,
budget, inflation, trade) while FSI-core banking gaps lingered. Each macro page is
well-built, but the **marginal /economy chart is lower-value than closing a
banking-core gap or exploiting the per-bank moat.** Is this a *banking-sector* product
or a *Türkiye-macro* product? Right now it is both, and the identity is blurring.

### 2. Supply-rich, demand-thin (the biggest gap)
Enormous investment on the supply side (data, features, rigor); almost none visible on
**distribution**. There's a public URL, a Telegram bot, and a Web-Analytics panel —
but no stated audience, no newsletter/brief, no embedding/sharing, no SEO or
discoverability play. **A world-class dataset with no owned distribution is a warehouse
nobody visits.** The highest-leverage next move is probably not another data lane but
turning the moat into something that goes *out* and that people return to.

### 3. Solo sustainability / bus factor
The whole system — 17 workflows, ~50 tables, ~69 scripts, ~82 extractor files, 34
pages — rests on one person + AI + a heroic engineering journal. That journal is
brilliant for continuity but is also a single point of failure, and every new lane
adds maintenance surface (a source changes format → silent breakage). Growth phase, or
time to shift to **consolidate / harden / distribute**?

### 4. The "so what" gap (self-diagnosed, half-fixed)
`display-study.md` nailed it: *"measures everything and concludes almost nothing."*
"The Read" is the fix in progress but runs on only **8 of 34 pages**. The deferred
**chronology lane** ("what changed this week and does it matter" — merging regulation +
news + disclosures + rate decisions) is arguably the single feature that would most
convert the product from a reference library into a thing analysts open every morning.
Synthesis is the frontier, not more raw series.

### 5. Fragile free-tier / unofficial-endpoint dependency
Everything rests on free tiers and undocumented endpoints (Yahoo chart API, TEFAS JSON,
Google-News redirect decoding, EVDS, keyless scrapes, Cloudflare/GitHub free limits).
The two-lane isolation + healthcheck + chart-spec verifier are good hygiene but don't
remove the risk. There is no explicit "what breaks if X goes away" blast-radius map.

---

## Prioritized recommendations (parked)

**A. Decide the identity; rebalance toward the differentiator.** Freeze macro-report
reproduction breadth. Redirect effort to (i) the chronology/"what changed" lane, (ii)
exploiting per-bank data no one else has (cross-bank league, head-to-head, peer
benchmarking — the deferred phase 4b), and (iii) the FSI-core banking gaps the audit
named.

**B. Own distribution.** Turn pipeline output into something that leaves the site: a
weekly auto-generated "State of Turkish Banking" brief (the AI research reports + "The
Read" + chronology → email/X/LinkedIn), shareable/embeddable chart mode, a read API,
per-bank-page SEO. Likely the single biggest unlock.

**C. Shift the eng posture from growth to consolidation.** Pay down the named debt —
the scariest is **CI silently skipping the fitz/pdfplumber extractor test suite**, i.e.
the crown-jewel extractors aren't actually gated. Unify the two header tiers, finish IA
consolidation (retire redirect debris, settle Digital's lane), add data-layer tests.

**D. Build a resilience/dependency map.** Enumerate every external free dependency, its
failure mode, and its fallback. Know the blast radius before it bites.

**E. Close the synthesis loop.** "The Read" on all tabs + the chronology lane + let an
LLM narrate *across* the whole dataset (automated, on-dashboard versions of the AI
research reports). Where per-bank data + macro context + news + regulation finally
combine into the "answered questions" the strategist audience wants — and what makes
the product unique rather than merely comprehensive.

---

## Caveat

This assessed the artifact, not its users. No read on actual traffic, who (if anyone)
relies on it, or whether the goal is impact/audience, a personal research tool, or the
craft of building it — which changes which recommendations matter. The "distribution"
critique assumes reach is a goal; if this is a private analytical instrument,
breadth-for-its-own-sake is a legitimate end. **The project-goal question was left open
on 2026-07-05** — resolve it before picking a direction from the list above.
