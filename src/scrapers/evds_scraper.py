"""EVDS scraper — pull selected TCMB series and write to evds_series table.

Designed to run inside scripts/refresh.py. The daily workflow polls only
daily/workday series; the Saturday full refresh polls every declared cadence.
Idempotent via INSERT OR REPLACE on (code, period_date).

Uses the EVDS HTTP client at src/scrapers/evds_client.py.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# EVDS HTTP client lives alongside this file
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.scrapers import evds_client as evds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "bddk_data.db"


class Series(NamedTuple):
    code: str
    label: str
    category: str  # rates / fx / inflation / cbrt / macro
    freq: int      # 1=daily, 3=weekly, 5=monthly, 6=quarterly


# Curated set — covers everything the legacy /rates tab uses.
SERIES: list[Series] = [
    # Policy rate corridor
    Series("TP.PY.P02.1H", "Policy Rate (1-week repo)", "rates", evds.FREQ_DAILY),
    Series("TP.PY.P01.ON", "ON Borrowing",              "rates", evds.FREQ_DAILY),
    Series("TP.PY.P02.ON", "ON Lending",                "rates", evds.FREQ_DAILY),
    Series("TP.APIFON4",   "CBRT Effective Funding Cost", "rates", evds.FREQ_DAILY),
    Series("TP.BISTTLREF.ORAN", "BIST TRY Reference",   "rates", evds.FREQ_DAILY),

    # Lending / deposit rates (weekly survey)
    Series("TP.KTFTUK",   "Consumer Loan",      "rates", evds.FREQ_WEEKLY),
    Series("TP.KTF17",    "Commercial Loan",    "rates", evds.FREQ_WEEKLY),
    Series("TP.KTF12",    "Housing Loan",       "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT06", "Deposit (TL total)", "rates", evds.FREQ_WEEKLY),

    # FX
    Series("TP.DK.USD.A", "USD/TRY (buying)", "fx", evds.FREQ_DAILY),
    Series("TP.DK.EUR.A", "EUR/TRY (buying)", "fx", evds.FREQ_DAILY),

    # CBRT balance sheet / sterilization
    Series("TP.AB.A01",      "CBRT Total Assets",     "cbrt", evds.FREQ_DAILY),
    Series("TP.AB.A02",      "CBRT Foreign Assets",   "cbrt", evds.FREQ_DAILY),
    Series("TP.AB.A03",      "CBRT Domestic Assets",  "cbrt", evds.FREQ_DAILY),
    Series("TP.APIFON2.TOP", "Sterilization Total",   "cbrt", evds.FREQ_DAILY),
    Series("TP.APIFON2.IHA", "Sterilization Auction", "cbrt", evds.FREQ_DAILY),
    Series("TP.APIFON2.KOT", "Sterilization Quotation", "cbrt", evds.FREQ_DAILY),
    Series("TP.APIFON2.LIK", "Liquidity Bills",       "cbrt", evds.FREQ_DAILY),

    # Inflation. TP.FG.J0 (CPI 2003=100) is NOT ingested: it died at the
    # Jan-2026 TÜİK rebase and polling stopped 2026-11-07 — TUKFIY2025.GENEL
    # below carries the full history alone.
    Series("TP.PKAUO.S01.D.U",  "CPI Expectation, Current Year-End", "inflation", evds.FREQ_MONTHLY),
    Series("TP.PKAUO.S01.I.U",  "CPI Expectation, Next Year-End",    "inflation", evds.FREQ_MONTHLY),
    Series("TP.PKAUO.S01.E.U",  "CPI Expectation, 12m ahead",        "inflation", evds.FREQ_MONTHLY),
    Series("TP.HANEBEK.HAN14A", "Household Inflation Exp, 12m",      "inflation", evds.FREQ_MONTHLY),

    # CBRT net funding (complement to sterilization)
    Series("TP.APIFON3",  "CBRT Net Funding (TL thousand)", "cbrt", evds.FREQ_DAILY),

    # CBRT reserves (international)
    Series("TP.AB.TOPLAM", "Gross Reserves (USD m)", "cbrt", evds.FREQ_WEEKLY),
    Series("TP.AB.C1",     "Gold Reserves (USD m)",  "cbrt", evds.FREQ_WEEKLY),

    # CBRT BS FX positions — for derived net reserves
    Series("TP.BL054", "CBRT FX Assets (TL thousand)",      "cbrt", evds.FREQ_WEEKLY),
    Series("TP.BL122", "CBRT FX Liabilities (TL thousand)", "cbrt", evds.FREQ_WEEKLY),

    # CBRT forward/swap short position (IMF reserve template §2.2.1, USD m,
    # negative) — the off-balance-sheet FX the CBRT owes forward, dominated by
    # swaps. The swap SPOT leg sits in BL054 (verified: net FX position moves
    # with it), so net-reserves-excluding-swaps = derived NIR − |this|. Monthly.
    # (This is the RIGHT swap measure; the domestic swap-auction stock
    # TP.SWAPTEKTAR.* is far narrower and was ~0 for most of 2025.)
    Series("TP.DOVVARNC.K15", "CBRT Forward/Swap Short Position (USD m)", "cbrt", evds.FREQ_MONTHLY),

    # Gold tons (CBRT books)
    Series("TP.BL0021", "Total Gold Reserves (grams)",         "cbrt", evds.FREQ_WEEKLY),
    Series("TP.BL0891", "Banks' Gold at CBRT (grams)",         "cbrt", evds.FREQ_WEEKLY),

    # Residents' FC deposits (dollarization)
    Series("TP.HPBITABLO4.4", "Households USD Deposits (USD m)",         "fx", evds.FREQ_MONTHLY),
    Series("TP.HPBITABLO4.5", "Households EUR Deposits (USD eq, USD m)", "fx", evds.FREQ_MONTHLY),
    Series("TP.HPBITABLO4.7", "Households Precious Metals (USD m)",      "fx", evds.FREQ_MONTHLY),

    # Real effective exchange rate (real appreciation backdrop). EVDS
    # rebased this series 2003=100 → 2025=100 (2026-11-07 audit); same code,
    # level scale changed — % derivations unaffected.
    Series("TP.RK.T1.Y", "REER (CPI based, 2025=100)", "fx", evds.FREQ_MONTHLY),

    # Deposit rates by maturity (≤1m through >12m)
    Series("TP.TRY.MT01", "Deposit rate ≤1m",   "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT02", "Deposit rate 1-3m",  "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT03", "Deposit rate 3-6m",  "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT04", "Deposit rate 6-12m", "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT05", "Deposit rate >12m",  "rates", evds.FREQ_WEEKLY),

    # Lending rate refinements
    Series("TP.KTF18",    "Commercial Loan (ex cards & OD)", "rates", evds.FREQ_WEEKLY),
    Series("TP.KTFTUK01", "Consumer Loan (incl. overdraft)", "rates", evds.FREQ_WEEKLY),

    # FC (USD/EUR) rates — for the BBVA liquidity FC interest-rate spread.
    # Commercial-loan rate by currency (TL analogue = TP.KTF17) and the blended
    # FC deposit rate (TL analogue = TP.TRY.MT06). Both weekly flow survey, %.
    Series("TP.KTF17.USD", "USD Commercial Loan rate", "rates", evds.FREQ_WEEKLY),
    Series("TP.KTF17.EUR", "EUR Commercial Loan rate", "rates", evds.FREQ_WEEKLY),
    Series("TP.USD.MT06",  "USD Deposit rate (total)", "rates", evds.FREQ_WEEKLY),
    Series("TP.EUR.MT06",  "EUR Deposit rate (total)", "rates", evds.FREQ_WEEKLY),

    # ------------------------------------------------------------------
    # Macro block — feeds the /economy tab (BBVA Türkiye Economic Outlook
    # adaptation). CPI rides TP.TUKFIY2025.GENEL alone since the Jan-2026
    # TÜİK rebase killed TP.FG.J0 (polling of the dead code stopped
    # 2026-11-07).
    # ------------------------------------------------------------------
    Series("TP.TUKFIY2025.GENEL", "CPI (2025=100)", "inflation", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # National accounts (TURKSTAT, quarterly). Recoded 2026-11-07: EVDS
    # re-schemed quarterly GDP with the Q2-2026 release and every old
    # TP.GSYIH*.HY.ZH/.HY.CF/.IFK.ZH code went 400 (site had frozen at
    # Q1-2026). New scheme: expenditure chain-vol = bie_gsyhhrczinc
    # (TP.GSYIH20.CY.*), current prices = bie_gsyhhrccar (TP.GSYIH20.BY.*),
    # production A10 chain-vol = bie_gsyhuretzinc (TP.GSYIH40.IFC.*).
    # Levels differ from the old scheme only by small backward revisions
    # (~0.5% at 2026-Q1); CY.P7 imports stay POSITIVE despite the "(Eksi)"
    # in the EVDS name, so contributions math is unchanged. The old
    # sectoral-total GVA (TP.GSYIH12.IFK.ZH) has no direct equivalent —
    # web/app/lib/growth.ts derives GVA = IFC.B1GQ − D21X31.
    # ------------------------------------------------------------------
    Series("TP.GSYIH20.CY.B1GQ", "GDP (chain-linked volume index)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH20.BY.B1GQ", "GDP (current prices, TL thousand)", "macro", evds.FREQ_QUARTERLY),

    # ------------------------------------------------------------------
    # National-accounts detail — feeds the /economy/economic-growth page
    # (Albaraka "Ekonomik Büyüme" quarterly report). TUIK chain-linked
    # volume indices (raw/unadjusted); the page computes y/y from the level
    # (v[t]/v[t-4]-1) and the Şekil 2 growth-contributions. NOTE: EVDS
    # carries only the top-level expenditure aggregates (not
    # durable/construction detail) and only the unadjusted production index
    # (the calendar-adjusted variant TUIK headlines on a few sub-sectors is
    # Excel-only — see METRICS.md §14).
    # ------------------------------------------------------------------
    # Expenditure method, chain volume (bie_gsyhhrczinc)
    Series("TP.GSYIH20.CY.P311", "Household Consumption (chain vol.)",         "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH20.CY.P32",  "Government Consumption (chain vol.)",        "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH20.CY.P51G", "Gross Fixed Capital Formation (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH20.CY.P6",   "Exports of Goods & Services (chain vol.)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH20.CY.P7",   "Imports of Goods & Services (chain vol.)",   "macro", evds.FREQ_QUARTERLY),
    # Production method / kind of activity, A10 aggregation (bie_gsyhuretzinc)
    Series("TP.GSYIH40.IFC.A",     "GVA: Agriculture (chain vol.)",               "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.BTE",   "GVA: Industry (chain vol.)",                  "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.C",     "GVA: Manufacturing (chain vol.)",             "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.F",     "GVA: Construction (chain vol.)",              "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.GTI",   "GVA: Services (chain vol.)",                  "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.J",     "GVA: Information & Communication (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.K",     "GVA: Finance & Insurance (chain vol.)",       "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.L",     "GVA: Real Estate (chain vol.)",               "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.MN",    "GVA: Professional/Admin/Support (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.OTQ",   "GVA: Public Admin/Education/Health (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.RTU",   "GVA: Other Services (chain vol.)",            "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.B1GQ",  "GDP at purchaser prices (chain vol., prod.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH40.IFC.D21X31", "Taxes less Subsidies (chain vol.)",         "macro", evds.FREQ_QUARTERLY),

    # Industrial production (TURKSTAT, SA + calendar adjusted, 2021=100).
    # Recoded 2026-11-07: .Y1 froze at Jun-2026 when TÜİK recoded the group;
    # .BCD is the same "Toplam Sanayi" SA aggregate under its new code.
    Series("TP.TSANAYMT2021.BCD", "Industrial Production (SA, 2021=100)", "macro", evds.FREQ_MONTHLY),

    # Labor market (TURKSTAT, seasonally adjusted, monthly)
    Series("TP.TIG03", "Employed (thousand persons, SA)",        "macro", evds.FREQ_MONTHLY),
    Series("TP.TIG06", "Labour Force Participation Rate (SA %)", "macro", evds.FREQ_MONTHLY),
    Series("TP.TIG08", "Unemployment Rate (SA %)",               "macro", evds.FREQ_MONTHLY),

    # Balance of payments (CBRT, monthly, USD million)
    Series("TP.ODANA6.Q01", "Current Account (USD m)",        "macro", evds.FREQ_MONTHLY),
    Series("TP.ODANA6.Q04", "Balance on Goods (USD m)",       "macro", evds.FREQ_MONTHLY),
    Series("TP.ODANA6.Q31", "Net Errors & Omissions (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.HARICCARIACIK.K8",  "Current Account ex Gold (USD m)",          "macro", evds.FREQ_MONTHLY),
    Series("TP.HARICCARIACIK.K10", "Current Account ex Gold & Energy (USD m)", "macro", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # Balance-of-payments detail — feeds the /economy/balance-of-payments
    # page (Albaraka "Ödemeler Dengesi" monthly report). Gold/energy
    # sub-balances come from bie_hariccariacik; the financial-account and
    # services detail from the BPM6 detailed presentation (bie_odeayrsunum6).
    # All monthly, USD million; the page rolls 12m and divides by 1000 for
    # bn$. Codes verified against the report's summary table (Apr-2026).
    # ------------------------------------------------------------------
    Series("TP.HARICCARIACIK.K4", "Non-Monetary Gold Balance (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.HARICCARIACIK.K7", "Energy Balance (USD m)",            "macro", evds.FREQ_MONTHLY),
    Series("TP.HARICCARIACIK.K9", "Current Account ex Energy (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q20",  "Services Balance (USD m)",                       "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q41",  "Travel Balance, net (USD m)",                    "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q102", "Direct Investment, net (USD m)",                 "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q108", "Direct Investment — net liab. incurred (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q113", "FDI Real Estate — net liab. (USD m)",            "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q114", "Portfolio Investment, net (USD m)",              "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q119", "Portfolio — net liab. incurred (USD m)",         "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q212", "Portfolio liab. — Equity & fund shares (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q123", "Portfolio liab. — Debt securities (USD m)",      "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q136", "Other Investment, net (USD m)",                  "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q157", "Loans — net liab. incurred, total (USD m)",      "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q166", "Loans liab. — Banks (USD m)",                    "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q171", "Loans liab. — General Government (USD m)",       "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q179", "Loans liab. — Other Sectors (USD m)",            "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q188", "Trade Credits — net liab. incurred (USD m)",     "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q138", "Currency & Deposits — net asset acq. (USD m)",   "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q143", "Currency & Deposits — net liab. incurred (USD m)", "macro", evds.FREQ_MONTHLY),
    Series("TP.ODEAYRSUNUM6.Q204", "Reserve Assets (USD m)",                         "macro", evds.FREQ_MONTHLY),

    # Fiscal — Treasury general budget, cash based (monthly, TL thousand)
    Series("TP.KB.GEN34", "General Budget Primary Balance (TL thousand)", "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEN35", "General Budget Balance (TL thousand)",         "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEN39", "General Budget Cash Balance (TL thousand)",    "macro", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # Central Government Budget (Merkezi Yönetim Bütçesi) — feeds the
    # /economy/budget page (Albaraka "Bütçe Görünümü" monthly report).
    # Hazine ve Maliye Bakanlığı, accrual; EVDS cat 1503 (bie_kbmgel
    # revenues + bie_kbmgid expenses). Monthly, native unit = TL → ÷1e6
    # for bn TL. DISTINCT from the cash GENEL BÜTÇE GEN34/35/39 above
    # (those are ~117 bn off at 12m). Budget balance / primary balance /
    # non-tax revenues have no direct series — derived in budget.ts
    # (GEL001−GID001, GEL001−GID002, GEL001−GEL003). Verified to the
    # report's Apr-2026 table.
    # ------------------------------------------------------------------
    # Revenues (bie_kbmgel)
    Series("TP.KB.GEL001", "Central Govt Budget Revenues (TL)",        "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL003", "Central Govt Tax Revenues (TL)",           "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL005", "Income Tax (TL)",                          "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL010", "Corporate Tax (TL)",                       "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL016", "Motor Vehicle Tax (TL)",                   "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL018", "Domestic VAT (TL)",                        "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL021", "Special Consumption Tax (ÖTV total) (TL)", "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL022", "ÖTV — Petroleum & Natural Gas (TL)",       "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL033", "VAT on Imports (TL)",                      "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL035", "Stamp Duty (TL)",                          "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL036", "Fees / Harçlar (TL)",                      "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL038", "Enterprise & Property Income (TL)",        "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GEL061", "Interest, Shares & Fines (TL)",            "macro", evds.FREQ_MONTHLY),
    # Expenditures (bie_kbmgid)
    Series("TP.KB.GID001", "Central Govt Budget Expenditures (TL)",    "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID002", "Primary (Non-Interest) Expenditure (TL)",  "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID003", "Personnel Expenditure (TL)",               "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID008", "Social Security State Premium (TL)",       "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID014", "Goods & Services Purchases (TL)",          "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID026", "Current Transfers (TL)",                   "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID110", "Capital Expenditure (TL)",                 "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID116", "Capital Transfers (TL)",                   "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID131", "Lending / Borç Verme (TL)",                "macro", evds.FREQ_MONTHLY),
    Series("TP.KB.GID152", "Interest Expenditure (TL)",                "macro", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # Inflation detail — feeds the /economy/inflation page (Albaraka
    # "Enflasyon" monthly report). TÜİK CPI 2025=100 core + COICOP groups
    # and the Yİ-ÜFE (domestic PPI) NACE family. All monthly index levels;
    # the page derives m/m, y/y, cumulative-since-Dec, and 12m-avg (ratio of
    # trailing-12m index averages). NOTE: CPI 2025=100 levels ≈116–129 while
    # the PPI TP.TUFE1YI.* family is still 2003-base (≈5454) — % derivations
    # are scale-invariant so this only matters for raw-level charts (none).
    # Şekil 2/3 plot weighted CONTRIBUTIONS (need TÜİK group weights, not in
    # EVDS) → the page shows m/m % per group instead. Verified to the report.
    # ------------------------------------------------------------------
    # CPI 2025=100 core (özel kapsamlı) indices
    Series("TP.FE25.OKTG02", "CPI Core A (excl. seasonal, 2025=100)",                  "inflation", evds.FREQ_MONTHLY),
    Series("TP.FE25.OKTG03", "CPI Core B (excl. unproc. food/energy/alc-tob/gold)",    "inflation", evds.FREQ_MONTHLY),
    Series("TP.FE25.OKTG04", "CPI Core C (excl. energy/food/alc-tob/gold)",            "inflation", evds.FREQ_MONTHLY),
    Series("TP.FE25.OKTG05", "CPI Core D (excl. unproc. food/alc-tob)",                "inflation", evds.FREQ_MONTHLY),
    # CPI 2025=100 COICOP main groups
    Series("TP.TUKFIY2025.01", "CPI 01 Food & non-alcoholic beverages",   "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.02", "CPI 02 Alcoholic beverages & tobacco",    "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.03", "CPI 03 Clothing & footwear",              "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.04", "CPI 04 Housing, water, electricity, gas", "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.05", "CPI 05 Furnishings & household equipment","inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.06", "CPI 06 Health",                           "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.07", "CPI 07 Transport",                        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.08", "CPI 08 Information & communication",       "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.09", "CPI 09 Recreation, sports & culture",     "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.10", "CPI 10 Education services",               "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.11", "CPI 11 Restaurants & accommodation",      "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.12", "CPI 12 Insurance & financial services",   "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUKFIY2025.13", "CPI 13 Personal care & misc",             "inflation", evds.FREQ_MONTHLY),
    # Yİ-ÜFE (domestic PPI) — headline + NACE sub-sectors (2003-base)
    Series("TP.TUFE1YI.T1",   "PPI Yİ-ÜFE General (domestic PPI)",        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T118", "PPI Electricity, gas, steam & A/C",        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T16",  "PPI Food products",                        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T6",   "PPI Crude petroleum & natural gas",        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T49",  "PPI Coke & refined petroleum",             "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T52",  "PPI Chemicals & chemical products",        "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T61",  "PPI Rubber & plastic products",            "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T64",  "PPI Other non-metallic mineral products",  "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T73",  "PPI Basic metals",                         "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T79",  "PPI Fabricated metal products",            "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T93",  "PPI Electrical equipment",                 "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T30",  "PPI Textiles",                             "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T28",  "PPI Tobacco products",                     "inflation", evds.FREQ_MONTHLY),
    Series("TP.TUFE1YI.T114", "PPI Other manufactured goods",             "inflation", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # Foreign trade (TÜİK customs, general trade system) — feeds the
    # /economy/foreign-trade page (Albaraka "Dış Ticaret Dengesi"). BEC
    # trade flows are USD THOUSAND (÷1e6 for bn$); unit-value indices are
    # 2015=100; Brent is USD/bbl. The page rolls 12m and derives trade
    # balance / coverage / terms-of-trade. Energy balance for Şekil 8 reuses
    # the already-ingested TP.HARICCARIACIK.K7. Verified to the report (Q2-22).
    # ------------------------------------------------------------------
    Series("TP.IHRACATBEC.9999", "Exports, total (customs, USD k)",            "macro", evds.FREQ_MONTHLY),
    Series("TP.ITHALATBEC.9999", "Imports, total (customs, USD k)",            "macro", evds.FREQ_MONTHLY),
    Series("TP.IHRACATBEC.1",    "Exports — Investment goods (BEC, USD k)",    "macro", evds.FREQ_MONTHLY),
    Series("TP.IHRACATBEC.2",    "Exports — Intermediate goods (BEC, USD k)",  "macro", evds.FREQ_MONTHLY),
    Series("TP.IHRACATBEC.3",    "Exports — Consumption goods (BEC, USD k)",   "macro", evds.FREQ_MONTHLY),
    Series("TP.ITHALATBEC.1",    "Imports — Investment goods (BEC, USD k)",    "macro", evds.FREQ_MONTHLY),
    Series("TP.ITHALATBEC.2",    "Imports — Intermediate goods (BEC, USD k)",  "macro", evds.FREQ_MONTHLY),
    Series("TP.ITHALATBEC.3",    "Imports — Consumption goods (BEC, USD k)",   "macro", evds.FREQ_MONTHLY),
    Series("TP.DT.IH.FIY.D01.2010", "Export Unit-Value Index (BEC, 2015=100)", "macro", evds.FREQ_MONTHLY),
    Series("TP.DT.IT.FIY.D01.2010", "Import Unit-Value Index (BEC, 2015=100)", "macro", evds.FREQ_MONTHLY),
    Series("TP.BRENTPETROL.EUBP",   "Brent Crude, European spot FOB (USD/bbl)", "macro", evds.FREQ_MONTHLY),

    # ------------------------------------------------------------------
    # Non-resident securities portfolio (weekly, Friday) — TCMB "Yurt Dışı
    # Yerleşikler Menkul Kıymet İstatistikleri" (datagroup bie_mknethar).
    # The dataset behind the widely-cited weekly foreign-flows chart. All
    # USD MILLION; net-transaction series (M7/M8) are the WEEKLY flow (net
    # buy +, net sell −), stock series (M1/M2) are holdings. Verified against
    # the press chart: M7 2026-06-12 = −117.8 ("sold $118m equities"),
    # 2026-06-05 = −856.9 (the −857 bar). History from 11-09-2020. Feeds
    # /economy/balance-of-payments (lib/portfolio-flows.ts).
    # ------------------------------------------------------------------
    Series("TP.MKNETHAR.M7", "Non-residents Net Equity Transactions (weekly, USD m)", "macro", evds.FREQ_WEEKLY),
    Series("TP.MKNETHAR.M8", "Non-residents Net GDDS Transactions (weekly, USD m)",   "macro", evds.FREQ_WEEKLY),
    Series("TP.MKNETHAR.M1", "Non-residents Equity Holdings (stock, USD m)",          "macro", evds.FREQ_WEEKLY),
    Series("TP.MKNETHAR.M2", "Non-residents GDDS Holdings (stock, USD m)",            "macro", evds.FREQ_WEEKLY),

    # ------------------------------------------------------------------
    # Money-market funding (Borsa İstanbul's repo market), added 2026-11-27.
    # bie_onrepofbap: the weighted-average overnight repo rate, business days
    # since 27-12-2018. The policy rate IS a one-week repo rate, so where the
    # overnight market print sits against the corridor is the day's liquidity
    # signal (35.7-37.9% in the week to 26-11-2026). The group's volume series
    # (TP.IHBAP) is left out: EVDS states no unit for it.
    # ------------------------------------------------------------------
    Series("TP.AOFOBAP", "BIST Overnight Repo Rate (weighted avg)", "rates", evds.FREQ_WORKDAY),

    # ------------------------------------------------------------------
    # Bank Loans Tendency Survey (TCMB, quarterly, bie_bkea), added 2026-11-27.
    # Each series is a net percentage of banks over the past three months, or
    # an expectation for the next three. The survey has 128; these are the
    # headline standards, pricing terms and demand for corporate and consumer
    # lending, the factors most often used to explain them, and banks' own
    # funding conditions. Labels name the question and stay neutral on sign:
    # which direction is positive is stated in TCMB's report table, not in the
    # series metadata, and must be read off it before anything charts these.
    # Latest observation at ingestion: 2026-Q3. Not yet charted.
    # ------------------------------------------------------------------
    # Corporate (SME = Küçük ve Orta Ölçekli İşletmeler)
    Series("TP.BKEA.S001", "BLTS: corporate credit standards, overall (net % of banks)",       "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S002", "BLTS: corporate credit standards, SME (net % of banks)",           "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S003", "BLTS: corporate credit standards, large firms (net % of banks)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S006", "BLTS: corporate credit standards, TL loans (net % of banks)",      "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S007", "BLTS: corporate credit standards, FX loans (net % of banks)",      "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S009", "BLTS: standards driver - access to money & bond market funding",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S010", "BLTS: standards driver - liquidity position",                      "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S011", "BLTS: standards driver - competition from other banks",            "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S015", "BLTS: standards driver - industry or firm outlook",                "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S017", "BLTS: corporate terms - margin on average loans (net % of banks)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S018", "BLTS: corporate terms - margin on riskier loans (net % of banks)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S020", "BLTS: corporate terms - collateral requirement (net % of banks)",  "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S024", "BLTS: corporate loan demand, overall (net % of banks)",            "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S025", "BLTS: corporate loan demand, SME (net % of banks)",                "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S026", "BLTS: corporate loan demand, large firms (net % of banks)",        "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S029", "BLTS: corporate loan demand, TL loans (net % of banks)",           "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S030", "BLTS: corporate loan demand, FX loans (net % of banks)",           "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S032", "BLTS: demand driver - inventory & working capital",                "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S042", "BLTS: corporate standards expected next 3 months, overall",        "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S049", "BLTS: corporate demand expected next 3 months, overall",           "macro", evds.FREQ_QUARTERLY),
    # Consumer
    Series("TP.BKEA.S056", "BLTS: housing credit standards (net % of banks)",                  "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S057", "BLTS: vehicle credit standards (net % of banks)",                  "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S058", "BLTS: other consumer credit standards (net % of banks)",           "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S059", "BLTS: housing standards driver - funding costs & balance sheet",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S063", "BLTS: housing standards driver - housing market expectations",     "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S064", "BLTS: housing terms - margin on average loans (net % of banks)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S065", "BLTS: housing terms - margin on riskier loans (net % of banks)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S067", "BLTS: housing terms - loan-to-collateral ratio (net % of banks)",  "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S076", "BLTS: vehicle terms - margin on average loans (net % of banks)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S077", "BLTS: vehicle terms - margin on riskier loans (net % of banks)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S087", "BLTS: other consumer terms - margin on average loans (net %)",     "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S088", "BLTS: other consumer terms - margin on riskier loans (net %)",     "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S092", "BLTS: housing loan demand (net % of banks)",                      "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S093", "BLTS: vehicle loan demand (net % of banks)",                      "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S094", "BLTS: other consumer loan demand (net % of banks)",                "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S117", "BLTS: housing standards expected next 3 months",                   "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S120", "BLTS: housing demand expected next 3 months",                     "macro", evds.FREQ_QUARTERLY),
    # Banks' own funding conditions
    Series("TP.BKEA.S123", "BLTS: domestic funding conditions, past 3 months (net % of banks)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S124", "BLTS: domestic funding conditions, next 3 months (net % of banks)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S125", "BLTS: external funding conditions, past 3 months (net % of banks)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.BKEA.S126", "BLTS: external funding conditions, next 3 months (net % of banks)", "macro", evds.FREQ_QUARTERLY),
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS evds_series (
    code           TEXT NOT NULL,
    period_date    DATE NOT NULL,
    value          REAL,
    label          TEXT,
    category       TEXT,
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, period_date)
);

CREATE INDEX IF NOT EXISTS idx_evds_category ON evds_series(category);
CREATE INDEX IF NOT EXISTS idx_evds_code_date ON evds_series(code, period_date);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


FREQUENCY_GROUPS: dict[str, frozenset[int]] = {
    "daily": frozenset({evds.FREQ_DAILY, evds.FREQ_WORKDAY}),
    "weekly": frozenset({evds.FREQ_WEEKLY, evds.FREQ_BIWEEKLY}),
    "monthly": frozenset({evds.FREQ_MONTHLY}),
    "quarterly": frozenset({evds.FREQ_QUARTERLY}),
}


def parse_frequency_groups(value: str) -> set[int] | None:
    """Resolve CLI frequency names; ``None`` means every configured series."""
    names = {part.strip().lower() for part in value.split(",") if part.strip()}
    if not names or names == {"all"}:
        return None
    unknown = names - set(FREQUENCY_GROUPS)
    if unknown or "all" in names:
        choices = "all, " + ", ".join(FREQUENCY_GROUPS)
        bad = ", ".join(sorted(unknown or {"all"}))
        raise ValueError(f"unknown EVDS frequency group(s): {bad}; choose {choices}")
    return set().union(*(FREQUENCY_GROUPS[name] for name in names))


def fetch_one(s: Series, start: str = "01-01-2018") -> int:
    """Pull one series via the EVDS client. Returns row count written."""
    end = datetime.now().strftime("%d-%m-%Y")
    df = evds.fetch_series(s.code, start=start, end=end, frequency=s.freq)
    if df is None or df.empty:
        print(f"  [warn] {s.code} ({s.label}): empty response")
        return 0

    # The client returns columns ['date', 'value']
    rows: list[tuple] = []
    for _, r in df.iterrows():
        d = r["date"]
        v = r["value"]
        if d is None or v is None or (isinstance(v, float) and v != v):  # NaN check
            continue
        try:
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            v_float = float(v)
        except (ValueError, TypeError):
            continue
        rows.append((s.code, d_str, v_float, s.label, s.category))

    if not rows:
        return 0
    conn = sqlite3.connect(str(DB))
    try:
        # Write ONLY what changed. EVDS has no incremental endpoint, so every run
        # re-fetches each series' whole history back to 2018 — but `INSERT OR
        # REPLACE` rewrote all of it, and because `downloaded_at` is omitted here
        # it took DEFAULT CURRENT_TIMESTAMP on every row. push_to_d1 windows on
        # that column, so 52,828 of evds_series' 53,521 rows looked "new" every
        # single day and were re-pushed to D1 with byte-identical values —
        # ~17M rows written/month, all of it waste, against a 50M/month
        # allowance (D1 bills rows written, and counts index maintenance too).
        #
        # Comparing (value, label, category) is the whole fix: a row we already
        # hold keeps its old `downloaded_at`, so the push window never sees it.
        # A revision, a rebase or a new observation still writes, because the
        # tuple differs. See docs/OPERATIONS.md → D1 write budget.
        existing = {
            (r[0], r[1]): (r[2], r[3], r[4])
            for r in conn.execute(
                "SELECT code, period_date, value, label, category "
                "FROM evds_series WHERE code = ?", (s.code,)
            )
        }
        changed = [r for r in rows if existing.get((r[0], r[1])) != (r[2], r[3], r[4])]
        if changed:
            conn.executemany(
                "INSERT OR REPLACE INTO evds_series(code, period_date, value, label, category) "
                "VALUES (?, ?, ?, ?, ?)",
                changed,
            )
            conn.commit()
    finally:
        conn.close()
    return len(changed)


def update_all(start: str = "01-01-2018",
               frequencies: set[int] | None = None) -> dict[str, int]:
    """Fetch + upsert configured series in the requested cadence groups.

    Returns per-series counts of rows actually WRITTEN (not fetched) — a settled
    series reports 0 on a normal day, and that is the healthy reading. `-1` is a
    failure. A run that writes 0 across the board means EVDS published nothing
    new, not that the scraper broke; freshness is judged on `MAX(period_date)`,
    see scripts/healthcheck.py."""
    conn = sqlite3.connect(str(DB))
    try:
        init_schema(conn)
    finally:
        conn.close()

    selected = [s for s in SERIES if frequencies is None or s.freq in frequencies]
    counts: dict[str, int] = {}
    for s in selected:
        try:
            n = fetch_one(s, start=start)
            counts[s.code] = n
            print(f"  [ok]  {s.code:24} {s.label:40} → {n} rows")
        except Exception as e:
            counts[s.code] = -1
            print(f"  [err] {s.code:24} {s.label:40} {type(e).__name__}: {e}")
    return counts


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--frequencies",
        default="all",
        help="comma-separated: daily, weekly, monthly, quarterly, or all",
    )
    cli = parser.parse_args()
    try:
        wanted = parse_frequency_groups(cli.frequencies)
    except ValueError as exc:
        parser.error(str(exc))
    counts = update_all(frequencies=wanted)
    total = sum(c for c in counts.values() if c >= 0)
    fails = sum(1 for c in counts.values() if c < 0)
    print(f"\n{len(counts)} series · {total} rows written · {fails} failures")
