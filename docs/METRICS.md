# Metrics Catalogue

Authoritative reference for every metric in the data pipeline. Lists
the **source** (BDDK table / EVDS series / derived formula), the
**unit**, the **frequency**, and **where** it surfaces in the
dashboard.

> Implementation lives in
> [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts) (TypeScript
> helpers reading directly from Cloudflare D1). Per-bank queries are in
> [`web/app/lib/audit.ts`](../web/app/lib/audit.ts). EVDS scraping is
> in [`src/scrapers/`](../src/scrapers/).

---

## Contents

- [1. Data sources](#1-data-sources)
- [2. Bank-type taxonomy](#2-bank-type-taxonomy)
- [3. Currency & time conventions](#3-currency--time-conventions)
- [4. Balance-sheet levels](#4-balance-sheet-levels) (`balance_sheet`)
- [5. Loan portfolio](#5-loan-portfolio) (`loans`)
- [6. Deposits & funding](#6-deposits--funding) (`deposits`)
- [7. Published ratios — BDDK Table 15](#7-published-ratios--bddk-table-15) (`financial_ratios`)
- [8. Derived / transformed metrics](#8-derived--transformed-metrics)
- [9. EVDS macro & interest rate series](#9-evds-macro--interest-rate-series)
- [10. Weekly BDDK series](#10-weekly-bddk-series) (`weekly_series`)
- [11. Weekly growth transforms](#11-weekly-growth-transforms)
- [12. Where each metric appears in the dashboard](#12-where-each-metric-appears-in-the-dashboard)
- [13. TBB digital-banking statistics](#13-tbb-digital-banking-statistics) (`tbb_digital_stats`)

---

## 1. Data sources

| Source | Content | Frequency | Table / Endpoint | Coverage in DB |
|---|---|---|---|---|
| BDDK monthly bulletin — Table 1 | Balance sheet | Monthly | `balance_sheet` | 2020-01 → 2026-02 |
| BDDK — Table 2 | Income statement | Monthly | `income_statement` | same |
| BDDK — Tables 3–7 | Loans (maturity, consumer, sectoral, SME, syndication) | Monthly | `loans` | same |
| BDDK — Tables 9–10 | Deposits (by type, by maturity) | Monthly | `deposits` | same |
| BDDK — Tables 15 & 17 | Regulator-published ratios & foreign-branch ratios | Monthly | `financial_ratios` | same |
| BDDK — Tables 8,11–14,16 | Securities, liquidity, capital adequacy detail, FX pos., off-balance | Monthly | `other_data` | same |
| BDDK — raw JSON (monthly) | Cache of every monthly API response | — | `raw_api_responses` | same |
| BDDK weekly bulletin | Weekly aggregates (loans, NPL, deposits, securities, etc.) | Weekly | `weekly_series`; endpoint `POST /BultenHaftalik/tr/Home/KiyaslamaJsonGetir` | 2024-01-26 → 2026-04-10 (116 weeks) |
| BDDK — raw JSON (weekly) | Cache of every weekly API response | — | `raw_weekly_responses` | same |
| TCMB EVDS v3 | Interest rates, FX, CPI, reserves | Daily/Weekly/Monthly | evds3.tcmb.gov.tr/igmevdsms-dis | cached in `evds_series` via [evds_scraper.py](../src/scrapers/evds_scraper.py) |
| TBB digital-banking report | Sector digital/internet/mobile banking stats | Quarterly | `tbb_digital_stats`; tbb.org.tr `.xls`/`.xlsx` workbook | 2019-Q1 → latest, via [update_tbb_digital.py](../scripts/update_tbb_digital.py) (see §13) |
| TBB acquisition report | Remote (digital) vs branch customer acquisition | Monthly | `tbb_acquisition_stats`; tbb.org.tr `.xlsx` workbook | 2021-05 → latest, via [update_tbb_acquisition.py](../scripts/update_tbb_acquisition.py) (see §13) |

All monetary BDDK values are in **million TL** unless noted. Table 5 (Sectoral
Loans) is an exception — published in **thousand TL**.

---

## 2. Bank-type taxonomy

Defined in [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts) as the
`BANK_TYPES` (monthly) and `WEEKLY_BANK_TYPES` (weekly) constants. ⚠ The same
numeric codes mean **different** banks in the monthly vs. weekly feeds — both
mappings live in that file. The table below is the **monthly** scheme
(balance_sheet, financial_ratios, loans, deposits), matching the `bank_types`
DB table; for `weekly_series` codes see §4.

| Code | Name (EN) | Name (TR) |
|---|---|---|
| 10001 | Entire Sector | Sektör |
| 10002 | Deposit Banks | Mevduat |
| 10003 | Participation Banks | Katılım |
| 10004 | Development & Investment Banks | Kalkınma ve Yatırım |
| 10005 | Local Private Banks (all types) | Yerli Özel |
| 10006 | State Banks (all types) | Kamu |
| 10007 | Foreign Banks (all types) | Yabancı |
| 10008 | Deposit Banks – Local Private | Mevduat-Yerli Özel |
| 10009 | Deposit Banks – State | Mevduat-Kamu |
| 10010 | Deposit Banks – Foreign | Mevduat-Yabancı |

**Two overlapping partitions** (verified vs 2026-03 data, total assets, trn TL):
- **By type** → Sector: `10002` (41.8) + `10003` (4.7) + `10004` (3.2) = 49.7 = `10001`
- **By ownership, all types** → Sector: `10005` (14.3) + `10006` (23.3) + `10007` (12.2) = 49.7 = `10001`
- **Deposit ownership** → Deposit: `10008` (13.3) + `10009` (18.7) + `10010` (9.7) = 41.8 = `10002`

⚠ The two partitions **overlap** — do NOT sum `{10005,10006,10007}` together with
`{10003,10004}`; that double-counts participation + development banks (→ 57.7 trn,
not 49.7). So `10006` "State" already includes state-owned participation banks
(Ziraat/Vakıf/Emlak Katılım) and development banks (Eximbank, Kalkınma, İller);
the three state *deposit* banks alone are `10009`.

The dashboard's `PRIMARY_BANK_TYPES = ['10001','10005','10006','10007','10003','10004']`
fetches these for **side-by-side comparison**, not as a summed breakdown.

---

## 3. Currency & time conventions

- **Currency suffix columns:** every level metric comes with `_tl`, `_fx`,
  `_total` (in balance_sheet: `amount_tl`, `amount_fx`, `amount_total`).
- **FX amounts are already converted to TL equivalent** by BDDK at the
  reporting-date exchange rate. "FX" in the dashboard therefore means
  "originally-denominated-in-foreign-currency balances, in TL units."
- **Growth math:** YoY = `(x_t / x_{t-12}) − 1`. MoM = `x_t / x_{t-1} − 1`.
  MoM-annualized = `(1 + MoM)^12 − 1`.
- **Published YTD ratios** (Table 15 income-based): BDDK reports as
  cumulative Jan..month. The dashboard scales them linearly
  (`value × 12 / month`) to produce a constant-annualized figure — see
  the `annualize=true` flag on `getPublishedRatio` in
  [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts) (SQL expression
  `ratio_value * 12.0 / month`).
- **Stock ratios** (NPL, CAR, LDR, demand share, coverage) are already
  annual-in-nature and never rescaled.

---

## 4. Balance-sheet levels

Source: `balance_sheet` (BDDK Table 1). Filter by `item_name LIKE`.

| Metric | `item_name` pattern | Unit | Currency filter |
|---|---|---|---|
| Total Assets | `%TOPLAM AKT%` | M TL | `amount_total` |
| Total Loans | `Krediler%` | M TL | `amount_total` / `_tl` / `_fx` |
| Total Deposits | `%Mevduat%Fon%` (ex interest / ex sub-items a/b) | M TL | same |
| Total Equity | `%TOPLAM ÖZKAYN%` | M TL | `amount_total` |
| Total Liabilities | `%TOPLAM YABANCI KAYN%` | M TL | `amount_total` |
| Gross NPL | `%Takipteki Alacak%` | M TL | `amount_total` |
| Securities (FVOCI) | `GUD Farkı Diğer Kapsamlı Gelire Yan. Menk. Değ.` | M TL | — |
| Securities (AC) | `İtfa Edilmiş Maliyeti Üzerinden Değerlenen Menkul Değerler` | M TL | — |
| Cash & central bank | `Nakit Değerler` + `T.C. Merkez Bankasından Alacaklar` | M TL | — |

Implementation: `getBalanceItem` in [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts).

---

## 5. Loan portfolio

Source: `loans`. Always filter by `table_number`.

### Table 3 — loans by maturity / broad class
Items: İhracat Kredileri, İthalat Kredileri, Tüketici Kredileri, Kredi
Kartları, Faktoring, Toplam Krediler, etc. Columns: `short_term_tl/_fx`,
`medium_long_tl/_fx`, `total_tl/_fx`, `total_amount`.

### Table 4 — consumer + commercial breakdown with NPL

| Metric | `item_name` | Used in |
|---|---|---|
| Consumer Loans (Housing + Auto + GPL) | `Tüketici Kredileri (2+3+4)` | Credit, Overview |
| Consumer — Housing | `Tüketici Kredileri - Konut` | Credit |
| Consumer — Auto | `Tüketici Kredileri - Taşıt` | Credit |
| Consumer — General Purpose (GPL) | `Tüketici Kredileri - İhtiyaç` | Credit |
| Retail Credit Cards | `Bireysel Kredi Kartları (10+11)%` | Credit |
| Corporate Credit Cards | `Kurumsal Kredi Kartları (28+29)%` | Credit |
| Commercial Instalment Loans | `Taksitli Ticari Krediler (20+21+22)%` | Credit |
| NPL — Consumer total | `Takipteki Tüketici Krd. (14+15+16)` | Asset Quality |
| NPL — Housing | `Takipteki Konut Kredileri` | Asset Quality |
| NPL — Auto | `Takipteki Taşıt Kredileri` | Asset Quality |
| NPL — GPL | `Takipteki İhtiyaç Kredileri` | Asset Quality |
| NPL — Retail Cards | `Takipteki Bireysel Kredi Kartları` | Asset Quality |

### Table 6 — SME breakdown

| Metric | `item_name` |
|---|---|
| SME Loans — Total | `Toplam KOBİ Kredileri (2+3+4)` |
| SME — Micro | `Mikro İşletmelere Kullandırılan Krediler` |
| SME — Small | `Küçük İşletmelere Kullandırılan Krediler` |
| SME — Medium | `Orta Büyüklükteki İşletmelere Kullandırılan Krediler` |
| SME — Customer counts | `%İşletme Niteliğindeki Müşteri Sayısı%` |

Implementation: `smeLoans`, `smeBreakdown`, `consumerMix`,
`consumerNplMix` in [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts).

---

## 6. Deposits & funding

Source: `deposits`. Tables 9 (by holder type) and 10 (by maturity).

### Level
- **Total Deposits** — Table 10, row `TOPLAM MEVDUAT`, column `total_amount`.
- **Domestic TL** — Table 10, `TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik`.
- **Domestic FX** — Table 10, `Döviz Tevdiat Hesabı / Katılım Fonları - Yurt İçi Yerleşik`.

### Maturity mix
Table 10 `TOPLAM MEVDUAT`, sum into buckets: `demand`, `maturity_1m`,
`maturity_1_3m`, `maturity_3_6m`, `maturity_6_12m`, `maturity_over_12m`.
Shown as stacked-area in Deposits tab.

### Bracket mix
Columns `bracket_10k, bracket_50k, bracket_250k, bracket_1m, bracket_over_1m`
exist but are currently only populated for some rows / not wired into the
dashboard.

Implementation: `depositMaturityMix`, `tlDeposits`, `fxDeposits` in
[`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts).

---

## 7. Published ratios — BDDK Table 15

Source: `financial_ratios` (table_number=15). Column `ratio_value` is the
regulator's published value.

The dashboard treats these as **authoritative** — do not recompute from
underlying tables. For income-based ratios BDDK publishes YTD (see
[annualization](#8-derived--transformed-metrics)).

| Metric | `item_name` | Annualize? | Up is good/bad |
|---|---|---|---|
| NPL Ratio | `Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler (%)` | no (stock) | **bad** |
| Coverage | `Takipteki Alacaklar Karşılığı / Brüt Takipteki Alacaklar (%)` | no | good |
| Capital Adequacy (CAR) | `Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı (%)` | no | good |
| LDR (ex Dev & Inv) | `Toplam Nakdi Krediler / Toplam Mevduat (Kalkınma ve Yatırım Bankaları Hariç) (%)` | no | neutral |
| LDR (all) | `Toplam Nakdi Krediler / Toplam Mevduat (%)` | no | neutral |
| Demand-deposit share | `Vadesiz Mevduat / Toplam Mevduat (%)` | no | neutral |
| ROA (YTD) | `Dönem Net Kârı (Zararı) / Ortalama Toplam Aktifler (%)` | **yes** | good |
| ROE (YTD) | `Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar (%)` | **yes** | good |
| Pre-tax return on assets | `Vergi Öncesi Kar (Zarar) / Ortalama Toplam Aktifler (%)` | yes | good |
| NIM (YTD) | `Net Faiz Geliri (Gideri) / Ortalama Toplam Aktifler (%)` | yes | good |
| Interest yield | `Toplam Faiz Gelirleri / Faiz Getirili Aktifler Ortalaması (%)` | yes | neutral |
| Interest cost | `Toplam Faiz Giderleri / Faiz Maliyetli Pasifler Ortalaması (%)` | yes | neutral |
| OPEX / avg assets | `İşletme Giderleri / Ortalama Toplam Aktifler (%)` | yes | bad |
| Fees / total income | `Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / Toplam Gelirler (%)` | no (ratio of flows in same window) | good |
| Non-interest cover | `Faiz Dışı Gelirler / Faiz Dışı Giderler (%)` | no | good |
| Leverage | `Yabancı Kaynaklar / Toplam Özkaynaklar (%)` | no | neutral |
| RWA net/gross | `Risk Ağırlıklı Kalemler Toplamı (Net) / Risk Ağırlıklı Kalemler Toplamı (Brüt) (%)` | no | neutral |
| Large deposits (≥1M TL) share | `Yüksek Montanlı (1 Milyon TL ve Üzeri) Mevduat / Toplam Mevduat (%)` | no | neutral |

Implementation: `getPublishedRatio` plus named wrappers (`ratioNpl`,
`ratioCar`, `ratioLdr`, `ratioCoverage`, `ratioRoa`, `ratioRoe`,
`ratioNim`, `ratioOpex`, `ratioFeesToRevenue`, `ratioRwaDensity`,
`ratioNonInterestCoverage`, `ratioFeesToOpex`,
`ratioOffBsDerivatives`) in
[`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts).

### CET 1 and capital-adequacy detail (lives in `other_data`, not Table 15)
Table 12 (BDDK Capital Adequacy Detail) — not in `financial_ratios`. Query
`other_data` with `table_number = 12` and the Turkish `item_name`:

| Metric | `item_name` |
|---|---|
| **CET 1 Ratio** | `Çekirdek Sermaye Yeterliliği Rasyosu ((6/7)*100) (YÜZDE)` |
| CAR (standard method) | `Sermaye Yeterliliği Standart Rasyosu ((5/7)*100) (YÜZDE)` |
| CET 1 Capital | `Çekirdek Sermaye` |
| Tier 1 Capital | `Ana Sermaye Toplamı` |
| Tier 2 Capital | `Katkı Sermaye Toplamı` |
| Total Capital | `Orana Esas Sermaye Toplamı (1+2)` |

⚠ **Value precision:** `value_numeric` is stored as integer (scraper cast).
For 2-decimal precision re-parse `value_text` or the raw JSON cache.

⚠ **Bank-type mapping:** BBVA's "Public Banks" CET 1 chart maps to
`bank_type_code = '10009'` (Public Banks all-models), **not** `10004`
(State Deposit Banks only). The latter has a much higher CET 1 (~20%)
because of different RWA composition.

---

## 8. Derived / transformed metrics

### Growth transforms — [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts)
- **YoY** — `yoy_growth(df)`: `x_t / x_{t-12} − 1`, percent.
- **MoM** — `mom_growth(df)`: `x_t / x_{t-1} − 1`, percent.
- **MoM annualized** — `mom_annualized(df)`: `(1 + MoM)^12 − 1`.
- **Annualize YTD** — `annualize_ytd(df)`: `value × 12 / month`. Applied
  only to income-based ratios from Table 15 (see column flag in §7).
  Assumes roughly even monthly accrual; December values are unchanged.

### Share / composition
- **FX loan share** = `total_loans_fx / total_loans_total × 100`.
- **FX deposit share** = `total_deposits_fx / total_deposits_total × 100`.
- **Interest yield − cost spread** (in Profitability) = yield − cost (both
  already annualized).
- **Market share** = bank_type's assets / Sector assets × 100 (available in
  the data store; currently not shown as a standalone panel).

Implementation: derivations are computed on-the-fly inside each page's
Server Component (e.g. `web/app/credit/page.tsx` calls `tlLoans` + `fxLoans`
and computes FX share in JS). There is no precomputed cache layer; D1's
edge latency makes one query per chart cheap enough.

### NPL ratio by segment
The dashboard now computes per-product consumer NPL ratios via
`consumerNplRatios` and commercial NPL ratios (SME / commercial / non-SME)
via `commercialNplRatios` in
[`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts). Both are surfaced
on the Asset Quality page.

---

## 9. EVDS macro & interest rate series

Source: TCMB EVDS v3, fetched by
[`src/scrapers/evds_client.py`](../src/scrapers/evds_client.py),
scheduled by [`src/scrapers/evds_scraper.py`](../src/scrapers/evds_scraper.py),
cached into the `evds_series` D1 table; dashboard reads via the
`evdsSeries` / `evdsMulti` helpers in
[`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts).
Host: `evds3.tcmb.gov.tr/igmevdsms-dis` — API key sent as header `key`.

> **Monthly-series date fix (2026-06-05):** EVDS returns monthly dates as
> `YYYY-M` (e.g. `2026-5`), but `evds_client._fetch_one` parsed only
> `%d-%m-%Y`, so **every monthly series** (CPI, expectations, REER,
> residents' FC) was silently coerced to NaT and dropped — landing empty in
> D1. `_parse_evds_dates` now backfills the `%Y-%m` format. After deploying,
> the next refresh repopulates these monthly series.

### Weekly TL flow rates (Rates tab)
Datagroups `bie_kt100h` (loans) and `bie_mt100h` (deposits).

| Dashboard label | EVDS code | TCMB name |
|---|---|---|
| Consumer loan | `TP.KTFTUK` | Consumer Loans (TRY) (Personal+Vehicle+Housing) Flow % |
| Consumer + overdraft | `TP.KTFTUK01` | Consumer Loans (TRY) incl. Real Person Overdraft |
| Commercial (ex cards & OD) | `TP.KTF18` | Commercial Loans (TRY) excl. Corp OD & Corp Credit Cards |
| Deposit (total TL) | `TP.TRY.MT06` | Total (TRY Deposits, Flow, %) |

Other series in the same datagroups (TP.KTF10/11/12/17, TP.KTF101,
TP.TRY.MT01-05, TP.TRYTAS.*, TP.TRYTIC.*) are available from the same
helper but not wired into any chart yet.

### CBRT Interest Rate Corridor (Rates tab)
Datagroups `bie_pyintbnk` (Central Bank Interbank Quotations) and
`bie_bisttlref` (BIST TLREF Reference Rate). Matches BBVA's "Interest Rate
Corridor & ON TRY Ref" chart 1:1.

| Line | EVDS code | What it is |
|---|---|---|
| **Policy Rate** | `TP.PY.P02.1H` | 1-week repo **quotation OFFER**. Set by MPC; step-function. CBRT's announced policy rate. |
| **ON Lending** (corridor upper) | `TP.PY.P02.ON` | Overnight OFFER quotation — rate at which CBRT lends to market. |
| **ON Borrowing** (corridor lower) | `TP.PY.P01.ON` | Overnight BID quotation — rate at which CBRT borrows from market. |
| **BIST TRY REF** | `TP.BISTTLREF.ORAN` | BIST TLREF — actual interbank O/N reference rate. Floats with market. |

**Why not `TP.APIFON4`?** `TP.APIFON4` is *CBRT Weighted Average Cost of
Funding* — an operational metric of what the market actually pays for
CBRT funding on a given day. It tracks the effective stance but isn't
the announced policy rate. CBRT's policy rate by definition is the
1-week repo rate (`TP.PY.P02.1H`).

**Why quotation vs auction:** The 1-week **auction** realized weighted
average (`TP.PY.P06.1HI`, currently ~40%) can differ from the posted
quotation (`TP.PY.P02.1H` = 37%) — CBRT uses auction sizing to tighten
beyond the announced rate. The auction series doesn't run continuously
and isn't "the policy rate"; it's a separate liquidity-management tool.

Related (not plotted currently):
- `TP.APIFON4` — effective cost of CBRT funding (daily)
- `TP.PY.P06.1HI` — 1-week deposit auction realized weighted avg
- `TP.BISPOLFAIZ.TUR` — BIS-published policy rate (monthly, same values)

### CBRT Net Funding / Sterilization (cat 3002, `bie_apifon`)
| Label | EVDS code | Notes |
|---|---|---|
| **CBRT Net Funding** | `TP.APIFON3` | Already equals `APIFON1 − APIFON2` at source — **do not recompute**. Daily, thousand TL (÷1000 → bn TL). Positive = excess TL liquidity (CBRT net funding market); negative = lack of liquidity (CBRT net absorbing). |
| Total funding (A) | `TP.APIFON1.TOP` | Gross daily funding to market. |
| Total sterilization (B) | `TP.APIFON2.TOP` | Gross daily absorption. Sub: `.IHA` auction, `.KOT` quotation, `.LIK` liquidity bills. |
| Effective cost of funding | `TP.APIFON4` | Weighted-avg rate CBRT charges on daily operations. Operational indicator, not the policy rate. |

### CBRT Gold Reserves in Tons (weekly, `bie_mbblnch`)
Unit is **grams** despite label "Net Gram" — divide by `1e9` for tons. 121-ton
decline 2026-03-06 → 2026-03-27 confirms unit.

| Label | EVDS code | Notes |
|---|---|---|
| Total CBRT gold (asset) | `TP.BL0021` | A11 International Standard Gold (net gram). Weekly Friday. |
| Banks' gold at CBRT | `TP.BL0891` | P3232 liability (net gram). |
| **CBRT-owned gold** | derived | `(TP.BL0021 − TP.BL0891) / 1e9` → tons. |
| Treasury non-int std gold | `TP.BL1111` | Usually zero. |
| Monthly equivalents | `TP.BL0021.A`, etc. | same series, monthly agg. |

### Residents' FC Deposits (weekly, `bie_hpbitablo4`)
All in **million USD**, weekly Friday.

| Label | EVDS code | Notes |
|---|---|---|
| Residents total FC | `TP.HPBITABLO4.2` | 1.1 All resident FC deposits. |
| Households total FC | `TP.HPBITABLO4.3` | 1.1.1 |
| Households USD | `TP.HPBITABLO4.4` | USD-denominated only. |
| Households EUR | `TP.HPBITABLO4.5` | EUR-denominated (already in USD equivalent). |
| Households Precious Metals | `TP.HPBITABLO4.7` | |
| Corporates total FC | `TP.HPBITABLO4.8` | 1.1.2 |

### CBRT Expectations Surveys
- **Market Participants Survey** (cat 1004, `bie_pkauo`, monthly):
  - `TP.PKAUO.S01.D.U` — CPI expectation, current year-end
  - `TP.PKAUO.S01.I.U` — CPI expectation, next year-end
  - `TP.PKAUO.S01.E.U` — 12-month-ahead CPI expectation
  - `TP.PKAUO.S04.D.U` — 12-month-ahead CBRT policy rate expectation
- **Household Expectations Survey** (cat 1007, `bie_hanebek`, monthly):
  - `TP.HANEBEK.HAN14A` — Household 12-month annual inflation expectation (avg)

### FC Loan & Deposit Rates (weekly, `bie_kt100h` / `bie_mt100h`)
All %, weekly flow.

| Label | EVDS code |
|---|---|
| Commercial Loan rate, USD | `TP.KTF17.USD` |
| Commercial Loan rate, EUR | `TP.KTF17.EUR` |
| Total USD Deposit rate | `TP.USD.MT06` |
| Total EUR Deposit rate | `TP.EUR.MT06` |
| Savings-only: `TP.USDTAS.MT06`, `TP.EURTAS.MT06`; Commercial-only: `.TIC.` variant | |

### CPI & inflation derived
- `TP.FG.J0` — Consumer Price Index (2003=100, monthly). Raw index value.
- `cpi_yoy[m] = CPI[m] / CPI[m−12] − 1`
- `cpi_12m_avg[m] = mean(cpi_yoy[m−11 .. m])`

### Other macro series
| Label | EVDS code | Notes |
|---|---|---|
| USD/TRY | `TP.DK.USD.A` | Buying rate. Daily. |
| Net international reserves | `TP.AB.N01` | Weekly. |
| REER (CPI based, 2003=100) | `TP.RK.T1.Y` | Monthly. Real-appreciation backdrop on the Liquidity tab. (`.T2.Y` = PPI based, `.T3.Y` = developing-economies basket.) |

### BBVA's "Deposit Rate (inc. RR cost)"
BBVA adds an internal required-reserve cost to the raw deposit rate. TCMB
does not publish that composite series. The dashboard shows the raw
`TP.TRY.MT06` and notes the discrepancy in the Rates banner.

---

## 10. Weekly BDDK series

Source: `weekly_series` + `raw_weekly_responses`. Endpoint `POST
/BultenHaftalik/tr/Home/KiyaslamaJsonGetir`. Returns 13 weeks per call;
scraper walks anchor dates backwards 13 weeks at a time. Implementation:
[`src/scrapers/weekly_api_scraper.py`](../src/scrapers/weekly_api_scraper.py).

### Schema
```sql
weekly_series(
    period_date DATE, category TEXT, item_id TEXT, item_name TEXT,
    bank_type_code TEXT, currency TEXT, value REAL,
    downloaded_at TIMESTAMP,
    PRIMARY KEY (period_date, item_id, bank_type_code, currency))
```

All values in million TL. Dates are published Fridays.

### ⚠ Bank-type codes: weekly ≠ monthly — CRITICAL
The weekly and monthly BDDK feeds reuse **the same numeric range `10001–10010`
for different bank groups.** The weekly scraper remaps the weekly-API codes
(`WEEKLY_TO_MONTHLY_CODE` in [weekly_api_scraper.py](../src/scrapers/weekly_api_scraper.py))
and stores them, but the **stored numbers still don't match the monthly tables**
in §2 — they match `WEEKLY_BANK_TYPES`. So **read `weekly_series` with
`WEEKLY_BANK_TYPES`, never `BANK_TYPES`.** (The remap dict's inline comments name
the targets with monthly labels that are wrong vs §2 — cosmetic only; values are
read back with the matching weekly mapping, so charts are correct.)

What `weekly_series.bank_type_code` actually holds (the scraper fetches only this
primary set), and how the SAME number differs in the monthly tables:

| weekly_series code | Weekly group (`WEEKLY_BANK_TYPES`) | Same code in MONTHLY (§2) |
|---|---|---|
| 10001 | Sector | Sector ✓ |
| 10003 | Private (deposit) | Participation ✗ |
| 10004 | State (deposit) | Dev & Investment ✗ |
| 10005 | Foreign (deposit) | Private, all types ✗ |
| 10006 | Participation | State, all types ✗ |
| 10007 | Dev & Investment | Foreign, all types ✗ |

Verified vs live data (weekly total loans `1.0.1`, trn TL): `10004` = 9.6 (State
deposit — Participation's whole asset base is only 4.7, so `10004` can't be
Participation), `10003` = 7.0, `10005` = 5.4, `10006` = 2.1, `10007` = 1.9; these
sum to the sector (25.9).

### Item catalogue (124 items across 7 categories)
Chart IDs follow `{category}.0.{item}` format. Each item is available for
all 6 primary bank types (10001 + 10003–10007) × 3 currencies (TL/FX/TOTAL).

| Category | Slug | Items | Examples |
|---|---|---|---|
| 1 | `krediler` | 22 | 1.0.1 Toplam Krediler · 1.0.3 Tüketici · 1.0.4 Konut · 1.0.5 Taşıt · 1.0.6 İhtiyaç · 1.0.8 Bireysel Kredi Kartları · 1.0.11 KOBİ (Bilgi) · 1.0.12 Ticari ve Diğer · 1.0.22 Döv. Endeksli |
| 2 | `takipteki_alacaklar` | 12 | 2.0.1 Takipteki Alacaklar · 2.0.2 Tüketici NPL · 2.0.3 Kart NPL · 2.0.4 KOBİ NPL · 2.0.5 Ticari NPL |
| 3 | `menkul_degerler` | 13 | 3.0.1 Toplam Menkul · 3.0.14 FVPL · 3.0.17 FVOCI · 3.0.20 Amortised Cost |
| 4 | `mevduat` | 12 | 4.0.1 Mevduat total · 4.0.3 Vadesiz · 4.0.4 Vadeli · 4.0.12 KKM |
| 5 | `diger_bilanco` | 16 | 5.0.1 Nakit · 5.0.2 CBRT · 5.0.4 Zorunlu Karşılıklar · 5.0.9 Bankalara Borçlar · 5.0.12 İhraç Menkul Kıymetler |
| 6 | `bilanco_disi` | 4 | 6.0.1 Gayrinakdi Krediler · 6.0.3 Türev Finansal Araçlar |
| 7 | `yp_pozisyon_saklama` | 45 | 7.0.1–7.0.45 Saklanan Menkul Değerler (custodial) |

Full catalogue persisted at [`scripts/_weekly_catalogue.json`](../scripts/_weekly_catalogue.json).

### Helper functions

In [`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts):

- `weeklySeries(category, item_id, currency, bankTypes, weeksBack)` →
  raw `(period, bank_type_code, value)` rows.
- `weeklyGrowth(category, item_id, currency, windowWeeks, bankTypes, weeksBack)` →
  annualized compound growth (see §11 below). The 52/N exponent is
  computed in TypeScript because D1's sandbox blocks `POWER()`.

---

## 11. Weekly growth transforms

Implemented as `weeklyGrowth` in
[`web/app/lib/metrics.ts`](../web/app/lib/metrics.ts) — SQL pulls
current + lagged values, exponent is applied in TypeScript.

| Transform | Formula | Notes |
|---|---|---|
| 4-week annualized | `(x_t / x_{t-4})^(52/4) − 1 = (x_t / x_{t-4})^13 − 1` | BBVA nowcast horizon; first available point is week 5 |
| 13-week annualized | `(x_t / x_{t-13})^(52/13) − 1 = (x_t / x_{t-13})^4 − 1` | BBVA medium-term trend; first available point is week 14 |
| 52-week YoY | `x_t / x_{t-52} − 1` | Not annualized — already yearly; first available point is week 53 |

Implementation detail: each transform groups by `bank_type_code` then
applies the shift inside the group. Rows where the prior value is ≤ 0 are
dropped (zero-guard against silent `inf` / negative-ratio rows). Output
is in **percent**, not decimal.

---

## 12. Where each metric appears in the dashboard

Implementation lives in `web/app/lib/metrics.ts` (TypeScript helpers
reading directly from D1). One page per tab under `web/app/<tab>/page.tsx`.

| Page | Charts | Underlying metrics (this doc §) |
|---|---|---|
| `/` (Overview) | 8 KPIs + sparklines: Total Assets, Assets YoY, Loan YoY, Deposit YoY, NPL, CAR, LDR, ROE. Sector trend charts: Total Assets level, NPL by group, Loan growth by group, Loan YoY trend. | §4, §7, §8 |
| `/credit` | Total Loans level + YoY by group + MoM sector + bar by bank. TL / FX / FX share. Consumer mix stacked area (level + percent). Consumer segment YoY. Retail vs Corporate cards. Public-vs-Private YoY (total + TL). SME breakdown + level. | §4, §5, §8 |
| `/deposits` | Total deposits level, YoY by group, MoM, bar by bank. TL / FX / FX share. Demand level + share. Maturity stacked (level + percent). LDR by group. | §4, §6, §7, §8 |
| `/asset-quality` | NPL by group + bar by bank. Coverage by group. Gross NPL stock (derived as total × ratio). Consumer NPL composition + per-product ratios. Commercial NPL (SME / commercial / non-SME from weekly bulletin). | §4, §5, §7, §10 |
| `/capital` | CAR by group + bar. Equity level + YoY. Liabilities / Equity. RWA Net / Gross. Off-BS derivatives / total assets. | §4, §7, §8 |
| `/profitability` | ROE, ROA, NIM (annualized). NIM components decomposition (signed stacked bars per bank group, annual + monthly TTM). OPEX / avg assets. Fees / revenue. Non-interest income / non-interest expense. Fees / OPEX. Optional ROE-vs-CPI overlay. | §7, §8, §9 (CPI), §16 |
| `/weekly` | Loan level + 4w ann. + 13w ann. (all groups). TL vs FX, public vs private TL. Consumer segments 13w. SME vs commercial 13w. Deposits trio. NPL stock + YoY. | §10, §11 |
| `/liquidity` | Adapts BBVA's liquidity section. TL & FC loan/deposit ratios (public vs private), TL deposit growth (sector YoY+13w; public vs private YoY), deposit dollarization (sector/public/private), residents' FC savings (households, USD bn), net CBRT funding (TL bn), gross reserves (USD bn), REER. | §9, §10, §11 |
| `/rates` | TCMB rate corridor, FX, weekly survey rates, sterilization channels. (Several historical Rates panels still pending D1 backfill — see [PROJECT_STATE.md](PROJECT_STATE.md) "Known issues".) | §9 |
| `/banks` + `/banks/[ticker]` | Bank index + per-bank drill-down: full BS + P&L tables, financial-assets time series. Reads from `bank_audit_*` tables. | See `web/app/lib/audit.ts` |
| `/cross-bank` (Compare) | Cross-bank heatmap, banks × {Total assets, NPL, Stage-2, NPL coverage, Provision intensity, ROE, ROA, NIM, Cost/Income}, colored by rank-vs-peers. Snapshot (latest common quarter) + Over-time (one metric × quarters). ROE/ROA/NIM/Cost-Income derived per bank from the P&L pivot by BRSA hierarchy (net profit `XXV.`→`XIX.`, NII `III.`, opex `XI.`+`XII.`, gross op profit `VIII.`) over period-end assets (BS roman I.–X.) / equity (BS liab `XVI.`); YTD flows annualized × (4/quarter). | See `web/app/lib/heatmap.ts` |

---

## Appendix A — things deliberately **not** in the dashboard

| Missing | Reason |
|---|---|
| Forecasts (ROE/credit path) | Requires proper model; BBVA uses in-house projections. |
| Full Financial Conditions Index | Model-dependent weighting; user asked to skip. Liquidity tab shows the REER component as a standalone backdrop. |
| Investment-fund volumes / net flows / fund dollarization | Source is TEFAS (mutual-fund AUM), not BDDK or EVDS. Needs a new TEFAS scraper. |
| Under-the-mattress (household) gold stock | BBVA estimate per CBRT 2012-IV methodology — needs gold import/production/jewelry-trade data + a model. Our `TP.BL0021` is CBRT vault gold, a different concept. |

> **Now replicated (Liquidity tab, 2026-06-05):** the BBVA liquidity-section
> charts we *can* source — TL & FC loan/deposit ratios and TL deposit growth
> split **Public (state) vs Private (private + foreign)**, deposit
> dollarization, net CBRT funding, gross reserves, residents' household FC
> savings, and REER. The public/private fold (foreign → private) reproduces
> the report's own figures. Helpers: `weeklyOwnershipRatio`,
> `weeklyGrowthByOwnership`, `weeklyDollarization` in `web/app/lib/metrics.ts`.
| FX-parity-adjusted credit growth | Needs monthly FX basket, not yet wired. Plain FX growth shown. |
| 4w / 13w rate trends | Weekly data in DB is sparse (14 periods). Use EVDS directly. |
| Bracket deposit mix (10k/50k/250k/1m/>1m) | Columns exist but not consistently populated. |
| Sectoral loans (Table 5) | Units are **thousand TL** — needs unit handling before wiring. |
| BBVA HQLA ex CB Swaps | BBVA's own definition of liquid FX assets — combines CBRT balance-sheet items net of swap exposures. Not a single EVDS series. Would need to replicate their formula. |
| BBVA Weekly Reserve Flows decomposition | BBVA derives "implicit FC sales", "export & services revenue", and "net sales" from daily reserve changes cross-checked against TCMB BoP. Proprietary. |
| BBVA "Net International Reserves exc Swaps" | Requires outstanding FX swap stock (`TP.FXSWAP03` is per-auction flow, not stock). Could approximate by cumulating swap auctions and deducting, but error-prone. |

> **`TP.AB.N01` investigation (resolved 2026-04-23):** N01 is not NIR —
> it's **Base Money** (Para Tabanı = currency issued + bank required
> reserves + free deposits), from datagroup `bie_abstc2` (CBRT Balance
> Sheet - Stand By, IMF Letter-of-Intent monitoring, weekly Friday).
>
> **The correct NIR is `TP.AB.N06`** (bie_abstc2). Raw unit is
> **thousand TL**; convert via `÷ USD_TRY ÷ 1e6` to get bn USD.
> Verified 2026-04-10: $55.6 bn, matching BBVA's Apr-1 chart label of
> $42 bn on a 27-Mar→3-Apr trajectory.
>
> Sibling series in the same datagroup:
>   - `TP.AB.N05` — Net Foreign Assets
>   - `TP.AB.N07` — Gross Foreign Assets
>   - `TP.AB.N08` — Gross Reserve Liabilities (negative)
>   - `TP.AB.N12` — Net Forward Position (returns 0 currently; ≠ swap stock)
>   - `TP.AB.N15` — Net Domestic Assets
>
> Registry updated: `net_reserves_raw` (mislabeled) replaced by
> `cbrt_base_money_tl` (N01) and `cbrt_nir_tl` (N06) with correct units.

### Net International Reserves — our derivation

The dashboard's Net Reserves line on the Rates tab is:
```
Net FX = (TP.BL054 Total FX Assets − TP.BL122 Total FX Liabilities) / TP.DK.USD.A / 1e6
```
from CBRT's weekly balance sheet (`bie_mbblnch`). This gives roughly $51bn
on 2026-04-10 vs BBVA's $42bn on 2026-03-31 — directionally right, differs
from BoP-defined NIR because:
- Balance-sheet FX assets include all FX claims (reserves + foreign bank
  credits + other FX securities), while BoP-NIR counts only liquid reserve
  assets.
- BoP-NIR further excludes FX liabilities to resident banks that show in
  our derivation.

To match BBVA's exact NIR we'd need: BoP reserves + derive liabilities per
IMF SDDS template. Left for later.

## Appendix B — non-obvious methodology choices

1. **LDR uses the "ex Development & Investment banks" version.** This is
   the headline sector number; including dev/inv banks double-counts
   project-finance lending that has no deposit counterpart.
2. **NPL up is red, CAR up is green** is the legacy direction convention
   from the old Dash app. The new dashboard renders KPIs without
   direction tinting; magnitudes speak for themselves.
3. **YTD annualization is linear** (`× 12/m`). A more-accurate approach
   would use last-12-months flows, which we don't have from the
   cumulative series. The simple scaling matches typical TCMB /
   analyst presentations.
4. **"Sector" is additive.** Growth rates of the Sector line are equal to
   size-weighted averages of the five ownership components — so Sector
   vs. ownership comparisons are meaningful and the lines don't need
   re-weighting.
5. **Weekly / monthly bank-type codes are remapped on ingest** (see §10).
   The same numeric range `10001–10010` means different things in the
   weekly vs monthly APIs. Downstream code always sees the monthly
   taxonomy.
6. **Weekly growth annualizations are compound** (`^13` or `^4`), not
   linear (`× 13`). Compound matches the way BBVA and TCMB report trend
   rates. Difference at 50% 4w ann. is ~3pp vs. simple.
7. **`TP.APIFON3` = net funding directly.** Do not recompute
   `APIFON1.TOP − APIFON2.TOP`; the difference is already published as
   its own series. Confirmed by the metric-finder agent 2026-04-23.
8. **CET 1 lives in `other_data` table 12**, not `financial_ratios`
   Table 15. See §7 end. Values are rounded to integer in
   `value_numeric` — parse `value_text` if decimals matter.

## Appendix C — BDDK income-statement item mapping (Table 2)

Used for ROE / NIM / revenue-composition decompositions. Item orders
are stable across months. All values are YTD cumulative; annualize with
`× 12/month` when building annualized displays.

### Interest income items
| `item_order` | `item_name` (abbrev) | Used for |
|---|---|---|
| 1 | Kredilerden Alınan Faizler (total) | NIM-loans component |
| 2 | — of which Consumer | loan-NIM sub-split |
| 3 | — of which Credit Cards | loan-NIM sub-split |
| 4 | — of which Commercial Instalment | loan-NIM sub-split |
| 5 | — of which Other | loan-NIM sub-split |
| 6 | Takipteki Alacaklardan | NPL interest (adds to "loans" bucket) |
| 7 | Bankalardan Alınan Faizler | "banks/MM/repo" bucket |
| 8 | Para Piyasası İşlemlerinden | "banks/MM/repo" bucket |
| 9 | FVPL (alım-satım amaçlı) menkul faiz | securities-NIM |
| 10 | FVOCI menkul faiz | securities-NIM |
| 11 | Amortized-cost menkul faiz | securities-NIM |
| 12 | Reverse repo | "banks/MM/repo" bucket |
| 13 | Finansal kiralama | "banks/MM/repo" |
| 14 | Diğer faiz gelirleri | "banks/MM/repo" |
| **15** | **Toplam Faiz Gelirleri** | Interest income total (pair with `Toplam Faiz Gelirleri / Faiz Getirili Aktifler Ortalaması` from Table 15 to back-solve avg IEA) |

### Interest expense items
| 16 | Mevduata verilen faizler | Deposit-NIM component |
| 17 | Bankalara verilen | Debt-NIM component |
| 18 | Para piyasasından | Debt-NIM |
| 19 | İhraç edilen menkul | Debt-NIM |
| 20 | Repo | Debt-NIM |
| 21 | Finansal kiralama | Debt-NIM |
| 22 | Diğer faiz giderleri | Debt-NIM |
| 23 | Toplam Faiz Giderleri | |
| **24** | **Net Faiz Geliri (= 15 − 23)** | NII — first ROE bucket |

### Non-interest items (ROE decomposition)
| 25 | Kredi ve alacaklar karşılık giderleri | Provisions bucket |
| 27 | Kredi kredisi ücret ve komisyonları | Fees (minor) |
| 31 | Bankacılık hizmetleri gelirleri | Fees (major) |
| 30 | Ortaklık/iştirak gelirleri | Dividend bucket |
| 32, 33, 34 | Diğer faiz dışı gelirler / Toplam faiz dışı gelirler | Other NII |
| 35, 42, 43, 44 | Personel, amortisman, vergi, diğer giderler | OPEX bucket |
| 36, 38, 39, 40 | Menkul değer değer düşüklüğü / iştirak değer düşüklüğü / diğer karşılıklar | Provisions (spec + gen + impair) |
| 41 | Ücret ve komisyon giderleri | **not** subtracted from fees in BBVA chart |
| **46** | **Net ticari kar/zarar (securities trading only)** | "Trading" bucket |
| **47** | **Net kambiyo (FX) kar/zarar** | **"Other NII" in BBVA — NOT "Trading"** |
| 49 | Net parasal pozisyon kar/zarar | Hyperinflation monetary gain; not in "Trading" |
| 50 | Toplam diğer faiz dışı gelir/gider (net) | Total non-int net — revenue denominator |
| 52 | Vergi karşılığı | "Other/tax" bucket |

### Typical BBVA decomposition formulas
```
NII            = item_24
Fees & Comm    = item_27 + item_31
Trading        = item_46                 # (securities only)
Dividend       = item_30
Other NII      = item_32 + item_33 + item_47 + item_48 + item_49
                 # FX goes here, not Trading
OPEX           = item_35 + item_42 + item_43 + item_44
Provisions     = item_25 + item_36 + item_38 + item_39 + item_40
Other/tax      = item_52

ROE component% = (TTM item) / (13-point trailing avg equity) × 100

NIM component% = (YTD item × 12 / month) / avg_IEA × 100
  where avg_IEA = item_15(YTD) × (12/month) / r_interest_yield_ytd × 100
                  # back-solved from Table 15 "Toplam Faiz Gelirleri /
                  # Faiz Getirili Aktifler Ortalaması (%)"
```

### Bank-type convention for BBVA "deposit banks" ROE panels
Use `bank_type_code = '10002'` (Deposit Banks, combined). Sector total
(`10001`) runs ~1pp higher because participation + dev/inv banks pull
it up.

## Appendix D — Derivations catalog (charts we replicate from primitives)

All formulas verified numerically by the metric-finder agent
(2026-04-23). Numerical agreement ≤ 1pp vs BBVA Mar-26 chart except
where noted.

> **Now also machine-readable.** New chart reproductions are captured as specs in
> [`web/app/lib/chart-specs.catalog.json`](../web/app/lib/chart-specs.catalog.json)
> (locator + transform + a `verify[]` anchor) and re-checked every day by
> `scripts/verify_chart_spec.py` (wired into the `healthcheck.yml` cron), so a
> BDDK rename or EVDS breakage alerts instead of silently blanking a chart. The
> derivations in this table are the seed backlog to migrate into specs over time.
> See [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md) for the full loop.

| Chart / description | Formula | Verified |
|---|---|---|
| CBRT Sov Bonds / Total Assets | `TP.AB.A051 / TP.AB.A01 × 100` | 4.22% vs 4.1% ✓ (0.12pp; BBVA likely nets a small liability) |
| CBRT Net Funding (bn TL) | `TP.APIFON3 / 1000` | −895 bn TL Mar-25, +543 bn TL Apr-26 ✓ |
| TL commercial spread | `TP.KTF18 − TP.TRY.MT06` | +2.52pp (raw; BBVA adds ~5pp RR cost) |
| TL consumer spread | `TP.KTFTUK − TP.TRY.MT06` | +12.65pp (raw) |
| NPL ratio — GPL | `Takipteki İhtiyaç / Tüketici İhtiyaç` (Table 4) | 5.64% vs 5.0% ✓ |
| NPL ratio — Cards (retail) | `Takipteki Bireysel KK / Bireysel KK (10+11)` | 4.78% vs 4.0% ✓ |
| NPL ratio — Housing | `Takipteki Konut / Tüketici Konut` | 0.16% vs 0.2% ✓ |
| NPL ratio — Auto | `Takipteki Taşıt / Tüketici Taşıt` | 0.79% vs 0.3% (small denom; trending up) |
| NPL ratio — Installment commercial | `Takipteki Taksitli Tic. / Taksitli Ticari (20+21+22)` | 2.81% vs 3.1% ✓ |
| NPL ratio — Corporate cards | `Takipteki Kurumsal KK / Kurumsal KK (28+29)` | 2.65% vs 2.2% ✓ |
| NPL ratio — SME | weekly `2.0.4 / 1.0.11` (currency=TOTAL) | 3.53% vs 3.1% ✓ |
| NPL ratio — Commercial (all) | weekly `2.0.5 / 1.0.12` | 2.15% vs 2.6% (0.45pp; denominator scope differs) |
| NPL ratio — Non-SME | weekly `(2.0.5 − 2.0.4) / (1.0.12 − 1.0.11)` | 1.37% vs 2.1% (0.7pp) |
| NIM — loans component | `(item_1 + item_6) × 12/m / avg_IEA × 100` | 12.58% vs 13.0% ✓ |
| NIM — securities | `(item_9+10+11) × 12/m / avg_IEA × 100` | 2.91% vs 3.1% ✓ |
| NIM — banks/MM | `(item_7+8+12+13+14) × 12/m / avg_IEA × 100` | 3.35% vs 2.9% ✓ |
| NIM — deposit exp | `item_16 × 12/m / avg_IEA × 100` | −11.64% vs −10.6% ✓ |
| NIM — debt-issued exp | `(item_17-22) × 12/m / avg_IEA × 100` | −2.78% vs −2.6% ✓ |
| ROE — NII bucket | `TTM item_24 / avg_equity_TTM × 100` | +51.7% vs +51% (Private Feb-26) ✓ |
| ROE — Fees bucket | `TTM (item_27+31) / avg_equity × 100` | +33.0% vs +36% close |
| ROE — OPEX bucket | `TTM (item_35+42+43+44) / avg_equity × 100` | −43.6% vs −42% ✓ |
| NII / Total Revenue | `item_24 / (item_24 + item_34 + item_50)` | 49.15% Dec-25 Sector ✓ |
| Trading+FX / Total Revenue | `(item_46 + item_47) / (item_24+item_34+item_50)` | −3.53% Sector ✓ |
| Fees YoY | `(item_27 + item_31)_t / same_YTD_{t−12m} − 1` | +48.8% Dec-25 ✓ |
| Real policy rate expectation (12m) | `(1+PKAUO.S04.D.U)/(1+PKAUO.S01.E.U) − 1` | 5.0% Apr-26 ✓ |
| CPI 12-month avg | `mean(CPI_YoY[m−11..m])` | 34.23% Jan-26 ✓ |
| CBRT-owned gold (tons) | `(TP.BL0021 − TP.BL0891) / 1e9` | 508 tons Mar-26 vs chart 509 ✓ |

---

## 13. TBB digital-banking statistics

Source: the **Banks Association of Türkiye (TBB)** "Dijital, İnternet ve Mobil
Bankacılık İstatistikleri" report, published quarterly as an Excel workbook
(`.xls` pre-2021, `.xlsx` since). These are **sector-wide aggregates** — there is
no per-bank or bank-type breakdown — so they complement (never overlap) the
balance-sheet / P&L tables. Ingestion: [`src/tbb/`](../src/tbb/) (discover →
download → parse) driven by [`scripts/update_tbb_digital.py`](../scripts/update_tbb_digital.py),
landing in `tbb_digital_stats`. Surfaces on the **/digital** tab
([`web/app/lib/digital.ts`](../web/app/lib/digital.ts)).

The parser emits one tidy long row per measurement, keyed by:

| Dimension | Values | Notes |
|---|---|---|
| `period` | `YYYY-MM` quarter-end | Mar/Jun/Sep/Dec. Each workbook holds a trailing ~5 quarters. |
| `channel` | `digital` \| `internet` \| `mobile` | `digital` = the union view (internet ∪ mobile), incl. demographics. |
| `segment` | `individual` \| `corporate` \| `total` | Customers (section I) come **only** from the channel-total sheet, split by the Bireysel/Kurumsal/Toplam column groups; transactions come from each sheet by name. |
| `section_code` | `I` … `IV` (`III.1`–`III.6`) | I customers · II non-financial txn · III.1–III.6 financial (transfers/payments/investments/cards/…) · IV product sales. On the `digital` sheet: II = gender, III = age group. |
| `metric_path` | `>`-joined Turkish header | Reproduces the 1–3-level merged column headers (e.g. `Havale > Üçüncü şahıslara yapılan > TP Havale`). `metric_slug` is its ASCII slug (the stable join key). |
| `unit` | `persons_thousands` \| `count_thousands` \| `volume_bn_try` | Head-counts (thousand people), transaction counts (thousand), transaction value (billion TL). |

**Units & conventions.** Customer counts are point-in-time at quarter end;
transaction figures are quarterly flows. The `/digital` data layer rescales for
display: thousands → millions, billion TL → ₺ trillion.

**Revisions.** TBB occasionally revises a recent quarter (flagged with `*` in
the source). Workbooks overlap, so `update_tbb_digital.py` processes them
oldest→newest and the idempotent upsert (PK = period, channel, segment, section,
metric_slug, unit) lets the newest file's revised value win.

**Cross-era unit changes (normalised at parse time).** TBB changed report units
over the years; `_classify_unit` recovers the canonical unit from each block's
header and rescales, so a series is continuous across the switch:
- *Customer counts* — pre-2020 reports give **absolute persons** (`Aktif müşteri
  sayısı`); 2020+ give **thousands** (`… (Bin)`). Canonical = thousands.
- *Transaction volumes* — pre-2020 give **`Milyon TL`** (million); recent give
  **`Milyar TL`** (billion). Canonical = billion TL.
- *Transaction counts* — always `(Bin)` (thousands); unaffected.

**Cross-era stability.** The 2025 reports added `*` footnote markers to headers
(`EFT` → `EFT *`, `Kurumsal` → `Kurumsal*`); the parser strips them so slugs stay
stable across the whole series. A handful of investment sub-instruments (III.3)
and renumbered mobile sub-sections only exist from the year TBB introduced them —
genuine source evolution, not a parsing gap. All headline series (customers,
transfers, payments, gender, age) are continuous across the full history.

### Charted on /digital

| Chart | Series | section / unit |
|---|---|---|
| Active customers — mobile vs internet | `mobile`/`internet` total, `aktif_musteri_sayisi` | I / persons |
| Active individuals by channel usage | mobile-only / both / internet-only | I / persons (digital, individual) |
| Registered customer base by channel | `mobile`/`internet` total, `sistemde_kayitli_en_az_bir_kez_login_olmus_musteri_sayisi` | I / persons |
| Net new registered customers per quarter | QoQ Δ of the registered base (derived; `quarterlyDeltas`) | I / persons |
| Product applications via mobile | `kredi_basvurusu` / `kredi_karti_ve_ek_kart_basvurusu` (mobile total) | II / count |
| Money-transfer volume per quarter | mobile vs internet grand total | III.1 / volume (₺ trn) |
| Money-transfer count per quarter | mobile vs internet grand total | III.1 / count |
| Bill-payment count per quarter | mobile vs internet `fatura_odemeleri` | III.2 / count |
| Active individuals by gender | Kadın / Erkek (TOPLAM) | II / persons (digital) |
| Active individuals by age group | 0–17 … 66+ (TOPLAM) | III / persons (digital) |
| Customers acquired (trailing 3m) — digital vs branch | derived from `tbb_acquisition_stats` (see §13.1) | acquisition / persons |
| Digital share of new customers (%) | derived: remote ÷ (remote + branch), trailing 3m | acquisition / % |

### 13.1 Remote vs branch customer acquisition (`tbb_acquisition_stats`)

A **separate monthly** TBB report — *"Uzaktan ve Şubeden Müşteri Edinim
İstatistikleri"* — distinct from the quarterly digital report above. It exists
because of the 2021 *Uzaktan Kimlik Tespiti* (remote e-KYC) regulation and reports,
per month, how many customers member banks acquired **remotely** (without a branch
visit) vs **at a branch**. Sector-wide; no per-bank breakdown. Ingestion:
[`src/tbb/acquisition.py`](../src/tbb/acquisition.py) driven by
[`scripts/update_tbb_acquisition.py`](../scripts/update_tbb_acquisition.py). Each
monthly workbook is **cumulative** (full history Mayıs 2021 → latest), so one fetch
refreshes everything. Surfaces in the **"Customer acquisition — digital vs branch"**
section of `/digital` ([`web/app/lib/acquisition.ts`](../web/app/lib/acquisition.ts)).

| Dimension | Values | Notes |
|---|---|---|
| `period` | `YYYY-MM` | Monthly. |
| `entity_type` | `individual` \| `merchant` \| `legal` | Gerçek Kişiler / Gerçek Kişi Tacirler / Tüzel Kişiler. Merchant & legal only reported from **2024-07**. |
| `method` | `branch` · `remote_rep` · `remote_courier` · `bulk` · `remote_application` | `branch` = finalised in person; `remote_rep` = video call with a representative; `remote_courier` = online application, ID confirmed by courier/field staff; `bulk` = bulk onboarding (payroll/corporate). `remote_application` is **intake** (a funnel count, not a finalised customer) — exclude it from acquisition/share figures. |
| `value` | persons (raw count) | The dashboard rescales to thousands. |

**"Digital" = branch-free finalisation** = `remote_rep + remote_courier + bulk`;
`branch` is non-digital. **Definition break:** individual-panel definitions were
refined as of **Ocak 2023** (the series continues). The monthly series is noisy, so
the dashboard plots a **trailing 3-month sum** for each month (`acquisitionData()`
sums each channel/method over the month plus the prior two; the first two months —
May–Jun 2021 — have no full window). The digital share of individual acquisition
rose from ~30% (2021) to a ~60% peak (2024–25), overtaking branch around 2023.

## 14. Economy tab (macro)

`/economy` adapts the Türkiye macro section of the BBVA (Garanti BBVA
Research) **"Türkiye Economic Outlook"** (1Q26, March 2026) into EVDS data.
Data layer: `web/app/lib/economy.ts`; all series live in `evds_series`
(category `macro`, plus the existing `inflation` / `rates` / `fx` codes).

### Sources (EVDS codes)

| Block | Code | Series | Freq |
|---|---|---|---|
| Growth | `TP.GSYIH26.HY.ZH` | GDP, chain-linked volume index | quarterly |
| Growth | `TP.GSYIH26.HY.CF` | GDP, current prices (TL thousand) | quarterly |
| Growth | `TP.TSANAYMT2021.Y1` | Industrial production, SA+cal adj (2021=100) | monthly |
| Labor | `TP.TIG03` / `TP.TIG06` / `TP.TIG08` | Employed (thousand, SA) / LFP (SA %) / unemployment (SA %) | monthly |
| Inflation | `TP.TUKFIY2025.GENEL` | CPI (2025=100) | monthly |
| Inflation | `TP.PKAUO.S01.D.U` / `.I.U` / `.E.U` | CBRT survey CPI expectations (current y-e / next y-e / 12m) | monthly |
| Policy | `TP.APIFON4` | CBRT effective cost of funding | daily |
| FX | `TP.DK.USD.A` / `TP.RK.T1.Y` | USD/TRY / REER (CPI, 2003=100) | daily / monthly |
| External | `TP.ODANA6.Q01` / `Q04` / `Q31` | Current account / goods balance / net errors & omissions (USD m) | monthly |
| External | `TP.HARICCARIACIK.K8` / `K10` | CA ex gold / ex gold & energy (USD m) | monthly |
| Fiscal | `TP.KB.GEN34` / `GEN35` / `GEN39` | General budget primary / overall / cash balance (TL thousand) | monthly |

### Derivations

- **GDP growth** = y/y % change of the chain-linked volume index (lag 4
  quarters). Quarterly EVDS dates (`2025-Q4`) are parsed to the quarter-start
  date by `evds_client._parse_evds_dates`.
- **CPI y/y & m/m** from the **2025=100** index, which TUIK backcasts to well
  before 2018. `TP.FG.J0` (2003=100) **died at the Jan-2026 rebase** — do not
  use it for current inflation.
- **Ex-ante real policy rate** = ((1 + funding/100) / (1 + πᵉ/100) − 1) × 100,
  where funding = monthly average of `TP.APIFON4` and πᵉ = 12m-ahead market
  expectation (`TP.PKAUO.S01.E.U`).
- **Current account / NEO** = trailing 12-month rolling sums, USD m → USD bn.
- **Fiscal balances (% GDP)** = trailing 12-month rolling sum of the monthly
  balance ÷ the most recent completed rolling-4-quarter **nominal** GDP at or
  before that month (both TL thousand, units cancel).
- **Caveat:** `TP.KB.GEN*` is the Treasury **general budget** (cash based) —
  slightly narrower than the *central government* budget BBVA charts, but the
  12m/%-GDP profile tracks it closely (2025: −2.84% vs BBVA's −2.9%).

### Not reproducible here (and why)

CDS spreads, OIS pricing, sovereign yield curves, BIST/MSCI indices
(Bloomberg); GDP nowcast and Financial Conditions Index (BBVA-proprietary
models); foreigners' positioning / carry stock (CBRT securities statistics
not ingested). Investment-fund *levels and composition* are now ingested from
TEFAS (§15, the /funds tab) — pure flow series (subscriptions/redemptions) are
still not derivable (AUM deltas mix flows with valuation). The static **BBVA baseline
scenario table** (report p. 42) is embedded in `economy.ts` for context —
refresh it when a new quarterly outlook is published. The non-reproducible
numbers themselves (CDS, OIS, carry/positioning, nowcast, FCI, sensitivities)
are preserved per edition in
[knowledge/bbva-economic-outlook/](knowledge/bbva-economic-outlook/).

### Verification

Anchored in `web/app/lib/chart-specs.catalog.json` (`economy.*` specs):
GDP y/y 2025-Q4 = 3.42%, CPI y/y May-26 = 32.6%, CA 12m Mar-26 = −$39.7bn,
unemployment Apr-26 = 8.2% — all match the published BBVA/TURKSTAT/CBRT
figures; `scripts/verify_chart_spec.py` re-checks daily in the healthcheck
(rolling sums supported via the `rolling_sum` transform op).

### Balance of Payments sub-page (`/economy/balance-of-payments`)

Reproduces the Albaraka Türk **«Ödemeler Dengesi»** monthly report (10
figures + summary table) from TCMB BoP statistics. Data layer:
`web/app/lib/bop.ts`; charts `TimeSeriesChart` (lines) and `BopFlowChart`
(signed-stacked bars + optional right-axis / dotted overlay). All raw
series are monthly USD m; "12m rolling" panels use a trailing-12-month sum
÷ 1,000 → USD bn. Codes verified to the report's Apr-2026 summary table.

| Figure | Series / derivation |
|---|---|
| Şekil 1 Current account (12m) | `TP.ODANA6.Q01`; ex-energy `TP.HARICCARIACIK.K9`; core `…K10` |
| Şekil 2 Goods & tourism (12m) | goods `TP.ODANA6.Q04`; net travel `TP.ODEAYRSUNUM6.Q41` |
| Şekil 3 Capital inflows (monthly) | FDI `…Q108`, portfolio `…Q119`, loans `…Q157`, trade credits `…Q188` (net liab. incurred) |
| Şekil 4 Direct investment | real estate `…Q113`; **other = Q108 − Q113**; 12m line = roll12(`…Q108`) |
| Şekil 5 Portfolio | equity & fund shares `…Q212`, debt securities `…Q123`; 12m line = roll12(`…Q119`) |
| Şekil 6 Loans by borrower | banks `…Q166`, general govt `…Q171`, other sectors `…Q179` |
| Şekil 7 Trade credits (12m) | `…Q188` |
| Şekil 8 Currency & deposits (12m) | net asset acq. `…Q138`; net liab. incurred `…Q143` |
| Şekil 9 Net errors & omissions (12m) | `TP.ODANA6.Q31` |
| Şekil 10 Financing of the deficit | need = `Q01`; **net foreign inv. = Q102 + Q114 + Q136**; **reserves − errors = Q204 − Q31** (dotted) |

**Financing identity** (Şekil 10, BPM6, signs as published): current account
≡ net foreign investment + (reserve assets − net errors). Apr-2026 reconciles
to −5.70 ≈ −19.19 + 13.48 (USD bn). The «net foreign investment» line is the
clean FDI+portfolio+other-investment net total; the source deck's right-side
annotation on this line uses a slightly wider grouping, so the dashboard label
states the exact definition. All 21 detail codes (`TP.ODEAYRSUNUM6.*`,
`TP.HARICCARIACIK.K4/K7/K9`) are in `evds_series` (category `macro`); five
`economy.bop_*` chart-specs anchor the daily verification.

**Foreign Portfolio Flows — Weekly** (same page, data layer
`web/app/lib/portfolio-flows.ts`): the dataset behind the widely-cited weekly
"foreigners net bought/sold $X of equities" chart. Source is TCMB **«Yurt Dışı
Yerleşikler Menkul Kıymet İstatistikleri»** (EVDS datagroup `bie_mknethar`,
**weekly, Friday, USD million**), distinct from — and more timely than — the
monthly BoP portfolio line above. The net-transaction series are already the
weekly net flow (net buy +, net sell −); no de-cumulation. Four series in
`evds_series` (category `macro`, freq weekly):

| Series | Meaning |
|---|---|
| `TP.MKNETHAR.M7` | Net **equity** transactions (weekly flow) — the headline bar chart |
| `TP.MKNETHAR.M8` | Net **GDDS** (govt domestic debt securities / DİBS) transactions |
| `TP.MKNETHAR.M1` | Equity **holdings** (stock) |
| `TP.MKNETHAR.M2` | GDDS **holdings** (stock) |

Verified against the press chart: `M7` 2026-06-12 = −117.8 ("sold $118m
equities"), 2026-06-05 = −856.9 (the −857 bar), 2026-04-17 = +579.4 (+579).
History from 11-09-2020. Weekly bars show the last 110 weeks; holdings ÷ 1,000
→ USD bn.

### Economic Growth sub-page (`/economy/economic-growth`)

Reproduces the Albaraka **«Ekonomik Büyüme»** quarterly GDP report from TÜİK
national accounts (2021 reference year, **chain-linked volume indices**,
quarterly). Data layer: `web/app/lib/growth.ts`. y/y growth is computed from
the index **level** (`v[t]/v[t−4] − 1`) — these are index series, not
pre-computed %.

| Figure / element | Series / derivation |
|---|---|
| KPIs | GDP y/y from `TP.GSYIH26.HY.ZH`; nominal ₺ from `…HY.CF` ÷1e9 (quarter + trailing-4Q) |
| Şekil 1 GDP growth (y/y) | `TP.GSYIH26.HY.ZH` y/y |
| Şekil 2 contributions (pp) | derived: `contribᵢ = (realᵢ[t] − realᵢ[t−4]) / GDP_real[t−4] × 100`, imports subtract, **inventories = residual** (GDP y/y − Σ). Components `TP.GSYIH20/21/22/24/25.HY.ZH` |
| Şekil 3 sectoral (y/y) | `TP.GSYIH01/02/04/05.IFK.ZH` |
| Şekil 6 government (y/y) | `TP.GSYIH21.HY.ZH` |
| Production table (14 rows) | `TP.GSYIH01..13.IFK.ZH` |
| Expenditure table (6 aggregates) | `TP.GSYIH20/21/22/24/25/26.HY.ZH` |

Contributions were validated against the report's cover (consumption +3.4,
investment +0.8, exports −2.9 pp — exact). Two `economy.growth_*` chart-specs
anchor the daily verification.

**EVDS coverage gaps (NOT wired — would need a TÜİK national-accounts Excel
scraper):** the seasonally-/calendar-adjusted GDP index (Şekil 1's **q/q**
line); the expenditure **detail** (durable/semi-/non-durable consumption =
Şekil 5; construction/machinery/other investment = Şekil 4, and the matching
table sub-rows); and the **calendar-adjusted** production variant — EVDS
carries only the unadjusted index, so a few production rows (industry,
manufacturing, services, public admin) differ from TÜİK's headline by up to
~1.5 pp while the GDP total matches exactly.

### Central-Government Budget sub-page (`/economy/budget`)

Reproduces the Albaraka **«Bütçe Görünümü»** monthly report from the TÜİK/
Treasury **central-government budget** (merkezi yönetim bütçesi) in EVDS
(cat 1503: `bie_kbmgel` revenues + `bie_kbmgid` expenses). Data layer:
`web/app/lib/budget.ts`. EVDS values scale **÷1e3 → million TL** (the report
table) and **÷1e6 → bn TL** (figures/KPIs). **Distinct from the cash
general-budget `TP.KB.GEN34/35/39`** already in the registry — those are
~117 bn off the central-government balance at 12m; do not conflate them.

| Element | Series / derivation |
|---|---|
| KPIs (12m) | balance / primary / tax revenue (rolling 12m) |
| Şekil 1 budget & primary (12m) | derived **balance = GEL001 − GID001**, **primary = GEL001 − GID002** |
| Şekil 5 monthly balance | derived balance (monthly) |
| Şekil 4 revenue growth (y/y, 3m MA) | tax `GEL003`; **non-tax = GEL001 − GEL003** |
| Şekil 3 tax mix (this month vs year ago) | `GEL005/010/018/021/033/035/036`, petrol-gas ÖTV `GEL022` |
| Şekil 2 expenditure mix | `GID003/008/014/026/110/116/131` |
| Table (17 rows) | the GEL/GID codes above + GID001/002/152, derived balances |

The three derivations (budget balance, primary balance, non-tax revenues) have
no direct EVDS series; all reproduce the report's Apr-2026 table exactly
(balance 12m −1,672,375; primary +791,101; tax 12,611,906 mn TL). 23 new
`TP.KB.GEL*/GID*` series in `evds_series` (`macro`/monthly); two
`economy.budget_*` chart-specs (one exercising the `derive`+`rolling_sum`
chain) anchor the daily verification.

### Inflation sub-page (`/economy/inflation`)

Reproduces the Albaraka **«Enflasyon»** monthly report from TÜİK CPI (2025=100)
and domestic PPI (Yİ-ÜFE) series in EVDS. Data layer:
`web/app/lib/inflation.ts`. All inputs are monthly index levels; every metric
is a scale-invariant derivation: **m/m** = `v/v[-1]−1`, **y/y** = `v/v[-12]−1`,
**cumulative-since-Dec** = `v/Dec[-1]−1`, **12-month-average y/y** = ratio of
trailing-12m index averages (the exact TÜİK convention — *not* the mean of 12
monthly y/y figures, which is ~0.1 pp off).

| Element | Series |
|---|---|
| KPIs / Şekil 1 | CPI `TP.TUKFIY2025.GENEL`, Core C `TP.FE25.OKTG04`, PPI `TP.TUFE1YI.T1` (y/y) |
| Şekil 6 core | `TP.FE25.OKTG04` (m/m + y/y) |
| Core table A/B/C/D | `TP.FE25.OKTG02/03/04/05` |
| Şekil 4 clothing | `TP.TUKFIY2025.03` (m/m) |
| Şekil 5 electricity & gas | `TP.TUFE1YI.T118` (m/m) |
| Şekil 2 CPI groups | `TP.TUKFIY2025.01–13` (m/m) |
| Şekil 3 PPI sectors | `TP.TUFE1YI.T{16,6,49,52,61,64,73,79,93,30,28,114}` (m/m) |
| Table 1 history | GENEL + T1 (m/m, y/y) |

**Gotchas:** Core **C** (`OKTG04`, excl. energy/food/alc-tob/gold) is the
headline "çekirdek". CPI 2025=100 levels are ≈116–129 while the PPI
`TP.TUFE1YI.*` family is still 2003-base (≈5454) — never compare levels, but
all %-derivations are scale-invariant. **Two coverage gaps (TÜİK-Excel only,
not in EVDS, flagged in-page):** (1) Şekil 2/3 plot weighted **contributions**
(need group weights) → the page shows **m/m % per group** instead; (2) the PPI
**Main-Industrial-Groupings** table (intermediate/durable/energy/capital
goods) — only the Yurtiçi-ÜFE header maps. 28 new series in `evds_series`
(category `inflation`/monthly); two `economy.inflation_*` chart-specs anchor
verification.

### TÜİK direct-detail lane (fills part of the EVDS gaps above)

Some report data is published only by TÜİK, not EVDS. The `src/tuik/` lane
pulls it deterministically (no API/LLM) and stores it in the **shared
`evds_series` table** under `TUIK.*` codes, so the whole access path
(`evdsMulti`, `push_to_d1`, the chart-spec verifier) works unchanged.

**Access recipe** (see `reference_tuik_data_access` memory): a cookie session
on `veriportali.tuik.gov.tr` (`/<lang>/statistical-themes` → sets `NSC_ESNS`
→ `/api/<lang>/data/statistical-themes` with Referer/Origin/X-Requested-With)
returns the theme tree whose leaf `url`s are the exact
`/api/<lang>/data/downloads?t=i&p=<encoded>` **.xls** URLs (OLE2/BIFF → xlrd,
the TBB pattern). The SDMX `nsiws.tuik.gov.tr/rest` endpoint 401s; the
`data.tuik.gov.tr/Bulten` pages are JS-only — both avoided.

| Filled | TÜİK table → codes | Page |
|---|---|---|
| Şekil 5 consumption detail | "Household final consumption by durability…" → `TUIK.NA.CONS_{DURABLE,SEMIDUR,NONDUR,SERVICES}` (chain-vol index, quarterly) | growth |
| Şekil 4 investment detail | "Gross fixed capital formation in chain linked…" → `TUIK.NA.GFCF_{CONSTRUCTION,MACHINERY,OTHER}` | growth |
| Inflation PPI MIG table | "Domestic PPI — Main Industrial Groupings (2003=100)" → `TUIK.PPI.MIG_*` (index, monthly) | inflation |
| (context) CPI group weights | "Weights for main groups…" → `TUIK.WEIGHT.CPI_01..13` (annual) | — |

All store the raw index level; the pages derive y/y, m/m (verified to the
report: consumption durable −0.22 / services 2.15, investment construction
3.26 / machinery 3.01; PPI MIG energy m/m 6.60). Wired into `refresh.py` as a
**non-critical** step (`--skip-tuik`), runs **in CI** on the EVDS lane and rides
its `evds_series` push. Two `economy.{growth_tuik_detail,inflation_ppi_mig}`
chart-specs anchor it. **Still on the EVDS fallback (not filled):** GDP q/q SA
line + calendar-adjusted production (messy interleaved-annual Excel) and exact
weighted contributions for Şekil 2/3 (TÜİK's only contribution table is a
lagged single-month snapshot; weight×m/m is approximate) — Şekil 2/3 keep m/m.

### Foreign Trade sub-page (`/economy/foreign-trade`)

Reproduces the Albaraka **«Dış Ticaret Dengesi»** report from TÜİK customs-trade
series in EVDS. Data layer: `web/app/lib/foreign-trade.ts`. **Unit traps:** the
BEC trade flows (`TP.IHRACATBEC.*` / `TP.ITHALATBEC.*`) are USD **thousand**
(÷1e6 → bn$); the energy balance `TP.HARICCARIACIK.K7` is USD **million**
(÷1e3 → bn$) — do not mix. "Annualised" panels are trailing-12m rolling sums.

| Figure | Series / derivation |
|---|---|
| KPIs | trailing-3-month `…BEC.9999` exports/imports; deficit = imp − exp |
| Şekil 1 balance + ex-energy | `bal = roll12(IHRACATBEC.9999) − roll12(ITHALATBEC.9999)`; ex-energy `= bal − roll12(K7)/1e3` |
| Şekil 2-3 exports/imports + growth | `…BEC.9999` (12m level + y/y) |
| Şekil 4 coverage | `exports/imports × 100` (12m) |
| Şekil 5 terms of trade | `TP.DT.IH.FIY.D01.2010 / TP.DT.IT.FIY.D01.2010 × 100` (unit-value indices, 2015=100) |
| Şekil 6-7 by BEC group | `…BEC.1/.2/.3` (investment/intermediate/consumption) |
| Şekil 8 energy deficit + Brent | `roll12(K7)/1e3` + `TP.BRENTPETROL.EUBP` (monthly avg) |

Verified to the report's Q2-2022 vintage (exports 246.0, imports 322.6, balance
−76.6, coverage 76.3, terms 76.55, energy deficit −67.69 exact). 11 new EVDS
series (`macro`/monthly; K7 already ingested); two `economy.foreign_trade_*`
chart-specs (one exercises `derive`, one `ratio`) anchor it at 2022-06.
**Not reproduced (flagged in-page):** the «Çekirdek Denge» core-balance line (an
Albaraka-internal construction — `tb − K7 − K4` gives the wrong sign, ~8 bn off;
proprietary) and the HS-chapter («Fasıl») tables Şekil 9 (TÜİK's dynamic
foreign-trade DB only — not in EVDS, nor the TÜİK theme-tree Excel downloads).

## 15. TEFAS fund-market statistics

Source: **TEFAS** (Turkey Electronic Fund Trading Platform, tefas.gov.tr) —
two JSON POST endpoints behind the fon-verileri SPA:
`api/funds/fonGnlBlgSiraliGetir` (per fund per day: NAV `fiyat`, AUM
`portfoyBuyukluk` in TL, investor count `kisiSayisi`, units outstanding) and
`api/funds/dagilimSiraliGetirT` (per fund per day portfolio allocation across
~55 sparse percentage fields). Data is T+1, trading days only; history is a
**rolling ~5 years** (the server rejects start dates older than 5 years:
"Başlangıç Tarihi 5 yıldan eski olamaz"). Server limits: ~6 requests/min,
max 30 days per request
(client paces at ~5.5/min — see [OPERATIONS.md](OPERATIONS.md) §TEFAS).
Ingestion: [`src/tefas/`](../src/tefas/) driven by
[`scripts/update_tefas.py`](../scripts/update_tefas.py). Surfaces on the
**/funds** tab ([`web/app/lib/funds.ts`](../web/app/lib/funds.ts)).

**Aggregated at ingest.** Per-fund rows (~7k/day across types) are never
persisted — each fetch window carries *every* fund for the dates it covers,
so complete per-date aggregates are computed in memory and only those land
in SQLite/D1 (four skinny tables, AUM in raw TL). Consequence: changing any
normalization rule below requires re-running the backfill
(`backfill-tefas.yml`, resumable, ~2.5–3 h).

| Table | Grain | Content |
|---|---|---|
| `tefas_manager_daily` | date × fon_tipi × manager | Σ AUM, fund count, Σ investor accounts |
| `tefas_category_daily` | date × fon_tipi × category | same, grouped by fund category |
| `tefas_allocation_daily` | date × fon_tipi × asset_class | AUM-weighted allocation % + covered-AUM base |
| `tefas_top_funds` | date × fon_tipi × fon_kodu | top 15 by AUM (rank, name, manager, NAV, investors) |

**Fund types** (`fon_tipi`): YAT mutual (~2,000 funds/day), EMK pension
(~400), BYF ETF (~30), GYF real-estate (~250), GSYF venture (~500). GYF/GSYF
are **not daily-priced** — stored as-is but excluded from /funds time series
(a single date's SUM only counts the funds that happened to report).

**Derived dimensions** (deterministic, in
[`src/tefas/normalize.py`](../src/tefas/normalize.py), unit-tested):

- **manager** — fund-title prefix through the `PORTFÖY` token
  (`"AK PORTFÖY ÇOKLU VARLIK …"` → `AK PORTFÖY`); EMK funds (run by pension
  companies) take the prefix through `EMEKLİLİK` (+ `A.Ş.` when adjacent);
  fallback = first two tokens. Mis-bucketing only affects manager-level
  views — sector sums are invariant to the grouping.
- **category** — first-match keyword scan of the fund title: `PARA PİYASASI`
  → money_market, `HİSSE SENEDİ` → equity, `BORÇLANMA ARAÇLARI` → debt,
  `KİRA SERTİFİKALARI` → lease_certificates, `SERBEST` → hedge,
  `ALTIN`/`KIYMETLİ MADEN` → precious_metals, `FON SEPETİ` → fund_of_funds,
  `KATILIM` → participation, `DEĞİŞKEN`/`KARMA` → mixed, else other.
  Specific keywords run before generic ones (`KATILIM HİSSE SENEDİ` → equity).
- **asset_class** — the ~55 allocation fields roll up to 11 classes
  (`ASSET_ROLLUP`): equity_tr (hs, gyy, gsyy) · equity_foreign (yhs) ·
  gov_debt_tr (dt, hb) · gov_debt_fx (kba, eut, db, dot, kibd) · corp_debt
  (ost, fb, bb, vdm, osdb) · foreign_debt (yba, ybkb, ybosb) · participation
  (kh\*, kks\*, osks, oksyd) · money_market (r, tr, tpp, bpp, vm\*, vint) ·
  precious_metals (km, kmbyf, kmkba, kmkks) · fund_units (yyf, byf, ybyf,
  fkb, gykb, gsykb) · other (d, t, gas, ymk, btaa, btas). Legend verified
  against tefas-crawler v0.5.0's legacy field schema; keys the API adds
  later roll to *other* and are logged with their weight (never fatal).

**AUM-weighted allocation.** Over funds having both an info row with AUM > 0
and an allocation row that day:
`weighted_pct[class] = Σ(aum_i × pct_i[class]) / Σ(aum_i)`, with the covered
denominator stored as `aum_base_try`. A fund's unmapped residual
(`100 − Σ mapped`, clamped ≥ 0) goes to *other*. Repo (`r`) and Borsa Para
Piyasası (`bpp`) can be **negative** (money-market borrowing / leverage,
common in serbest funds), so a class share can sit slightly outside 0..100;
each fund's own fields still sum to 100.

**Caveats.** `kisiSayisi` counts investor *accounts per fund* — a person
holding five funds is counted five times, so investor series are levels of
engagement, not unique people. `bilFiyat` (allocation endpoint) and
`borsaBultenFiyat` are ignored.

### Charted on /funds

| Chart | Series | Source table |
|---|---|---|
| AUM by fund type (₺ trn, stacked) | YAT / EMK / BYF, month-end | `tefas_manager_daily` (SUM over managers) |
| Total AUM nominal vs real (index) | deflated by CPI `TP.TUKFIY2025.GENEL` | same + `evds_series` |
| Mutual-fund AUM by category (₺ trn + % stack) | money_market / debt / equity / hedge / precious_metals / rest | `tefas_category_daily` |
| Portfolio allocation (% stack) | 8 display classes (gov/corp debt, equity, … merged from the 11 stored) | `tefas_allocation_daily` |
| Investor accounts & fund counts | per fund type, month-end | `tefas_manager_daily` |
| Largest funds tables | latest top-15 per YAT / EMK / BYF | `tefas_top_funds` |

All time series sample the **month-end trading day** per fund type and chart
by `YYYY-MM` (~60 points over the 5-year history) so per-type samples align.

---

## 16. NIM components decomposition (/profitability)

Replicates the Garanti BBVA Research **"NIM components of private banks
(annualized)"** chart from the BDDK monthly bulletin (verified to 0.1pp on
every bucket for Dec-24 and 2025). Implementation:
`web/app/lib/nim-components.ts` (shaping; pure TS) + `nimComponentsRaw()` in
`web/app/lib/metrics.ts` (one D1 query); chart spec
`profitability.nim_components_private` anchors it in the daily healthcheck.

**Buckets** — `income_statement` `item_order` positions (currency `'TL'`,
`amount_total`, million TL, cumulative YTD). Expense items are stored
**positive** and negated for display:

| Bucket | item_order | Notes |
|---|---|---|
| Customer loans (income) | 1 + 6 | 2–5 are consumer sub-lines of 1 — never added |
| Banks & money market (income) | 7 + 8 | |
| Fixed-income securities (income) | 9 + 10 + 11 + 12 | **incl. reverse-repo income (12)** — BBVA convention |
| Other interest income | 13 + 14 | |
| Customer deposits (expense) | 16 | "participation funds" label for 10003 |
| Interbank & money market (expense) | 17 + 18 | |
| Debt issued & repo (expense) | 19 + 20 | **incl. repo funding expense (20)** — BBVA convention |
| Other interest expense | 21 + 22 | |

15/23/24 are subtotals (excluded); internal sums reconcile: 1+6..14 − (2..5) =
15, 16..22 = 23, net = 24.

**Denominator** = 13-point average of month-end `balance_sheet`
`TOPLAM AKTİFLER` (item 26): Dec(Y−1)…Dec(Y) for annual bars.

**Views.** *Annual*: `YTD(Dec) / avg13 × 100` per year from 2021 (2020 needs
Dec-2019 assets, which predate the data) plus a trailing
**"YYYY ann."** bar when the latest month < Dec: `YTD(m) × 12/m` over the
average of the m+1 month-ends Dec(Y−1)…m — **annualized actuals, not a
forecast** (BBVA's "F" bar is their projection; we don't reproduce it).
*Monthly TTM*: `TTM(m) = YTD(y,m) + FY(y−1) − YTD(y−1,m)` over the 13-month
trailing average of assets ending m; first valid point **2021-01**.

**Bank groups.** Default **Private = deposit codes 10008+10010 summed**
(domestic private + foreign deposit banks) — the BBVA definition; ownership
code 10005 alone misses the chart by 0.3–0.6pp. Also selectable: the two
Private sub-cuts (10008 / 10010), State deposit (10009), Participation
(10003), Dev & Inv (10004), Sector (10001). {10008,10010,10009} ∪ 10003 ∪
10004 partitions the sector. For composite groups a period is emitted only
when every member code has data.

## 17. BIST equity-market data + valuation (/economy, /banks/[ticker])

Borsa İstanbul daily EOD via the **Yahoo Finance chart API**
(`query1.finance.yahoo.com/v8/finance/chart/{symbol}`, keyless). Turkish symbol
= `<ticker>.IS`; indices use the index code (`XU100.IS`, `XBANK.IS`). Ingested
by `src/scrapers/bist_scraper.py` into three D1 tables (see migration
`0012_bist.sql`): `bist_prices` (daily OHLCV, banks + indices), `bist_dividends`
(cash dividend events, banks only), `bist_shares` (shares outstanding per bank).

**Universe.** Derived at runtime from `data/banks/bddk_bank_list.json` — the
banks with `listed: true` + a `bist_ticker` (11 banks). **QNBFB** is listed but
its float is ~0.12% and Yahoo carries no tradeable price for `QNBFB.IS`, so it
yields no rows and no valuation (omitted from `bist_shares.json`).

**Index chart (/economy).** XU100 and XBANK levels **rebased to 100** at the
window start (`rebase100()` in the page) so the banking sector's relative
performance against the broad market is directly comparable.

**Valuation (/banks/[ticker]).** Combines the market price with *audited*
fundamentals (`web/app/lib/bank-fundamentals.ts`, methodology shared with the
`/cross-bank` ROE in `heatmap.ts`). Audit amounts are **thousand TL** → ×1000 to
compare against a TL market cap.

| Metric | Definition |
|---|---|
| **Market cap** | latest close × `shares_outstanding` (TL) |
| **P/B** | market cap ÷ period-end **book equity** (label-matched on any roman line — `%ZKAYNAK%`/`%EQUITY%` — so participation banks at XIV. resolve) |
| **P/E** | market cap ÷ **TTM net income** (YTD P&L de-cumulated to single quarters, trailing four summed; telescopes to `YTD(latest)+FY(prior)−YTD(same q prior yr)`, robust to YTD-vs-3-month column quirks) |
| **Dividend yield** | trailing-12m `bist_dividends` per share ÷ latest close |
| **1y change** | latest close ÷ close nearest (latest − 365d) − 1 |

Sanity (GARAN, Jun-2026): close ₺135.9 × 4.2bn = ₺570.8bn market cap; ÷ ₺451.3bn
equity = **P/B 1.26×**; ÷ ₺118.6bn TTM net income = **P/E 4.8×**.

**Shares maintenance.** `bist_shares` is best-effort refreshed each run from
Yahoo `quoteSummary` (cookie+crumb handshake) and falls back to the committed
`data/banks/bist_shares.json` seed; refresh the seed on capital actions
(bonus/rights issues). See [OPERATIONS.md](OPERATIONS.md) §BIST equity market.

**Cross-bank (`/cross-bank`).** `heatmapPanel` also emits **P/B** and **P/E**
columns (neutral color — cheap/expensive isn't good/bad). Market cap per
(bank, period) = the **quarter-end close** (last trading day inside the calendar
quarter, via a `ROW_NUMBER()` window over `bist_prices`) × shares, divided by
the same audited equity / `ttmNet` used elsewhere. **The latest period uses the
freshest price** — live Yahoo quote → else the latest stored EOD close → else
quarter-end — so the Snapshot shows a current P/B/P/E (not a months-old
quarter-end one); historical over-time rows keep their own quarter-end close
(point-in-time). Current shares are used throughout (no historical counts), so
deep-history ratios are approximate across capital actions. Listed banks only —
the unlisted majority render "—".

**Live overlay (delayed Yahoo, `web/app/lib/bist-live.ts`).** All three surfaces
overlay the *latest* Yahoo price at page-render time: `/banks/[ticker]` price +
market cap + P/B/P/E/yield (label "⏱ as of HH:MM · ~15-min delayed", or "last
close DD Mon" when the market is shut); `/cross-bank` snapshot P/B & P/E (live
price on the latest period, else the latest stored close); `/economy`
indices (a live final point appended to each rebased series). Quotes come in one
batched Yahoo `spark` request (not N per-symbol fetches — a burst of 11 gets the
Cloudflare egress IP rate-limited). It's ~15-min
delayed during BIST hours and the last close otherwise — **not** real-time
(that needs a paid feed). Everything is price-linear: `applyLivePrice` rescales
market cap/P/B/P/E by `r = live/stored` and yield by `1/r`. **Caching is
deliberately NOT KV** (the 12h `cachedAll` window guards the ~1k KV-writes/day
cap): the fetch uses Cloudflare's edge cache (`cf.cacheTtl`) + a 60 s per-isolate
in-memory map, with a 2.5 s timeout and graceful fallback to the stored close on
any failure. Kill switch: `BIST_LIVE_DISABLED=1`.

**Market ticker (`/economy`, `/news`).** A scrolling "flowing data" strip
(`web/app/components/MarketTicker.tsx`) of BIST indices (XU100 / Banks / 30),
FX (USD/TRY, EUR/TRY), and commodities (Brent `BZ=F`, gold `GC=F` $/oz, plus a
derived **gram gold ₺** = $/oz ÷ 31.1035 × USD/TRY), each with a day-change %.
Data: `getMarketTicker()` (`web/app/lib/market-ticker.ts`) → one batched
`rawQuotes` spark request (arbitrary Yahoo symbols, no `.IS` append). Server-
rendered, then the client polls `GET /api/market-ticker` every 60 s (edge-cached
so polls don't re-hit Yahoo). Hidden entirely when the fetch fails or
`BIST_LIVE_DISABLED=1`.
