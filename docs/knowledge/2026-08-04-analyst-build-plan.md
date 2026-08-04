# Analyst build plan — 2026-08-04

> **Status: IMPLEMENTED and CALIBRATED, same day** (commits `77b92ad` →
> `5b31f4c`; calibration verdict at the end of this doc). Artifacts-only until
> the D1 write freeze lifts. Originally: task-level detail for building the
> automated analyst layer, superseding the abstract discussion in
> `2026-08-04-analyst-feasibility-test.md` — the feasibility test answered "can
> it work"; this said "here is every piece, in order, with pass/fail criteria."

> **As-built corrections (2026-08-04, pre-implementation probe).** The first
> draft carried premises the snapshot refutes; corrected in place below:
> periods are `YYYYQN` with **no hyphen**; the BS total row is
> `hierarchy = ''` (empty string), never `'TOTAL'` or a label match;
> **2026Q2 does not exist in the numeric lanes** (TEB's wrong-unit extraction
> was purged, and further 2026Q2 extraction is blocked *until these detectors
> exist*), so TEB-case criteria run on synthetic fixtures; balance sheet and
> P&L store **no prior column** — cross-period anchors live only in the
> `period_type` lanes; `basis_text` is one row per filing in the filing's own
> language (tr 654 / en 322), not a TR+EN pair; discontinued operations are
> already a `pl_roles` role (`disc_net`) — the detector watches the amount,
> not row appearance (the "GARAN Romania" pass case came from a ChatGPT
> review and was verified fabricated); nothing stores `reporting_unit` today
> and filings are R2-only, so fresh unit regex runs in CI; migration number
> is 0037; Task 1.8 (divergence detectors) added from the feasibility
> verdict's "two missing derivations".

## Ground rules

Every task below traces to a specific existing file, table, or pattern in the
repo. Nothing is greenfield — the substrate (bot's grounding stack, D1 schema,
validator infrastructure, snapshot lane, workflow conventions) is the
scaffolding.

**The analyst never sets a figure.** It reads figures from deterministic SQL
queries and writes connective prose. The `gotData` + `unsupportedFigures` guard
from `web/app/lib/bot.ts` applies unchanged (the `gotData` flag at `:244`, the
ungrounded-figure drop at `:302`, `unsupportedFigures` at `:322`/`:478`): a
paragraph containing a 4+ digit number without a query having returned ≥1 row is
never sent. Abstention is structural, not behavioral.

**One LLM agent, not a team.** The external report's own citations (Kim et al.
2025) show single-agent ≥ multi-agent at matched token budget on tool-heavy
tasks. The feasibility test showed the gap is asking follow-up questions of data
already held — not parallel specialist views.

**Detectors are deterministic.** Every signal is a structured fact produced by
a TypeScript/Python comparison against stored rows. The LLM never discovers
what changed — it receives a list and contextualizes it.

---

## Phase 1 — Section 9 detectors (comparability infrastructure)

These close the gap ChatGPT flagged: "audited quarterly" is too generic.
They produce structured signals from the data already held. All run
deterministically against the audit-lane snapshot (`data/bank_audit.db`).

### Task 1.1 — Reporting-unit change detector

**File:** `src/analyst/detect_unit_change.py`
**What:** Compares `total_assets` QoQ for every bank/period/kind. A ratio
`current_total / prior_total > 50` or `< 0.02` fires. The TEB 2026Q2 case:
assets ₺799bn → ₺841m (ratio 0.00105, the bank switched Bin→Milyon).

**Input:** `bank_audit_balance_sheet` — for each `(bank_ticker, kind)`, the
total row is `WHERE hierarchy = ''` (empty string; every detail row carries a
roman or dotted numeral) within each `statement` leg; total assets =
`MAX(amount_total)` across both legs, per the corpus rule in `bot-schema.ts`.
Compare consecutive periods.

**Output:** `{ signal: "unit_change", bank, period, kind, prior_total, current_total, ratio }`

**Pass criteria:**
- Fires on a synthetic TEB fixture (2026Q1 = 799,241,647 ₺000 → a
  million-printed Q2 at ~1/1000 scale; ratio ~0.00105). The real rows were
  purged from the snapshot, and the standing instruction blocks further 2026Q2
  extraction **until this detector exists** — this task is the unblocker.
- Silent on the full stored 2022Q1→2026Q1 corpus (38 banks × 17 quarters)
- Handles both BS legs (assets and liabilities totals)
- Skips missing periods gracefully

### Task 1.2 — Cross-period discontinuity detector

**File:** `src/analyst/detect_cross_period.py`
**What:** Compare each filing's stored PRIOR column against the value the
earlier filing itself reported. Balance sheet and P&L store **no prior column**
(their continuity check is Task 1.1's QoQ ratio); the stored priors live in the
`period_type` lanes, where the prior column is the **prior year-end** — every
quarter of year Y carries it, giving a free 4-way anchor against the stored
Y−1 Q4 current column:

| Lane | Anchor | Table |
|---|---|---|
| Capital | `total_capital`, `total_rwa`, `cet1_ratio`, `capital_adequacy_ratio` | `bank_audit_capital` |
| Liquidity | `leverage_ratio`, `lcr_total`, `lcr_fc`, `nsfr` | `bank_audit_liquidity` |
| FX position | TOTAL `net_position` (reuse `fx_cross_period`'s comparison) | `bank_audit_fx_position` |
| NPL movement | `opening_balance` vs prior year-end `closing_balance`, per group | `bank_audit_npl_movement` |
| Equity | prior-block closing `total_equity` vs prior-year SAME-quarter current | `bank_audit_equity_change` |

**Deliberately excluded: `credit_quality`.** Its prior columns were never
validated (the §4 lanes checked only the current column for years) and a
corpus run fires 235 times, dominated by wrong-cell prior reads (YKBNK 2025Q1
`loans_by_stage` prior prints ₺7.2bn against a ₺1.2tn reference). Anchor it
only after the prior-column repair lands. Two more corpus-taught guards:
a stored prior of literal `0.0` against a large reference is the dash→0.0
extraction artifact, not a restatement (SKBNK's 2023–24 capital priors) —
skipped; and a hit on a partition whose lane validator is already failing is
marked `lane_validation_failing: true` (read as extraction defect first).

A mismatch ≥1% on any anchor fires. The relationship to the validators is
deliberate and inverted: `validator.py` **suppresses** known restatements via
skip-lists (`_FX_XPERIOD_SKIP` at `revalidate_audit_db.py:308`, plus
`_RP_SKIP`/`_RP_PRIOR_SKIP`) so lanes stay green — the detector **fires
informatively** on exactly those, because a restatement is a fact the analyst
memo must carry, not an error to hide.

**Output:** `{ signal: "cross_period_mismatch", bank, period, kind, lane, prior_col, current_prev_period, pct_diff }`

**Pass criteria:**
- Fires on the documented restatements the validator skip-lists: HALKB
  2025Q3/Q4 unconsolidated FX, ALBRK 2023Q1 consolidated, TOMK 2024Q2–Q4
  unconsolidated, ALNTF 2023Q1 unconsolidated. *(TOMK 2024Q1's prior column is
  blank in the source — the zero-guard correctly declines to compare a value
  the filer never printed.)*
- Fires at ~1000× on a synthetic TEB-style fixture
- Silent on the partitions that reconcile (the overwhelming majority)
- Skips partitions where the prior period is genuinely absent (new-entrant
  banks, first filings)

### Task 1.3 — Audit opinion classification + change detector

**File:** `src/analyst/detect_opinion_change.py` + `src/analyst/classify_basis.py`
**What:** Two sub-tasks.

**1.3a — Classify the qualified `basis_text` paragraphs.**
`bank_audit_opinion` holds 976 rows (552 modified, 424 clean); **545** of the
modified rows carry a non-empty `basis_text` paragraph (the auditor's "Basis
for Qualified Opinion"). Currently they are stored verbatim and **never
classified**.

Build a deterministic classifier (regex, no LLM) that tags each paragraph into a
closed set of categories. The feasibility test already found the categories:
- `free_provision` — "a portion of the free provision…outside of the
  requirements of BRSA…" (ALBRK, ŞEKERBANK, most modified opinions)
- `bond_reclassification` — state banks reclassifying bond portfolios
- `other` — catch-all for the tail

Each row is stored **in the filing's own language** (`language` column: tr 654 /
en 322 across all rows) — there is no TR+EN pair. The classifier carries phrase
patterns for both languages and anchors on the **leading** portion of the text:
the qualification sits at the start of the field, and the known `_BASIS_END`
defect means the tail can over-run into Key Audit Matters.

**1.3b — Detect opinion changes.**
For each bank, compare consecutive quarters:
- `opinion_type` change (clean → qualified, qualified → clean, etc.)
- `category` change (free_provision → bond_reclassification → other)
- `report_kind` change (review → audit, audit → review — Q4 vs interim is
  expected; an unexpected change fires)
- `auditor` change (PwC → KPMG, etc.)

**Output:** `{ signal: "opinion_change", bank, period, kind, prior_type, current_type, prior_category, current_category, basis_text_excerpt }`

**Pass criteria:**
- Classifies at least 80% of the 552 modified paragraphs (the `free_provision`
  category alone should cover the majority — ALBRK, ŞEKERBANK, and most
  modified opinions are over exactly this)
- `other` is reserved for the genuine tail
- Detects ALBRK's consistent "qualified every quarter" pattern (no false
  positive on a bank that stays qualified for the same reason)
- Detects if a bank goes clean → qualified for a NEW reason

### Task 1.4 — Perimeter-change detector

**File:** `src/analyst/detect_perimeter_change.py`
**What:** Detects changes in the bank's reporting perimeter that make QoQ
comparison misleading. Three checks:

**1.4a — Consolidated/unconsolidated gap widening.**
For banks that file both kinds, compute:
```
gap = abs(consolidated_total_assets − unconsolidated_total_assets) / unconsolidated_total_assets
```
Fire when `|gap_current − gap_prior| > 0.03` (3pp). *(The first draft said
20pp — the largest move in the stored corpus is 12.7pp, ANADOLU 2024Q2, so a
20pp detector can never fire. 3pp captures the nine real perimeter moves out
of 428 stored quarter-pairs and nothing else.)* A subsidiary
acquisition/disposal moves this gap.

**1.4b — Discontinued operations.**
`bank_audit_pl_roles` already carries a `disc_net` role in 1,039 of 1,050
partitions — the discontinued-operations line exists as a printed row almost
everywhere, so **row appearance is not the signal; the amount is**. Fire when
the `disc_net`-role amount transitions from zero/NULL to material (or back).
*(The first draft cited "Garanti's Romania disposal" as the canonical case —
that came from a ChatGPT site review and was verified fabricated. The pass case
is whatever real `disc_net` transitions the corpus actually holds, plus a
synthetic fixture.)*

**1.4c — New/missing line items in P&L.**
Scan `bank_audit_pl_roles` for each bank/period. A role key that was present in
Qn-1 but absent in Qn (or vice versa) fires — it means the bank changed its
income-statement structure (new subsidiary, new business line, regulatory
reclassification).

**Output:** `{ signal: "perimeter_change", bank, period, kind, subtype: "cons_gap"|"discontinued_ops"|"line_item_change", detail }`

**Pass criteria:**
- Fires on real `disc_net` zero→material transitions in the corpus if any
  exist (report the census); synthetic fixture otherwise
- Fires on any bank whose con/uncon gap materializes or disappears
- Silent on banks that file only one kind (no gap to compare)
- Silent on stable P&L structures

### Task 1.5 — Basis-metadata extractor

**File:** `src/analyst/extract_basis_metadata.py`
**What:** Extracts three structured facts from the front-matter of every filing
that the current pipeline reads but does not store as structured fields. These
are the exact items ChatGPT said should be an assurance badge:

| Field | Source | How |
|---|---|---|
| `reporting_unit` | "Bin Türk Lirası" / "Milyon Türk Lirası" declaration | Regex — designed in `2026-08-01-llm-vs-regex-unit-detection.md`, code already exists at `scripts/scratch_bench_unit_detection.py` (22-page window, clean on 550 sampled filings); promote it into `src/analyst/`. Filings are **R2-only** (no local PDFs), so the fresh regex pass runs in CI; stored 2022Q1–2026Q1 partitions are seeded `bin` — the sweep established no pre-2026Q2 filing ever used millions — with provenance marking them sweep-derived |
| `assurance_level` | Already stored as `report_kind` in `bank_audit_opinion` — `audit` for Q4 annual, `review` for Q1–Q3 interim | Join on `bank_audit_opinion` — no re-extraction needed |
| `consolidation_basis` | "Konsolide" / "Konsolide Olmayan" from the filing's title page | Already derivable from the `kind` column (`consolidated` / `unconsolidated`) + the `bank_audit_opinion.solvency_type` field |

The output is NOT a detector signal — it's a structured metadata row that the
analyst agent and the per-bank page consume. The `reporting_unit` field enables
Task 1.1 to be a cross-check (the stored unit should match the detected unit).

**Output:** `{ bank, period, kind, reporting_unit: "bin"|"milyon", assurance_level: "audit"|"review", consolidation_basis: "consolidated"|"unconsolidated" }`

**Pass criteria:**
- `reporting_unit` returns `milyon` for all 11 held 2026Q2 filings and `bin`
  for all 2022Q1–2026Q1 filings (confirmed by the July-August sweep)
- `assurance_level` matches `bank_audit_opinion.report_kind` for every
  partition that has an opinion row
- Zero UNKNOWN on the 550-sample sweep corpus

### Task 1.8 — Divergence detectors (headline-conceals-composition)

**File:** `src/analyst/detect_divergence.py`
**What:** The two derivations the feasibility verdict names as the missing
half of Case B — "cheap, deterministic, and would have caught Şekerbank
automatically." Nothing in the stored data currently flags "the headline
conceals the composition"; these two do.

**1.8a — Capital composition.** From `bank_audit_capital`: the CAR − CET1 gap,
normalized as the non-core share of regulatory capital (`gap / CAR`). Fire when
non-core share ≥ 40%, or when the gap widens materially QoQ while CAR holds
(the Tier-2-plugging-a-core-hole signature, ŞEKERBANK 2025Q3: CAR 17.87 → 24.18
while CET1 12.92 → 11.46). Thresholds tuned on the fleet at build time with two
required hits: SKBNK 2026Q1 (gap 13.5pp, 61% non-core) and ALBRK 2026Q1 (gap
7.4pp, 47% non-core).

**1.8b — NPL-vs-coverage divergence.** From `bank_audit_stages` (coverage is
precomputed there, stored as a FRACTION unlike the percent capital ratios):
NPL ratio flat or falling over a trailing 4-quarter window while Stage 3
coverage falls ≥ 10pp. *(At 5pp the corpus fires 138 times across 23 banks —
that describes the 2022–26 dilution cycle, not an outlier; 10pp yields 71
over a real outlier set. Severity: `alert` when coverage lands under 60% or
the fall is ≥ 15pp, else `notice`.)* The ŞEKERBANK pattern: NPL 1.70 → 1.33
while coverage 69.7% → 48.3%. A falling NPL ratio with collapsing coverage is
invisible to any single-series screen — this is the signal that forces the
npl_movement decomposition question.

**Output:** `{ signal: "divergence", subtype: "capital_composition"|"npl_coverage", bank, period, kind, detail }`

**Pass criteria:**
- 1.8a fires on SKBNK 2026Q1 and ALBRK 2026Q1
- 1.8b fires on SKBNK 2026Q1; correctly silent on ALBRK (its NPL is *rising* —
  visible in the headline, not concealed)
- Firing rate across the fleet is reported and stays a minority of partitions
  (it is a signal, not a constant)

### Task 1.6 — Detector runner CLI

**File:** `scripts/analyst/detect.py`
**What:** Runs all detector modules against the audit-lane snapshot and emits
a combined signals JSON file. Optionally pushes to a D1 table.

```bash
python scripts/analyst/detect.py --db data/bank_audit.db           # all banks, all periods
python scripts/analyst/detect.py --bank SKBNK --period 2026Q1      # single partition
python scripts/analyst/detect.py --signal-type unit_change          # one detector
python scripts/analyst/detect.py --push                            # push signals to D1
```

**Pass criteria:**
- Runs all detector modules in <30 seconds against the full 38-bank /
  17-quarter snapshot
- Emits a JSON file with one signal per line, keyed by `(signal_type, subtype,
  bank, period, kind)`
- `--stage` mode writes to `data/analyst.db` staging tables (only — there is
  no push flag at all while the D1-write freeze stands; the push wiring is a
  freeze-lift decision, see Task 1.7)

### Task 1.7 — D1 tables for signals

**File:** `web/migrations/0037_analyst_signals.sql`
*(0036 is taken — `0036_bank_call_transcripts.sql` already exists.)*
**What:** Two new D1 tables plus one view for the Worker to read.

```sql
-- One row per detector firing. The analytical fact, not the prose.
CREATE TABLE IF NOT EXISTS analyst_signals (
    signal_id     TEXT NOT NULL,          -- e.g. "unit_change:SKBNK:2026Q2:unconsolidated"
    signal_type   TEXT NOT NULL,          -- unit_change | cross_period_mismatch | opinion_change | perimeter_change | divergence
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    severity      TEXT NOT NULL,          -- notice | alert | critical
    fired_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload       TEXT NOT NULL,          -- JSON: { prior_value, current_value, ratio, detail, ... }
    PRIMARY KEY (signal_id)
);

-- One row per analyst note produced. The prose, grounded on signals.
CREATE TABLE IF NOT EXISTS analyst_notes (
    note_id       TEXT NOT NULL,          -- e.g. "note:SKBNK:2026Q1:2026-08-05"
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    signal_ids    TEXT NOT NULL,          -- JSON array of signal_ids this note is based on
    title         TEXT NOT NULL,          -- one-line summary
    body          TEXT NOT NULL,          -- markdown, ~2-3 pages
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model         TEXT,                   -- which LLM produced it
    fact_check_passed INTEGER NOT NULL DEFAULT 0,  -- gotData + unsupportedFigures verified
    PRIMARY KEY (note_id)
);

-- Convenience: latest note per bank, for the per-bank page to join
CREATE VIEW IF NOT EXISTS v_latest_analyst_note AS
SELECT n.* FROM analyst_notes n
JOIN (
    SELECT bank_ticker, MAX(generated_at) AS max_at
    FROM analyst_notes GROUP BY bank_ticker
) latest ON n.bank_ticker = latest.bank_ticker AND n.generated_at = latest.max_at;
```

**Follow-up task (schema.py):** Mirror the DDL in `src/analyst/schema.py` so
the staging SQLite gets these tables — needed for local testing and for
`push_to_d1.py` to sync them. Registration reality: a table reaches D1 only by
being in `registry.REGISTRY` or `INFRA_TABLES`
(`src/audit_reports/registry.py:173`) — these are not statement lanes, so they
join via the infra/table-set path, and the actual push stays behind the
standing D1-write freeze.

**Pass criteria:**
- Migration applies cleanly against local D1 (`npx wrangler d1 migrations apply bddk-data --local`)
- `analyst_signals` primary key prevents duplicate signals
- `analyst_notes.fact_check_passed` is enforced by the agent runner (not by SQL constraint — it's a runtime gate)

---

## Phase 2 — 11-section data assembly

Before the model produces a memo, a deterministic query layer assembles the
full analytical view. This is the bridge between "stored rows spread across 16
audit tables + bulletin tables + EVDS + KAP" and "the 11 things a bank analyst
looks at."

### Task 2.1 — Query layer: section queries

**File:** `web/app/lib/analyst/sections.ts` (new file)
**What:** For a given `(bank_ticker, period, kind)`, returns a typed object
with all 11 sections populated from the data that already exists. Each section
is a deterministic SQL query (reusing `cachedAll()` from `db.ts`).

The sections and their source tables:

```typescript
interface AnalystSections {
  // Section 1 — Business model
  business: {
    bank_type: string;             // bank_types
    ownership: {                   // kap_ownership (current as_of)
      shareholders: { name, share_pct, is_indirect }[];
      subsidiaries: { name, activity, share_pct }[];
      free_float: number;
    };
    profile: {                     // bank_audit_profile
      branches: number | null;
      personnel: number | null;
    };
    digital: {                     // tbb_digital_stats or tkbb_digital_stats
      active_customers: number | null;
      digital_customers: number | null;
    };
    market_share: {                // derived from balance_sheet sector table
      assets_pct: number;
      loans_pct: number;
      deposits_pct: number;
      peer_rank_by_assets: number;
      peer_count: number;
    };
  };

  // Section 2 — Macro / regulation (point-in-time for the period)
  macro: {
    policy_rate: number | null;    // evds_series
    cpi_12m: number | null;        // evds_series
    usd_try: number | null;        // evds_series
    regulations: {                 // regulation_briefings (nearest briefing to period)
      categories: string[];
      summary: string;
    };
  };

  // Section 3 — Earnings quality
  earnings: {
    balance_sheet_total: number;   // bank_audit_balance_sheet (TOTAL row)
    net_income_ttm: number;        // bank_audit_profit_loss + pl_roles (decumulated)
    net_income_quarterly: number;
    roe_nominal: number;
    roe_real: number;              // Fisher-deflated via real-terms.ts
    roa_nominal: number;
    free_provision_release: number | null;  // bank_audit_free_provision
    fp_pct_of_income: number | null;
    adjusted_net_income_ttm: number | null; // net income − FP release
    nim_approximation: {           // P&L sub-items (interest income / avg assets)
      interest_income: number;
      interest_expense: number;
      net_interest: number;
      avg_earning_assets: number | null;
      nim_pct: number | null;
    };
    fee_income: {                  // P&L sub-items 4.1, 4.2, 5.1, 5.2
      total_fees_received: number;
      total_fees_paid: number;
      net_fees: number;
    };
    opex: {                        // P&L via pl_roles (opex anchors)
      personnel: number | null;
      other_opex: number | null;
      total_opex: number;
      cost_income_pct: number;
    };
    pl_movers: {                   // biggest QoQ line-item changes (top 5)
      item_name: string;
      change_pct: number;
    }[];
  };

  // Section 4 — Asset quality
  asset_quality: {
    gross_loans: number;           // bank_audit_balance_sheet
    npl_gross: number;             // bank_audit_credit_quality (Stage 3)
    npl_ratio_pct: number;
    stage2_ratio_pct: number;
    stage2_total: number;
    stage1_total: number;
    stage3_coverage_pct: number;   // ECL / Stage 3
    cost_of_risk_pct: number | null; // provisions / avg gross loans (TTM)
    npl_movement: {                // bank_audit_npl_movement
      opening: number;
      additions: number;
      collections: number;
      write_offs: number;
      closing: number;
    };
    npl_by_bucket: {               // decomposed from npl_movement
      group3_share: number | null;
      group4_share: number | null;
      group5_share: number | null;
      group3_coverage: number | null;
      group4_coverage: number | null;
      group5_coverage: number | null;
    };
    loans_by_sector: {             // bank_audit_loans_by_sector (top 5)
      sector: string;
      amount: number;
      share_pct: number;
    }[];
  };

  // Section 5 — Currency risk
  currency: {
    net_fx_position: number;       // bank_audit_fx_position
    net_on_balance: number;
    net_off_balance: number;
    fx_breakdown: {
      ccy: string;
      net_position: number;
    }[];
    fx_assets_total: number;       // bank_audit_balance_sheet (FC column total)
    fx_liabilities_total: number;
    usd_try_rate: number;          // evds_series
  };

  // Section 6 — Funding and liquidity
  funding: {
    total_deposits: number;        // bank_audit_balance_sheet
    try_deposits: number;
    fc_deposits: number;
    demand_deposits: number | null;
    ldr_pct: number;               // loans / deposits
    lcr_total_pct: number | null;  // bank_audit_liquidity
    lcr_fc_pct: number | null;
    nsfr_pct: number | null;
    leverage_pct: number | null;
  };

  // Section 7 — Capital
  capital: {
    cet1_pct: number;              // bank_audit_capital
    tier1_pct: number;
    car_pct: number;
    car_minus_cet1_pp: number;     // the Şekerbank signal
    rwa: number;
    total_equity: number;
    equity_to_assets_pct: number;
    capital_trajectory: {          // last 4 quarters
      period: string;
      cet1: number;
      car: number;
    }[];
  };

  // Section 8 — Securities portfolio
  securities: {
    total_securities: number;      // bank_audit_balance_sheet
    securities_to_assets_pct: number;
    // Breakdown (fixed/CPI-linked/trading) NOT available — in footnotes, not extracted
    breakdown_available: false;
  };

  // Section 9 — Comparability (the section 9 metadata)
  comparability: {
    reporting_unit: string;        // from Task 1.5
    assurance_level: string;       // audit | review
    consolidation_basis: string;   // consolidated | unconsolidated
    opinion_type: string;          // clean | qualified | adverse | disclaimer
    opinion_category: string | null; // from Task 1.3a
    basis_text_excerpt: string | null;
    auditor: string | null;
    signals_this_period: {         // any section 9 signals that fired
      signal_type: string;
      severity: string;
    }[];
  };

  // Section 10 — Governance
  governance: {
    controlling_shareholder: string | null;  // kap_ownership (largest direct holder)
    free_float_pct: number | null;
    qualified_opinion_streak: number;  // consecutive quarters qualified
    is_free_provision_qualified: boolean;
  };

  // Section 11 — Valuation
  valuation: {
    roe_nominal: number;
    roe_real: number;
    roe_ex_fp: number | null;      // ROE excluding free provision release
    book_value_per_share: null;    // NOT available — BIST prices removed
    price_to_book: null;
    // All valuation fields null — prices removed. Only profitability metrics.
  };

  // Metadata
  meta: {
    bank_ticker: string;
    bank_name: string;
    period: string;
    kind: string;
    generated_at: string;
    data_freshness: {              // MAX(extracted_at) per source table
      source: string;
      latest: string;
    }[];
  };
}
```

**Pass criteria:**
- `buildAnalystSections("SKBNK", "2026Q1", "unconsolidated")` returns every
  non-nullable field populated from the snapshot
- Every nullable field that IS in the data returns a value (not null where
  the row exists)
- The function does NOT call an LLM — it's pure deterministic SQL assembly
- Runs in <500ms against the snapshot (local SQLite) or <2s against D1
- Reuses `cachedAll()` for D1 queries (already in `web/app/lib/db.ts`)
- Each section has a `_gaps: string[]` field listing what IS missing (e.g.,
  securities breakdown, BIST prices) — this is the agent's awareness of its
  own blind spots

### Task 2.2 — Peer context builder

**File:** `web/app/lib/analyst/peers.ts` (new file)
**What:** For a given bank, computes licence-class peer medians for the key
ratios (ROE, NPL, CAR, CET1, LDR, NIM). This is the "is it the bank or the
sector" layer. Reuses `peerStat()` from `bank-brief.ts` but extends it to
compute medians per section.

**Output:** `PeerContext { bank.licence_class, medians: { roe, npl_ratio, car, cet1, ldr, stage2_ratio, coverage, cost_of_risk, fee_ratio, cost_income }, peer_count, excluded_tickers }`

**Pass criteria:**
- Excludes `PEER_EXCLUDED_TICKERS` (TAKAS)
- Groups by licence class (deposit / participation / development)
- Computes medians (not means — medians are robust to one outlier bank)
- Returns N/A for ratios where fewer than 3 peers hold data

### Task 2.3 — Previous-period comparator

**File:** `web/app/lib/analyst/comparator.ts` (new file)
**What:** For a given `(bank, period, kind)`, returns the QoQ and YoY changes
for every key metric in the 11-section view. This is the raw material the
detectors already computed — the comparator makes it queryable per-section.

**Pass criteria:**
- QoQ for the same bank/kind, previous quarter
- YoY for the same bank/kind, same quarter one year prior
- Handles missing prior periods gracefully (new entrant banks)
- Returns both direction (`up`/`down`/`flat`) and magnitude (`+12.3pp`, `−4.7%`)

---

## Phase 3 — The analyst agent

### Task 3.1 — LLM prompt + system message

**File:** `web/app/lib/analyst/prompt.ts` (new file)
**What:** The system prompt that converts the assembled 11-section data +
signals + peer context + comparatives into a 2–3 page analyst memo.

**Design constraints:**
- The model receives **data, not tables**. Each section arrives as a typed
  key-value block (e.g., `CAR: 22.13% (peer median 18.6%)`). The model never
  writes SQL.
- The prompt explicitly names what IS missing per section (the `_gaps` field
  from Task 2.1). The model must NOT guess missing data.
- The model is instructed to structure the memo as:
  1. **Headline** (one sentence — the single most important fact about this
     bank this quarter)
  2. **What changed** (2–3 paragraphs — the signals that fired, QoQ/YoY
     movements that matter, peer context)
  3. **What it means** (2–3 paragraphs — causal chain, drawing from
     npl_movement decomposition, equity change, free provision, the auditor's
     words, and regulation)
  4. **What to watch** (bullet points — 2–4 forward indicators with
     falsification conditions)
  5. **Comparability caveats** (bullet points — stage definitions differ,
     reporting unit changed, opinion qualified over X, etc.)
- The model uses the **same free-tier LLM chain** as the bot:
  `web/app/lib/llm.ts` → OpenRouter `nemotron-3-super-120b-a12b:free` →
  Groq `openai/gpt-oss-120b` → Cerebras `gpt-oss-120b`
- Temperature 0.0, fixed seed
- Max output: 2,000 words

**Pass criteria:**
- The prompt fits in the free-tier models' context windows (~128k tokens for
  nemotron, less for others)
- A run with `ANALYST_DRY_RUN=true` returns the prompt without calling an LLM
  (for debugging)
- The prompt explicitly forbids investment recommendations, price targets, and
  trade calls

### Task 3.2 — Grounding guard (reuse bot.ts, don't reimplement)

**File:** `web/app/lib/analyst/guard.ts` (new file)
**What:** Wraps the analyst output in the same grounding stack as the Telegram
bot. This is NOT new code — it imports and extends the existing guards.

**Guard pipeline:**
1. `gotData` — every 4+ digit number in the memo must appear in the assembled
   sections data. If not, the paragraph is dropped.
2. `unsupportedFigures` — percentages matched at ×1 and ×100 (like the bot).
   Decimal-appropriate tolerance.
3. `hasOnlyKnownNumbers` — the `det_hash` equivalent: the output's claim set
   is diffed against the input data's fact set.
4. Substitution: the model's hand-typed list of metrics is replaced with one
   rendered from the actual assembled sections (same `substituteDataList()`
   pattern from `bot-sql.ts`).

**Pass criteria:**
- A memo with a hallucinated figure (e.g., "NPL ratio 5.2%" when the data
  says 1.33%) is either corrected or the paragraph is dropped
- The guard never modifies a figure — it drops or flags, it doesn't edit
- `fact_check_passed` in `analyst_notes` is set to 0 if any figure failed
  and the paragraph could not be corrected

### Task 3.3 — Agent runner

**File:** `scripts/analyst/run_agent.py` or `web/app/lib/analyst/runner.ts`
**What:** The orchestrator that:
1. Calls `buildAnalystSections()` (Task 2.1)
2. Fetches peer context (Task 2.2)
3. Fetches comparatives (Task 2.3)
4. Fetches fired signals for this bank/period from `analyst_signals`
5. Assembles the prompt (Task 3.1)
6. Calls the LLM (via `llm.ts`)
7. Runs the grounding guard (Task 3.2)
8. Stores the result in `analyst_notes`

**Location choice:** The agent should run in the **Next.js Worker**, reusing
the existing D1 bindings, `llm.ts`, and `bot.ts` grounding stack. A Python
version can exist for local testing against the snapshot, but the production
path is TypeScript in the Worker.

**Pass criteria:**
- `POST /api/admin/analyst/run?bank=SKBNK&period=2026Q1&kind=unconsolidated`
  returns the memo as JSON (admin-gated — same auth as /admin)
- A dry-run mode returns the assembled prompt without calling the LLM
- The agent respects the same `RUN_BUDGET_MS = 20_000` timeout as the bot
- Errors (D1 unavailable, LLM timeout, grounding failure) are caught and
  logged — the memo is NOT stored if fact_check fails

### Task 3.4 — Calibration test

**What:** Run the agent against ALBRK 2026Q1 and ŞEKERBANK 2026Q1 — the same
(bank, period) pairs the hand-written memos in
`docs/knowledge/2026-08-04-analyst-feasibility-test.md` cover. (Memo A is the
ALBRK **2026Q1** memo; the ₺7.0bn release it centres on sits in the 2025Q1
comparative history.)

**ALBRK 2026Q1 pass criteria:**
- The headline names the free-provision release as the dominant fact
- The memo quantifies it (₺7.0bn = 89% of printed profit)
- It identifies the core-margin halving (₺2.22bn → ₺1.10bn) in the same
  quarter the release flattered the bottom line
- The comparability caveats note the qualified opinion, the reporting unit,
  and the fact that the printed profit history is not comparable to itself

**ŞEKERBANK 2026Q1 pass criteria:**
- The headline names the CAR/CET1 divergence (22.1% vs 8.6%) or the NPL/
  coverage divergence (1.33% vs 48.3%)
- The memo decomposes the coverage fall (mix vs genuine erosion) using the
  npl_movement data — NOT a causal guess
- It identifies the free-provision release (₺350m = 17% of 2025 profit)
- The comparability caveats note the qualified opinion and the fact that
  headline ratios (CAR, NPL) flatter the bank

**Failing criteria:** The agent produces a memo that is factually correct but
misses the non-obvious finding (it reports the printed ROE and NPL without
decomposing them). This is the "first question vs second question" gap from the
feasibility test.

---

## Phase 4 — Delivery infrastructure

### Task 4.1 — GitHub Actions workflow

**File:** `.github/workflows/analyst-daily.yml`
**What:** Daily run that:
1. Pulls the audit-lane snapshot from R2
2. Runs `scripts/analyst/detect.py` (all detectors)
3. If signals fired, pushes `analyst_signals` to D1
4. For each bank with new critical/alert signals, calls the agent
5. Pushes `analyst_notes` to D1
6. Notifies Telegram for critical-severity signals (reusing `scripts/notify.py`)

**Schedule:** Daily 07:00 UTC (after the news refresh, before European market
open). The first version is dispatch-only until the calibration test passes.

**Concurrency group:** `bddk-audit` (it reads the audit snapshot — must not
race with `refresh-audit.yml`).

**Secrets needed:** Same as the bot — `OPEN_ROUTER_API`, `CEREBRAS_KEY`,
`GROQ_API_KEY` (already in `web/cloudflare-env.d.ts`). No new secrets.

**Pass criteria:**
- A `dry_run=true` dispatch reads the snapshot, runs detectors, prints signals,
  calls no LLM, pushes nothing
- A real run with no signals fires (quiet day) exits 0 and pushes nothing
- A run with signals fires, generates notes, pushes to D1, and pings Telegram
  (if `NOTIFY_TELEGRAM` is set)

### Task 4.2 — /admin integration

**File:** `web/app/admin/analyst/page.tsx` + `web/app/admin/analyst/AnalystCard.tsx`
**What:** A new card on `/admin` showing:
- Recent signals (last 7 days, grouped by bank/severity)
- Recent analyst notes (last 7 days, latest 5)
- Manual trigger: "Run analyst for bank X, period Y"
- Per-signal detail: click to see the signal payload + the note it generated

**Pass criteria:**
- Admin-gated (same auth as the rest of /admin)
- Shows "No signals today" on a quiet day
- Manual trigger dispatches `analyst-daily.yml` with `banks=<TICKER>` input
- Reuses existing GitHub Actions dispatch pattern from the Pipeline card

### Task 4.3 — Per-bank page integration

**File:** `web/app/banks/[ticker]/page.tsx`
**What:** A "Analyst" section on the per-bank page, below the vitals and above
the financials. Shows:
- The latest analyst note for this bank (headline + first paragraph)
- Signals that fired this quarter
- Link to full note (modal or dedicated page)
- The comparability badge (reporting unit, assurance level, opinion type)

**The badge** — this is the ChatGPT recommendation, concretely:
```
2026 Q1 · limited review · unconsolidated · BRSA basis · Qualified (PwC)
```
Built from `comparability` section (Task 2.1, section 9).

**Pass criteria:**
- The badge appears on every per-bank page
- The badge links the opinion type to the `basis_text` paragraph
- If no note exists for this bank's latest quarter, the section shows "Analysis pending"
- The section is a server component — no client-side LLM call

### Task 4.4 — /analyst tab (optional, Phase 4+)

**File:** `web/app/analyst/page.tsx`
**What:** A dedicated page listing all recent analyst notes across banks, with
filters by bank, period, signal type. The "feed" view.

**Priority:** Low. The per-bank page integration (Task 4.3) is more important —
the analyst's natural home is the bank page, not a separate feed.

---

## Phase 5 — Gaps that remain after this build

These are the things the 11-section framework CANNOT answer from stored data,
even after Phase 4 is complete. They are documented here so the agent can say
"not available" rather than guessing.

| Section | Gap | Why |
|---|---|---|
| 3. Earnings | CPI-linked bond income decomposed from net interest | Blended in P&L line items — needs footnote extraction |
| 3. Earnings | Swap/hedging costs separated from net trading | Blended in `5.1`/`5.2` — needs footnote extraction |
| 3. Earnings | Securities duration | Not disclosed in BRSA tables — in annual report notes |
| 4. Asset quality | Stage definitions (SICR triggers, DPD thresholds) | In §3 accounting-policy notes — the A3 gap |
| 4. Asset quality | Restructured loans (separated from performing) | In §5 footnotes — not extracted |
| 4. Asset quality | Collateral type/quality per loan segment | In §5 footnotes — not extracted |
| 5. Currency | Borrower FX exposure (unhedged FX loans) | Bank filings don't carry this at loan level |
| 6. Funding | Deposit concentration (top 10 depositors) | Not in BRSA tables — in annual report |
| 6. Funding | External debt maturity schedule | In §4 footnotes — not extracted |
| 7. Capital | Tangible common equity (goodwill/intangible removed) | BS doesn't separate goodwill — needs footnote |
| 8. Securities | Fixed vs floating vs CPI-linked breakdown | In §4 footnotes — not extracted |
| 8. Securities | Unrealized gains/losses on AFS/AC portfolio | In §4 footnotes — not extracted |
| 10. Governance | Management turnover, guidance vs actuals | Not sourced — needs KAP/IR tracking |
| 11. Valuation | P/B, P/E, dividend yield | BIST prices removed (Yahoo terms) — needs licensed feed |

**Each of these is a footnote-extraction task** — the prose lane
(`bank_audit_prose`) already holds the text (369k rows, 165M chars, local only).
The gap is not "we don't have the documents" — it's "the text is stored but
not structured."

---

## Build order

```
Phase 1  (detectors)  → Task 1.5 (basis metadata) first — everything else
                         (unit change, cross-period, opinion, perimeter)
                         reads its output
                      → Task 1.3a (classify basis_text) second — the
                         qualification atlas is the highest-value dataset
                         nobody else has
                      → Remaining detectors (1.1, 1.2, 1.4, 1.8) in parallel
                      → Task 1.6 (CLI) + 1.7 (D1 tables) last

Phase 2  (data layer) → Task 2.1 (section queries) — the spine, everything
                         depends on it
                      → Task 2.2 (peer context) + 2.3 (comparator) in parallel

Phase 3  (agent)      → Task 3.1 (prompt) + 3.2 (guard) — design before
                         the runner
                      → Task 3.3 (runner) — thin orchestrator
                      → Task 3.4 (calibration test) — the gate before Phase 4

Phase 4  (delivery)   → Task 4.1 (workflow) + 4.2 (/admin) in parallel
                      → Task 4.3 (per-bank page) last — depends on D1 tables
                         having real data
```

**The calibration test (Task 3.4) is the kill point.** If the agent cannot
reproduce the hand-written memos' findings on ALBRK and ŞEKERBANK, do not
proceed to Phase 4. The diagnostic is: does the agent ask the second question
(npl_movement decomposition, CAR−CET1 divergence), or does it report the
printed headline ratios and stop?

---

## What NOT to build (the anti-scope)

- **Not a team of agents.** The external report's own citations show single-agent
  ≥ multi-agent at matched budget. The feasibility test showed the bottleneck
  is asking follow-up questions of data already held, not parallel specialist
  perspectives.
- **Not a LangGraph state machine.** The agent is a single prompt → LLM call →
  grounding guard, not a multi-node graph with cascade cooldowns. The analysis
  is stateless — it reads the assembled sections for one bank/quarter and
  produces one memo.
- **Not a signal-discovery system.** The detectors produce a FIXED set of
  signal types. There is no "dynamic detector generation" or "enricher" that
  provides market context. The model receives structured facts, not raw data.
- **Not a trading recommendation engine.** The memo is a credit/analyst note,
  not an investment call. It never says "buy", "sell", "long", or "short".
- **Not a per-bank chat interface.** The Telegram bot already answers questions.
  The analyst produces a structured memo — it is not a conversation.
- **No per-metric click-through provenance (yet).** ChatGPT's recommendation
  for click-to-see-source per metric is valid but a separate build. The
  comparability badge (Task 4.3) is the first step toward it.

---

## As-built record (2026-08-04, same day)

Implemented through Phase 4 in three commits (`77b92ad`, `914e3f6`, `6e4f920`).
Deviations from the plan above, each deliberate:

- **Task 3.3 location — CI, not the Worker.** Memo generation runs in
  `analyst-daily.yml` via `web/scripts/analyst-run.ts` (node:sqlite over the
  R2 snapshots), importing the SAME `web/app/lib/analyst/` modules the Worker
  reads. Three reasons: the LLM keys are CI secrets by design (none exist
  locally or need to reach a route), batch generation belongs in Actions like
  every other lane, and a Worker-side writer would be a second D1 write path
  outside `push_to_d1.py`'s budget discipline. No `/api/admin/analyst/run`
  route exists; the /admin card is the workflow-dispatch entry in the existing
  Pipeline panel (Task 4.2 trimmed accordingly — the signals/notes browsing UI
  comes with the D1 push at freeze-lift). Task 4.4 (the /analyst feed) is not
  built, as the plan already preferred.
- **Task 1.6 has `--stage`, not `--push`** — there is no push flag at all
  while the freeze stands. Signals + basis metadata stage into
  `data/analyst.db`; how that third staging DB wires into `push_to_d1.py` is a
  freeze-lift decision, recorded in Task 1.7.
- **The guard needed a STRUCTURE gate the plan did not foresee.** Calibration
  round 1: nemotron (the bot's first-choice model) answered the long
  instruction-heavy memo prompt with its own planning monologue, truncated at
  max_tokens — and the ALBRK version PASSED the figure check, because every
  number it echoed was in the data block. Form is a claim too: `guardMemo` now
  requires the headline + all four sections, and the memo lane excludes
  nemotron via `chatComplete`'s new `excludeProviders` (the bot's short SQL
  loop keeps it — the chains differ on purpose). This is the same lesson as
  "the model does not signal doubt", one level up: it does not signal
  off-task either.

## The one number that matters

If the Şekerbank 2026Q1 memo says "NPL ratio improved to 1.33% from 1.70%" and
stops there, the build failed. If it says "NPL ratio fell to 1.33% but Stage 3
coverage collapsed from 69.7% to 48.3%, driven 13.2pp by mix shift into lightly
provisioned buckets and 8.2pp by within-bucket erosion, with zero write-offs
and accelerating new NPL formation in Group III" — the build passed.

That is the "second question" test. Everything in this plan is in service of it.

## Calibration verdict (Task 3.4) — PASSED, five rounds, 2026-08-04

Run via `analyst-daily.yml banks=CALIBRATE` (runs 30903420162 → 30904767159).
Each round's failure became a deterministic harness fix; nothing was fixed by
hoping the model behaves.

- **Round 1 — FAILED, and the failure was the harness.** nemotron answered the
  long instruction-heavy prompt with its planning monologue, truncated at
  max_tokens — and ALBRK **passed the figure guard**, because every number the
  monologue echoed was in the data block. Fixes: a STRUCTURE gate in
  `guardMemo` (headline + all four sections — form is a claim too) and
  `excludeProviders` in `chatComplete` (the memo lane skips nemotron; the
  bot's short SQL loop keeps it).
- **Round 2 — SKBNK passed the kill point**; an "overstated by ₺700 million"
  figure evaded the ≥1000 amount floor (amounts are thousand TL, so a
  million-denominated figure is numerically small). Fix: denomination-scaled
  checking (million ×1e3, bn ×1e6) — which in round 3 turned out to VERIFY the
  claim rather than block it (the ₺700,000k was the auditor's own
  retained-earnings figure, illegible to the guard only by denomination).
- **Rounds 3–5 — the ALBRK second question landed piece by piece, each time by
  moving the derivation into the data** (the coverage-decomposition pattern,
  applied twice more): ex-release profit per FP-history row made the memo
  quote "the 2025Q1 base was inflated by a release = **89.2%** of printed
  profit; YoY comparisons against it are misleading" (round 4), and
  like-quarter pairs in the core-margin rendering made it read the underlying
  series correctly (round 5: "core margin more than double the same quarter a
  year earlier while printed income collapsed −88.5% — the declines are
  overstated; the core series shows genuine improvement", quoting the ₺7.0bn).

**Final state (rounds 3–5, temp 0, free-model chain):**

- **SKBNK 2026Q1: PASS on all four criteria, stable across three rounds.**
  Headline = the CAR/CET1 divergence; coverage fall decomposed from the
  precomputed table (18.94pp = 12.13 mix + 6.81 erosion over the standard
  4-quarter window — the memo's 5-quarter equivalent of the hand memo's
  13.2/8.2); **zero write-offs stated and used causally**; Group III
  formation quoted at the hand memo's exact ₺391,354; a real falsifier
  ("the first non-zero write-off would falsify"). The one-number test above:
  passed as written.
- **ALBRK 2026Q1: all four criteria demonstrated** (release-distortion
  headline in round 4; ₺7.0bn + core-margin reading in round 5), with the
  caveat that a single run leads with ONE of the two legitimate stories
  (capital composition vs release distortion) and carries the other in-body.
- **Residual defects, named:** occasional interpretive gloss errors on
  correctly-grounded figures (round 5 read `noncore_share 0.47` as "only
  0.47%"); signal-payload internals quoted verbatim once; one garbled
  negation. The guard checks figures and form, not semantics — a wrong WORD
  about a right NUMBER is the class it cannot catch. Provider rotation
  (cerebras ↔ groq) adds run-to-run variance at temp 0.

Iteration stopped deliberately after round 5: both hand-memo finding sets are
reproduced, and further prompt-tuning against the same two known memos would
be overfitting the harness (the 22/22 unit-detection lesson). The next real
test is a bank neither the prompt nor the harness was tuned on.

## The untuned test and the story gates (same day, commits `6abb49a`–`3e65b56`)

**GARAN 2026Q1** was that test, and it failed instructively: the memo led with
a capital-composition story on a bank whose CAR−CET1 gap sits AT the class
median (narrative transferred from the calibration banks), skipped the
genuinely strong finding (29.3% nominal ROE = **−1.2% REAL**), and invented a
figure in the forward section — which the guard dropped, correctly failing
the memo.

The cure was the same as every calibration failure — compute the judgment:

- **STORY GATES**, a deterministic editorial layer at the top of the data
  block. Six candidate stories (comparability events, free-provision
  distortion, capital composition, coverage divergence, adverse peer
  deviations, real-terms erosion) each ruled LIVE or DEAD with the numeric
  reason, **ranked** (bank-specific distortions above regime-wide
  conditions), the first live gate marked LEAD. The headline must state the
  LEAD; every live story must get its own paragraph; a dead story gets one
  "notably absent" sentence. The coverage gate carries a data-level fallback
  mirroring the detector thresholds so it holds where `analyst_signals` is
  absent.
- **`capital.ratio_drivers`** — CET1-capital vs RWA growth QoQ/YoY, so "why
  the ratio moved" is a quote (the hand memos' RWA-vs-capital derivation).
- Watch-section thresholds restricted to held figures; a "TL X" template
  placeholder that leaked in one run now drops the paragraph like an
  invented figure; dropped paragraphs persist in the memo artifact.

**Validation across all three banks (run 30906062055, all passing the
guard):** GARAN leads with its peer-deviation story and carries a full
real-terms paragraph plus the correct negative-mix decomposition reading and
"RWA grew 46.1% YoY" causality; ALBRK leads with the free-provision re-base
(ex-release profit quoted, history cited, capital and real-terms each getting
their paragraph, the ratio-drivers used); SKBNK leads with the auditor's own
₺700,000k understatement arithmetic and keeps its full decomposition. Gate
regressions were caught twice in testing before shipping (a signal-only gate
going dead without staged signals; the un-ranked gates letting ALBRK's lead
drift to real-terms).

**Known residuals, deliberately not chased further:** run-to-run variance in
WHICH history figures get quoted (free-model provider rotation at temp 0);
semantic glosses the guard cannot see (a share compared against a
pp-median); occasional stiff phrasing. The structural properties — grounded
figures, correct story selection, complete live-story coverage, structural
abstention — are now enforced, not hoped for.

## The deep-dive and the GO arc (same day, evening — commits `f151bae`…)

The user benchmarked the memo against an external GARAN deep-research
document and asked for that depth. The format became a **13-section research
report** (~2,400 words, tables); where the two overlap, our filings
reproduce the benchmark's figures bank-for-bank (GARAN consolidated: CAR
16.2, CET1 12.0, NPL 3.2, Stage-3 coverage 62.8 — identical). Reaching a
clean pass took removing, one measured failure at a time, every class of
number the model wanted and the data block did not supply — growth percents,
cross-row totals, direction words, outside-knowledge benchmarks — plus one
guard bug (a grouped figure part-matching before a denomination word) and
one dead assumption (no `:free` DeepSeek exists; the PAID flash is now
user-authorized for this lane, Baidu-pinned and seeded).

The "GO" batch then added: ranked story gates with a computed LEAD (cured
narrative transfer measured on the untuned GARAN run), a relation verifier
(a wrong direction word between two right numbers now drops the sentence's
paragraph), per-stage GROSS ECL expense (sums reproduce the disclosed
₺30.5bn for GARAN), verbatim management commentary from the transcripts
lane (executive turns only, claims-not-data framing), hash-gated
regeneration with R2-persisted staging state, a report scorer over run
artifacts, and — the feasibility test's #1 missing dataset — **per-bank
stage definitions extracted from the prose corpus**: 24/38 banks' own
disclosed thresholds (90-day default × 22, explicit 30-day SICR × 11) as a
generated, committed module with verbatim snippets. The stage-comparability
disclaimer now stands only where a bank disclosed nothing parseable.
