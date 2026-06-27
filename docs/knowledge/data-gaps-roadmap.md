# Data-gaps roadmap — the "drivers behind the outcomes"

A banking-strategist gap analysis (2026-06-20). The platform is rich in **outcome**
metrics (ROE, ROA, NIM, NPL, CAR, P/B) and **macro** context (the EVDS suite) but
was thin on the **drivers** that explain those outcomes at the bank level. This
doc records what shipped and what is groundwork-only, so the deferred lanes are
ready to build without re-deriving the analysis.

Companion: each metric below is classified in
`data/metric_knowledge/registry.json` (query with `scripts/metric_knowledge.py
--show <id>`).

## Tier A — SHIPPED (derived from data already in D1)

No new ingestion; pure derivations off the audited `bank_audit_*` tables.

| Metric | Where | Definition |
|---|---|---|
| Loan yield, deposit cost, spread | `web/app/lib/heatmap.ts` | TTM interest on loans (P&L `1.1`) ÷ avg gross loans (BS `2.1`); TTM interest on deposits (P&L `2.1`) ÷ avg deposits (BS `I.`); yield − cost |
| Cost of risk | same | TTM ECL provisions (P&L `IX.`, magnitude) ÷ avg gross loans |
| PPOP / assets | same | TTM (gross operating profit `VIII.` − \|opex `XI.`+`XII.`\|) ÷ avg total assets |
| Market share (assets/loans/deposits), HHI, league table | `web/app/lib/market-share.ts` | bank ÷ Σ reporting banks per quarter; Σ shareᵢ²×10⁴ |

Surfaced on `/cross-bank` (new heatmap columns + a Market-share/HHI block) and on
`/banks/[ticker]` (a **Performance** section: margin bridge + share trend).

All on a **TTM / 5-point-average-balance** basis (matching the ROE convention,
`reference_roe_ttm_definition`). Shares are "of reporting banks" (~98% of sector),
not the BDDK aggregate — same source for numerator and denominator avoids the
audit-vs-bulletin unit/timing mismatch and the bank-type double-count trap.

## Tier A.2 — SHIPPED 2026-06-27 (the §4 market-risk lane, formerly Tier B)

The two market-risk gaps below were the dashboard audit's **P0** (CAMELS "S"
unhomed). Both are now deterministic per-bank extractors in the audit lane,
surfaced on the new `/market-risk` tab (spine S8).

| Metric | Table / extractor | Definition |
|---|---|---|
| FX net open position | `bank_audit_fx_position` / `src/audit_reports/fx_position.py` | §4 currency-risk footnote, per currency (EUR/USD/OTHER/TOTAL); net_position = net_on_balance + net_off_balance. ~99% coverage. |
| Interest-rate repricing gap | `bank_audit_repricing` / `src/audit_reports/repricing.py` | §4 interest-rate-risk footnote, per bucket (lt_1m…gt_5y/non_sensitive/total); gap = reported total position, cumulative_gap derived. ~81% coverage (participation banks omit). |

Footing identities validated in `validator.py` (`check_fx_position` /
`check_repricing`). The original Tier-B scoping is kept below for history.

## Tier B — GROUNDWORK ONLY (needs new extraction from reports we already ingest)

The data lives in the quarterly BRSA PDFs but in **narrative §4 footnote tables**
currently dumped unstructured into `other_data`. Deterministic extractors only
(pdfplumber/fitz anchors — no LLM, per `feedback_extractors_no_api`).

### FX net open position (`fx_net_open_position`) — ✅ SHIPPED (see Tier A.2)
- **Why it matters:** the single biggest risk lens for TR banks; dollarization +
  the regulatory NOP limit. We hold the TL/FC split of *stocks* but not the *net*
  position (on + off balance, net of FX derivatives).
- **Source:** §4 market-risk footnote — the currency-risk table (YP varlıklar /
  yükümlülükler / net bilanço pozisyonu / net nazım hesap pozisyonu) + the
  off-balance/derivatives tables (BDDK monthly Table 14 has a sector analogue).
- **Proposed schema:** `bank_audit_fx_position(bank_ticker, period, kind,
  currency, on_bs_assets, on_bs_liab, off_bs_long, off_bs_short, net_position,
  period_type)` — one row per major currency (USD/EUR/other) + total.
- **Extractor:** new `src/audit_reports/fx_position.py`, fitz anchor on the
  currency-risk heading; validate net = (assets+offlong) − (liab+offshort) and the
  per-currency rows sum to total.
- **Effort/risk:** medium. Table layout varies (per-currency columns vs rows);
  participation banks word it differently. Wire into `reextract_statement.py`.

### Interest-rate repricing / maturity gap (`repricing_gap`) — ✅ SHIPPED (see Tier A.2)
- **Why it matters:** asset-liability mismatch — how a rate move repriced the book;
  the duration story behind NIM moves.
- **Source:** §4 interest-rate-risk footnote (faize duyarlılık) + the liquidity
  maturity-ladder schedule, by bucket (<1m, 1–3m, 3–12m, 1–5y, >5y, non-sensitive).
- **Proposed schema:** `bank_audit_repricing(bank_ticker, period, kind, bucket,
  rate_sensitive_assets, rate_sensitive_liab, gap, cumulative_gap, period_type)`.
- **Extractor:** new module, anchor on the bucket header row; validate gap = RSA −
  RSL and cumulative = running sum.
- **Effort/risk:** medium-high. Wide many-column table; bucket labels vary.

## Tier C — GROUNDWORK ONLY (needs a new external source)

### Credit ratings history (`credit_rating`)
- **Why it matters:** market view of creditworthiness; rating actions move funding
  cost and are catalysts.
- **Source:** agency press releases (Fitch / Moody's / S&P / JCR Eurasia / SAHA) +
  KAP rating disclosures. The `docs/knowledge/external-reports/` catalog links the
  agencies (links only, no data).
- **Proposed schema:** `bank_ratings(bank_ticker, agency, rating_type, grade,
  outlook, action, action_date, source_url)` — a rating-**events** table.
- **Approach:** scrape/parse agency press + KAP; a per-agency scale map normalises
  grades to a numeric ladder for comparison. Sovereign ceiling caps most.
- **Effort/risk:** medium. Scales differ by agency (`provider_varies`); cadence is
  adhoc. Start with KAP rating disclosures (already a source we scrape).

### Sovereign yield curve / real rate (`sovereign_yield_curve`)
- **Why it matters:** the risk-free curve banks price against; real rate = policy
  stance; benchmark for valuation discount rates.
- **Source:** some benchmark government-bond yields are in **EVDS** (drop into
  `evds_scraper.py`); the full curve + CDS/OIS are market data.
- **Approach:** add the EVDS benchmark-yield series; derive the real rate as
  nominal − CPI expectation (we already hold CPI expectations).
- **Effort/risk:** low for the EVDS subset; **CDS/OIS stay out of scope**
  (Bloomberg/OTC, paywalled — see the `/economy` "out of scope" note).

## Explicitly out of scope (paywalled / proprietary)

CDS spreads, OIS pricing, analyst price targets, foreigners' positioning flows,
and per-bank *advertised* rates (no official feed) — documented in
`reference_per_bank_rate_sources` and the `/economy` page footnote.
