# CBRT Financial Stability Report 2026-I — chart inventory & reproducibility map

**Report:** TCMB Finansal İstikrar Raporu 2026-I, published 22 May 2026 (Vol. 42, 81 pp, Turkish full text).
**PDF:** https://www.tcmb.gov.tr/wps/wcm/connect/559f289f-e867-459e-a485-bb8a450da29e/Tam+Metin.pdf?MOD=AJPERES
**Landing (all editions):** https://www.tcmb.gov.tr/wps/wcm/connect/tr/tcmb+tr/main+menu/yayinlar/raporlar/finansal+istikrar+raporu

Purpose: chart-by-chart inventory of the FSR (~140 charts + 12 tables) graded by whether **we**
can reproduce each one on the dashboard. The FSR is the narrative backbone of
[`../sector-story-spine.md`](../sector-story-spine.md); this doc turns its 2026-I edition into a
concrete build-vs-skip map. Assessed 2026-07-02 against the data actually in D1/EVDS
(see "Data assets" below).

**Legend**
- ✅ **already on dashboard** (same metric, possibly different cadence/granularity)
- 🟢 **buildable now** — data already in D1/EVDS, derivation only
- 🟡 **needs new free public source** (EVDS series not yet ingested, TÜİK, Risk Merkezi, BKM, EGM, SEDDK, KAP)
- 🔴 **not reproducible** — supervisory or proprietary micro-data (TCMB bank-by-bank weekly returns,
  Risk Merkezi loan-level, SGK-matched firm data, TMSF deposit registry, Takasbank, Bloomberg/IIF)

**Data assets graded against:** BDDK monthly bulletin (`balance_sheet`/`income_statement`/`loans`/
`deposits`/`financial_ratios`) · BDDK weekly bulletin (`weekly_series`: loans by type, NPL by segment,
securities, deposits incl. KKM, selected BS, off-BS) · EVDS lane (policy/funding rates, **weekly loan
rates TP.KTF\***, **weekly deposit rates TP.TRY.MT01–06**, FX, reserves, household FC deposits
TP.HPBITABLO4.\*, BoP detail TP.ODEAYRSUNUM6.\*, GDP, CPI, Brent) · per-bank audited quarterly
(`bank_audit_capital` — CET1/AT1/T1/T2/total + **total RWA only, no KRET/PRET/ORET split** +
ratios; `bank_audit_liquidity` — LCR/LCR-FC/NSFR/leverage; `bank_audit_fx_position`;
`bank_audit_repricing`; `bank_audit_stages` + `bank_audit_credit_quality`; `bank_audit_npl_movement`;
BS/P&L/OCI/CF) · TEFAS (`tefas_*`) · `nonbank_balance_sheet` · BIST lane.

---

## II. Küresel Finansal Görünüm — Global outlook (13 charts + 2 boxes)

Sources: Bloomberg, FRED, IIF, World Gold Council, Caldara & Iacoviello GPR. **Verdict: skip.**
Paywalled/foreign sources and out of dashboard scope (we are a TR banking dashboard, not a global
macro monitor).

| Chart | Title | Grade | Note |
|---|---|---|---|
| II.1–II.2 | Geopolitical Risk index; VIX | 🔴 | GPR index is actually free (Iacoviello site) but out of scope |
| II.3–II.5 | Brent/LNG/metals; fertilizer & food; gold & silver | 🔴/🟢 | Brent already ingested (TP.BRENTPETROL, on /economy); rest skip |
| II.6–II.13 | DM/EM bond yields, policy-rate expectations, DXY, EM CDS, implied FX vol, EM fund flows | 🔴 | Bloomberg/IIF |
| Box II.1 (Tablo II.1.1–2) | Geopolitical risk → credit market regressions | 🔴 | research box, firm-level |
| Box II.2 (II.2.1–2, Tablo II.2.1) | Central-bank gold demand; TCMB gold reserves | 🟢 partial | TCMB gold reserves available in EVDS reserve series if ever wanted |

## III.1 Hanehalkı — Households (18 charts, 2 tables, 1 box)

| Chart | Title | Grade | Note |
|---|---|---|---|
| III.1.1–4, Tablo III.1.1 | Household debt/GDP (level, peers, composition) | 🟢 | consumer loans + cards (weekly/monthly, have) ÷ nominal GDP; verify a **nominal** GDP series is ingested (chain-volume TP.GSYIH\* is); peers 🔴 (IIF) |
| III.1.5–6 | Average maturity of retail loan types | 🔴 | Risk Merkezi loan-level |
| III.1.7 | Credit-card balance left to interest | 🟡 | Risk Merkezi/BKM monthly public stats (new scrape) |
| III.1.8–9 | Credit-card & overdraft (KMH) limit vs balance/utilization | 🟡 | Risk Merkezi monthly public |
| III.1.10, III.1.14 | Housing loan flow & stock | ✅ | /credit (weekly loans by type) |
| III.1.11 | House sales (TÜİK) | 🟡 | EVDS has TÜİK house-sales series — not yet ingested |
| III.1.12 | House prices (KFE) vs construction cost index, y/y | 🟡 | EVDS has KFE + construction cost — not yet ingested; natural /economy addition |
| III.1.13, III.1.15 | Vehicle loans vs first-hand car sales | 🟢/🟡 | loans ✅; car sales = ODMD/EGM (new source) |
| Tablo III.1.2, III.1.16–17 | Household financial assets (level, /GDP, mix) | 🟢 partial | deposits ✅, TEFAS funds ✅, FC/precious-metal deposits ✅ (TP.HPBITABLO4); equities (MKK) + pension (EGM) 🟡 |
| III.1.18 | Non-deposit assets & investor counts | 🟡 | MKK investor counts + BES participants |
| Box III.1.I (I.1–I.3) | Deposit distribution by size bucket (montan), FX share by bucket | 🔴 | TMSF/BDDK internal registry |

## III.2 Reel Sektör — Non-financial corporates (16 charts, 3 tables)

| Chart | Title | Grade | Note |
|---|---|---|---|
| III.2.1–2, Tablo III.2.1 | Corporate financial debt/GDP, TL vs FX | 🟢 partial | domestic loans ✅; external-loan component 🟡 (EVDS private-sector external debt) |
| III.2.3–4 | Peer-country corporate leverage | 🔴 | IIF |
| III.2.5–6 | External-debt rollover ratio; foreign loans & bond issuance | 🟢 approx | derivable from BoP detail already ingested (TP.ODEAYRSUNUM6 corporate loan/bond flows) |
| III.2.7–8 | Corporate debt/assets, debt & asset growth | 🔴 | TCMB firm-level dataset |
| **III.2.9–11** | **Corporate FX position (net, natural-hedge adjusted, short-term)** | 🟡 | EVDS publishes the full "FX assets & liabilities of non-financial companies" dataset monthly — highest-value new ingest in Section III; fits /economy |
| III.2.12 | Short-term FX credit flow | 🟢 approx | weekly FX loans + BoP flows |
| III.2.13–14 | Loan share by firm size (employees) | 🔴 | SGK-matched micro |
| Tablo III.2.2, III.2.15–16 | Corporate deposits (/GDP, TL share) | 🟢 | deposits tables carry the commercial split |
| Tablo III.2.3 | BIST non-financial firms: profitability/liquidity/leverage under inflation accounting | 🔴 | out of scope (we cover banks; source is firm financials aggregation) |

## IV.1 Kredi Gelişmeleri ve Kredi Riski — Credit & asset quality (35 charts + 1 box)

Our sweet spot: everything TCMB builds here from supervisory weekly data has a public shadow in
the BDDK weekly bulletin (already in `weekly_series`) or in our audited per-bank tables.

| Chart | Title | Grade | Note |
|---|---|---|---|
| IV.1.1–3 | Loan rates: TL commercial, FX commercial, housing/consumer/card | ✅/🟡 | TL sets on /rates (TP.KTF\*); FX commercial rate = trivial EVDS add |
| IV.1.4 | Max card/KMH rates (TCMB-set) | 🟡 | trivial (TCMB announcement series) |
| IV.1.5–7 | Installment commercial loan rate detail | 🔴 | flow micro-data |
| **IV.1.8–15** | **Credit growth: total, commercial/retail, SME, TL/FX — 13-week annualized, FX-adjusted (KEA)** | 🟢 | `weekly_series` loans by type + USD/TRY for FX adjustment. We only show monthly/yoy today; this momentum view is the FSR/market standard |
| IV.1.16–17 | Share of loans subject to growth caps | 🔴 | ZK-exemption classification is internal |
| IV.1.18–22 | Segment growth: consumer ex-KMH, KMH, cards, housing, vehicle | 🟢 | weekly consumer sub-splits |
| IV.1.23–24, IV.1.27 | Asset quality: NPL ratio total & by loan type | ✅ | /asset-quality (weekly NPL by segment) |
| IV.1.25 | Stage-2 (yakın izleme) loan share | 🟢 | aggregate `bank_audit_stages` (quarterly vs FSR monthly) |
| IV.1.26 | Overdue share within Stage 2 | 🔴 | supervisory |
| IV.1.28 | Stage-2 composition (restructured / refinanced / other) | 🟢 partial | `credit_quality` captures restructured sub-rows where banks disclose them |
| **IV.1.29** | **NPL-ratio change contributions (new NPL / live-loan growth / FX effect), 3 panels: total, retail, commercial** | 🟢 | derivable: `npl_movement` inflows + loan growth + FX effect |
| **IV.1.30** | **NPL flow components: additions / collections / write-offs (3 panels)** | 🟢 | **direct match** — `bank_audit_npl_movement` roll-forward aggregated to sector; we hold it per-bank, richer than the FSR |
| IV.1.31 | Loan-group transition rates (1→2, 2→3, cure) | 🔴 | supervisory transition matrix |
| IV.1.32 | Protested bills & bounced cheques ratio | 🟡 | Risk Merkezi public stats (EVDS carries protested-bill series) |
| IV.1.33 | Defaulted-bond ratio | 🟡 | KAP/MKK; low value — skip |
| IV.1.34 | Restructured-loan ratios | 🟢 partial | as IV.1.28 |
| IV.1.35 | Provision (ECL) coverage by stage | ✅/🟢 | total coverage on /cross-bank & /asset-quality; per-stage coverage from `credit_quality` ECL by stage |
| Box IV.1.I (Tablo I.1–2, I.1–4) | Banking-sector gold balance sheet; gold-price shock → FX loans/rates | 🟢 partial | precious-metal deposit lines exist (monthly/weekly); loan-side gold split & event study 🔴 |

## IV.2 Likidite Riski — Liquidity & funding (21 charts + 1 box)

| Chart | Title | Grade | Note |
|---|---|---|---|
| IV.2.1–2 | Liquid assets share; selected liquid items | 🟢 | monthly BS lines (cash, CBRT, repo receivables, securities) |
| IV.2.3 | LCR total & FX (4-week MA) | ✅ | /liquidity shows audited quarterly per-bank + sector; FSR's weekly cadence is supervisory-only |
| IV.2.4 | Loan/deposit ratio (total, TL, FX, with LT averages) | ✅ | /liquidity (TL/FC LDR) |
| IV.2.5 | TCMB funding (OMO + swaps) | ✅ | /liquidity (TP.APIFON\*) |
| IV.2.6–7 | TL deposit rate vs policy rate; 1–3M deposit rate | ✅ | /rates (TP.TRY.MT\*) |
| IV.2.8–12 | Deposit growth TL/FX, savings vs commercial, mix, TL share (incl. KKM wind-down) | ✅ | /deposits |
| IV.2.13 | Banks' TL funding from abroad (swap book) | 🔴 | TCMB internal swap data |
| IV.2.14 | Banks' external debt stock & share | 🟢 approx / 🟡 | monthly BS "payables to banks" lines approximate; precise = EVDS external-debt stats |
| IV.2.15 | Geographic split of external borrowing | 🔴 | supervisory |
| IV.2.16 | External-debt rollover ratio | 🟢 approx | BoP banking-sector loan flows (already ingested) |
| IV.2.17 | Eurobond & subordinated (SBB) stock | 🟢 approx / 🟡 | audit BS "securities issued" line; per-issue detail = KAP |
| IV.2.18–19 | Syndication rollover & spreads | 🔴 | spreads Bloomberg; rough rollover trackable via KAP filings 🟡 |
| IV.2.20–21 | FX liquid assets; vs short-term external debt | 🟡 | reserves + short-term external-debt series (EVDS, not ingested) |
| Box IV.2.I | Distribution of banks by net liquidity position vs TCMB; effect on loan rates | 🔴 | bank-by-bank TCMB transaction data |

## IV.3 Faiz ve Kur Riski — Interest-rate & FX risk (24 charts)

Maps onto our /market-risk lane (CAMELS "S").

| Chart | Title | Grade | Note |
|---|---|---|---|
| IV.3.1 | TL sovereign (DİBS) yield curve | 🟡 | EVDS DIBS yields — already on `data-gaps-roadmap.md` |
| IV.3.2 | DİBS–OIS spread | 🔴 | OIS = Bloomberg |
| IV.3.3 | Rate changes across instruments in selected windows | 🟢 | composite of series we hold |
| IV.3.4–6 | TL loan–deposit spread, flow & stock | ✅/🟢 | stock = margin engine (per-bank!); flow spread = trivial derivation on /rates |
| IV.3.7–9 | Weighted average maturity of assets/liabilities, TL & FX | 🔴 | supervisory |
| IV.3.10–11, IV.3.13 | Fixed-rate share of TL loans/securities; remaining maturity | 🔴 | supervisory |
| IV.3.12 | Securities/assets share | 🟢 | monthly BS + weekly securities table |
| **IV.3.14–15** | **TL & FX asset-liability repricing gap by bucket (0–1M, 1–3M, 3–6M, 0–6M band)** | ✅ | /market-risk from `bank_audit_repricing` (quarterly vs FSR monthly; per-bank granularity is our edge) |
| IV.3.16–17 | BHFOR (IRRBB standard ratio) level + kernel density | 🔴 | supervisory (not in public §4 disclosures) |
| IV.3.18 | Banks' FX position (on/off-BS, NOP) | ✅ | /market-risk (`bank_audit_fx_position`) |
| IV.3.19 | Asset share of banks by NOP/equity bucket | 🟢 | per-bank NOP + equity + assets → bucket-weighted distribution; nice dispersion view |
| IV.3.20–24 | On-BS FX assets/liabilities change; off-BS net FX position & change | 🟢 | decomposition variants of data we hold |

## IV.4 Kârlılık ve Sermaye Yeterliliği — Profitability & capital (15 charts)

Strongest overlap; most charts are aggregations of audited statements we already extract per-bank.

| Chart | Title | Grade | Note |
|---|---|---|---|
| IV.4.1 | ROE & ROA (12M) | ✅ | /profitability |
| **IV.4.2** | **ROE distribution × asset share (dispersion)** | 🟢 | per-bank TTM ROE + asset share — direct /cross-bank addition |
| **IV.4.3–4** | **ROA decomposition: NII / fees / cost of risk / opex-personnel / trading / other (annual & quarterly stacked bars with net marker)** | 🟢 | audit P&L aggregates; margin engine already computes CoR & PPOP — flagship FSR chart form |
| IV.4.5–6 | NIM (12M) + components (loan & securities yield vs deposit & other funding cost) | ✅/🟢 | NIM in margin engine; component stack derivable from P&L interest lines |
| IV.4.7 | Cost of risk | ✅ | margin engine |
| IV.4.8–9 | Fees & commissions: level, opex coverage; product composition | 🟢/🔴 | level + fee/opex ratio from P&L ✅ derivable; product split (payments vs lending) not in P&L detail |
| IV.4.10–11 | CAR & CET1 (reported and ex-forbearance) | ✅/🔴 | reported ratios on /capital (monthly sector + audited per-bank); "BDDK esneklikleri hariç" variant is TCMB-computed |
| IV.4.12 | CAR change contributions (profit, SBB, valuation, FX, KRET/PRET/ORET) | 🟢 partial | from `bank_audit_capital` components: profit→CET1, SBB→T2, ΔRWA total. **Schema stores total RWA only — no credit/market/op split**, so the RWA leg collapses to one bar |
| IV.4.13 | Own-funds composition (profit+reserves, paid-in, SBB, revaluation, other) | 🟢 | capital components stored |
| IV.4.14–15 | Excess capital buffer (%, and trillion TL; sector vs D-SIB vs other) | 🟢 approx | CAR − requirement; hardcode public D-SIB buffer buckets; per-bank data is our edge |

Also **Tablo IV.5.1** (macroprudential measures & regulations timeline) — overlaps /regulation
briefings; cross-reference only.

## V. Banka Dışı Finansal Kesim — Non-bank financial sector (12 charts, 3 tables)

| Chart | Title | Grade | Note |
|---|---|---|---|
| V.1–V.2, Tablo V.1 | Financial-sector size /GDP; intl comparison (FSB) | 🟢 partial | banks + non-bank lane + TEFAS ÷ GDP; insurance 🟡 (SEDDK); FSB comparison 🔴 |
| V.1.1–3, Tablo V.1.1 | Fund AUM & counts by type; mutual-fund growth | ✅ | /funds (TEFAS) |
| V.1.4 | Pension funds | 🟡 | EGM/BEFAS public weekly data (new ingest) |
| V.1.5–6 | TL vs FX mutual-fund portfolio allocation | 🟢 | `tefas_allocation_daily` (needs TL/FX fund-category mapping) |
| V.1.7–8 | Money-market-fund AUM; MMF return vs TL deposit rate | 🟢 | TEFAS category AUM/returns + deposit-rate series |
| V.1.9–10 | Banks' TL/FX liabilities sourced from funds | 🔴 | Takasbank |
| V.2.1–5 | Other NBFIs (leasing/factoring/financing): assets/GDP, currency & product composition | ✅/🟢 | /non-bank (`nonbank_balance_sheet`); verify TL/FX split coverage for the currency-composition charts |

---

## Headline conclusions

1. **The core banking sections (IV.1–IV.4) are largely within reach.** Roughly half of the FSR's
   banking charts are already on the dashboard or derivable from data already in D1 — often at
   **per-bank granularity the FSR itself never shows** (it publishes sector aggregates from
   supervisory data; we aggregate up from audited statements).
2. **Best exact-match gaps** (🟢, no new sources): NPL flow & contribution decomposition
   (IV.1.29–30 ← `bank_audit_npl_movement`), 13-week annualized FX-adjusted credit growth
   (IV.1.8–22 ← `weekly_series`), ROA decomposition (IV.4.3–4 ← audit P&L), capital-buffer /
   own-funds charts (IV.4.12–15 ← `bank_audit_capital`), stage-2 & stage-coverage views
   (IV.1.25/28/35), ROE dispersion (IV.4.2).
3. **Highest-value new ingests** (🟡, all free): corporate FX position (III.2.9–11), KFE house
   prices + house sales (III.1.11–12), protested bills/cheques (IV.1.32), DIBS yield curve
   (IV.3.1), pension funds (V.1.4), banks'/corporates' external-debt stats.
4. **Structurally out of reach** (🔴): balance-sheet maturity & fixed-rate structure (IV.3.7–13),
   BHFOR/IRRBB, loan transition matrices, deposit size distribution, syndication spreads,
   liquidity-position distributions, firm-level real-sector metrics, Bloomberg/IIF global charts.
   Don't chase these; the FSR is the only public window on them (cite it instead).

## Recommended follow-ups (priority order, not yet built)

All 🟢 no-new-source dashboard additions:
1. **NPL flow components + NPL-ratio contribution chart** on /asset-quality (`bank_audit_npl_movement`)
2. **13-week annualized (FX-adjusted) credit growth** on /credit (`weekly_series`)
3. **ROA decomposition stacked bars** on /profitability (audit P&L)
4. **Stage-2 share + stage-level coverage** on /asset-quality (`bank_audit_stages`/`credit_quality`)
5. **Excess-capital buffer + own-funds composition** on /capital (`bank_audit_capital`)
6. **ROE-dispersion × asset-share view** on /cross-bank

Then a 🟡 ingest wave for /economy: corporate FX position, KFE + house sales, protested bills.

Chart-form notes (FSR house style, useful when building): three-panel small multiples
(Toplam/Bireysel/Ticari), signed stacked contribution bars with net marker, horizontal
waterfall for CAR contributions, 100% stacked composition, banded line charts for repricing
buckets (0–6M band + bucket lines), dashed long-term-average reference lines on ratio charts.

Verification anchors if follow-ups are built (printed 2026-I values): 2026Q1 NPL additions
≈165 bn TL, collections ≈32.3 bn TL (commercial) / 33 bn TL (retail), sector excess capital
buffer ≈1.7 trn TL, NIM (quarterly, annualized) ≈6.6% in Mar 2026, TL 0–6M repricing gap
≈−2.9% of assets, FX 0–6M surplus ≈+46 bn USD.
