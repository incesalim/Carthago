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
| `/profitability` | ROE, ROA, NIM (annualized). OPEX / avg assets. Fees / revenue. Non-interest income / non-interest expense. Fees / OPEX. Optional ROE-vs-CPI overlay. | §7, §8, §9 (CPI) |
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
| Money-transfer volume per quarter | mobile vs internet grand total | III.1 / volume (₺ trn) |
| Money-transfer count per quarter | mobile vs internet grand total | III.1 / count |
| Bill-payment count per quarter | mobile vs internet `fatura_odemeleri` | III.2 / count |
| Active individuals by gender | Kadın / Erkek (TOPLAM) | II / persons (digital) |
| Active individuals by age group | 0–17 … 66+ (TOPLAM) | III / persons (digital) |

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
not ingested); investment-fund flows (TEFAS). The static **BBVA baseline
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
