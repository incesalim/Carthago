# Audit-report extraction coverage — what a BRSA report holds vs. what we extract

**Date:** 2026-07-15 · **Status:** 📋 REFERENCE (coverage snapshot; no code change) · **Memory:** [[reference_audit_report_full_structure]]

## What prompted it

"Can you [map] every table and information that can be extracted from an audit
report vs. what we extract." A full-coverage census, verified against current
code (`src/audit_reports/registry.py`), the corpus census in
`docs/AUDIT_BANK_CATALOG.md`, and the gap docs — not the older memory note,
which was stale on two points (see *Corrections*).

## Bottom line

We hold the **numeric backbone**: primary statements + key prudential ratios +
IFRS-9 credit quality, plus two targeted screens (audit opinion, free provision).
Everything narrative (§1/§3/§6/§7 text) and most §5 line-item footnotes are
untapped. Concretely: **17 registered statement types → 16 D1 tables, + 1
screen** (`bank_audit_free_provision`). The report contains dozens more tables
and ~25 qualitative note-sets we don't touch.

Extraction is deterministic — PyMuPDF/fitz + heading anchors + labelled rows,
**no LLM API** ([[feedback_extractors_no_api]]). 14 of the 17 types carry a
structural validator.

## The 7-section (Bölüm) report, section by section

| § | Section contents | We extract | D1 table |
|---|---|---|---|
| **§1 General information** | Establishment, capital history, shareholders, board/management, **branch & personnel counts**, consolidation scope | ✅ branches / personnel only | `bank_audit_profile` |
| **§2 Financial statements** | Balance sheet, off-balance, P&L, OCI, changes in equity, cash flow, **profit-distribution table** | ✅ BS assets, BS liabilities, off-balance, P&L, OCI, equity-change, cash-flow · ❌ profit-distribution (Kâr Dağıtım) | `bank_audit_balance_sheet`, `bank_audit_profit_loss`, `bank_audit_oci`, `bank_audit_equity_change`, `bank_audit_cash_flow` |
| **§3 Accounting policies** | ~25 qualitative sub-notes (basis of presentation, ECL methodology, tax, leasing, derivatives, segment policy…) | ❌ nothing (narrative, no tables) | — |
| **§4 Financial structure & risk** | Capital adequacy, liquidity/leverage, **FX position**, **repricing/IRRBB**, + ~9 more risk disclosures | ✅ capital (CET1/AT1/Tier1/Tier2/Total, RWA, ratios), liquidity (LCR/NSFR/leverage), FX net open position, interest-rate repricing gap | `bank_audit_capital`, `bank_audit_liquidity`, `bank_audit_fx_position`, `bank_audit_repricing` |
| **§5 Notes to statements** (largest) | Every line-item note: credit quality/stages, NPL movement, loans-by-sector, fees, deposits, derivatives, related-party, maturity ladder, **free provision**… | ✅ credit_quality (IFRS-9), stages (derived), NPL movement, loans-by-sector (annual-only), + free-provision screen | `bank_audit_credit_quality`, `bank_audit_stages`, `bank_audit_npl_movement`, `bank_audit_loans_by_sector`, `bank_audit_free_provision` |
| **§6 Other explanations** | Incl. **credit-ratings summary** (Moody's/Fitch/S&P long/short-term + outlook) | ❌ nothing | — |
| **§7 Independent auditor's report** | Full opinion/review text and its basis | ✅ opinion *type* (clean / qualified / adverse / disclaimer), not full text | `bank_audit_opinion` |

## The 17 registered types (`src/audit_reports/registry.py`)

- **Core** (gate `bank_audit_extractions.success`): BS assets · BS liabilities · Income statement (P&L)
- **Other §2:** OCI · changes in equity · cash flow · off-balance sheet
- **§4 risk:** capital adequacy · liquidity (LCR/NSFR/leverage) · FX net open position · repricing gap (IRRBB)
- **§5 notes:** IFRS-9 credit quality · IFRS-9 stages (derived) · loans by sector (Q4-only) · NPL movement
- **Screens (not in registry):** bank profile (branches/personnel) · audit opinion · free provision (`bank_audit_free_provision`, per [[project_albrk_free_provision_finding]])

Note: BS assets / BS liabilities / off-balance are three registered types that
share one table (`bank_audit_balance_sheet`, `statement` column). That's why 17
types → 16 tables.

## Detected-but-NOT-parsed (profiler finds the anchor; no extractor writes it)

From the `§4/§5 table inventory` census in `docs/AUDIT_BANK_CATALOG.md`. The
profiler (`src/audit_reports/profiler.py`) counts these anchors across all 975
reports. Four are found in most reports and remain unextracted — each is one
extractor away:

| Table | Present in | Why it's worth having |
|---|---|---|
| **Fees & commissions** (`fn_fees_commissions`) | **100%** | fee-income detail below the P&L line; feeds non-interest-income analysis |
| **Liquidity maturity ladder** (`fn_liquidity_maturity`) | **99%** | contractual maturity of assets/liabilities — distinct from the LCR/NSFR *ratios* we already hold |
| **Business segments** (`fn_segment`) | **89%** | revenue/assets by segment (retail/corporate/treasury) |
| **Related-party / risk-group** (`fn_related_party`) | **56%** | intra-group exposures |

The other 8 profiler anchors are already extracted: `fn_credit_stages` →
credit_quality/stages, `fn_fx_position` → fx_position, `s4_capital` → capital,
`s4_leverage` + `s4_liquidity` → liquidity, `fn_interest_rate_risk` → repricing,
`fn_npl_movement` → npl_movement, `fn_loans_by_sector` → loans_by_sector.

## Completely untapped (not even anchor-tracked)

- **§1:** capital history, shareholder list, board/management (ownership + subsidiaries come from a *separate* KAP scrape, [[reference_kap_ownership_scrape]], not this report)
- **§2:** profit-distribution table (Kâr Dağıtım Tablosu)
- **§3:** all ~25 accounting-policy notes (ECL methodology, tax, leasing, derivatives policy, segment policy…) — narrative, no tables
- **§4:** ~9 more risk disclosures — credit risk by geography/sector/rating, counterparty credit risk, securitisation, market risk, operational risk, equity-position risk, fair-value hierarchy, fiduciary/on-behalf, Basel RWA-by-risk-type + remuneration
- **§5:** bulk of line-item notes — deposits by type/maturity, loans by type, securities detail, derivatives detail, subsequent events
- **§6:** credit-ratings summary (agency ratings + outlook)
- **§7:** full auditor's-report *text* (we keep only the classified verdict)

## Corrections to the prior memory note

The 2026-07-04 `reference_audit_report_full_structure` memory was stale on two
points, corrected here and in the memory file:

1. **Fees & commissions is NOT extracted.** The old note listed it under §5 ✅.
   In fact `fn_fees_commissions` is only *detected* by the profiler (100% of
   reports) — no extractor writes it to D1 (no `bank_audit_fees*` table exists).
2. **FX position and interest-rate risk ARE now extracted.** The old note's
   "detected-but-unparsed" list still included `fn_fx_position` and
   `fn_interest_rate_risk`; the market-risk lane shipped them as
   `fx_position` + `repricing` on 2026-06-27 ([[project_market_risk_lane]]).

## Next candidates (if we extend coverage)

Highest-value untapped, by coverage × analytical use: **fees & commissions**
(100% coverage, feeds fee-income mix) and **related-party** (governance/risk
signal). Both fit the existing fitz-anchor pattern — a new extractor + registry
entry + push wiring, no new infra ([[reference_engine_strategy]]).

## Related docs

- `src/audit_reports/registry.py` — the authoritative list of what we extract
- `docs/AUDIT_BANK_CATALOG.md` — per-bank quirks + the §4/§5 anchor census
- `docs/MISSING_AUDIT_DATA.md` — which (bank, period) cells are missing within the extracted set
- `reference_audit_report_full_structure` (memory) — the durable one-line version
