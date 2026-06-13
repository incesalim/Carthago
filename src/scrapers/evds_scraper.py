"""EVDS scraper — pull selected TCMB series and write to evds_series table.

Designed to run inside scripts/refresh.py weekly.
Idempotent via INSERT OR REPLACE on (code, period_date).

Uses the EVDS HTTP client at src/scrapers/evds_client.py.
"""
from __future__ import annotations

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

    # Inflation
    Series("TP.FG.J0",          "CPI (2003=100)",                "inflation", evds.FREQ_MONTHLY),
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

    # Gold tons (CBRT books)
    Series("TP.BL0021", "Total Gold Reserves (grams)",         "cbrt", evds.FREQ_WEEKLY),
    Series("TP.BL0891", "Banks' Gold at CBRT (grams)",         "cbrt", evds.FREQ_WEEKLY),

    # Residents' FC deposits (dollarization)
    Series("TP.HPBITABLO4.4", "Households USD Deposits (USD m)",         "fx", evds.FREQ_MONTHLY),
    Series("TP.HPBITABLO4.5", "Households EUR Deposits (USD eq, USD m)", "fx", evds.FREQ_MONTHLY),
    Series("TP.HPBITABLO4.7", "Households Precious Metals (USD m)",      "fx", evds.FREQ_MONTHLY),

    # Real effective exchange rate (real appreciation backdrop)
    Series("TP.RK.T1.Y", "REER (CPI based, 2003=100)", "fx", evds.FREQ_MONTHLY),

    # Deposit rates by maturity (≤1m through >12m)
    Series("TP.TRY.MT01", "Deposit rate ≤1m",   "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT02", "Deposit rate 1-3m",  "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT03", "Deposit rate 3-6m",  "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT04", "Deposit rate 6-12m", "rates", evds.FREQ_WEEKLY),
    Series("TP.TRY.MT05", "Deposit rate >12m",  "rates", evds.FREQ_WEEKLY),

    # Lending rate refinements
    Series("TP.KTF18",    "Commercial Loan (ex cards & OD)", "rates", evds.FREQ_WEEKLY),
    Series("TP.KTFTUK01", "Consumer Loan (incl. overdraft)", "rates", evds.FREQ_WEEKLY),

    # ------------------------------------------------------------------
    # Macro block — feeds the /economy tab (BBVA Türkiye Economic Outlook
    # adaptation). TP.FG.J0 (CPI 2003=100) died at the Jan-2026 TUIK
    # rebase; TP.TUKFIY2025.GENEL is the replacement and is backcast to
    # well before 2018, so it carries the full history alone.
    # ------------------------------------------------------------------
    Series("TP.TUKFIY2025.GENEL", "CPI (2025=100)", "inflation", evds.FREQ_MONTHLY),

    # National accounts (TURKSTAT, quarterly)
    Series("TP.GSYIH26.HY.ZH", "GDP (chain-linked volume index)",    "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH26.HY.CF", "GDP (current prices, TL thousand)",  "macro", evds.FREQ_QUARTERLY),

    # ------------------------------------------------------------------
    # National-accounts detail — feeds the /economy/economic-growth page
    # (Albaraka "Ekonomik Büyüme" quarterly report). TUIK 2021-ref-year
    # chain-linked volume indices (raw/unadjusted); the page computes y/y
    # from the level (v[t]/v[t-4]-1) and the Şekil 2 growth-contributions.
    # Codes verified against the report's y/y table. NOTE: EVDS carries only
    # the top-level expenditure aggregates (not durable/construction detail)
    # and only the unadjusted production index (the calendar-adjusted variant
    # TUIK headlines on a few sub-sectors is Excel-only — see METRICS.md §14).
    # ------------------------------------------------------------------
    # Expenditure method (bie_gsyhhyhe)
    Series("TP.GSYIH20.HY.ZH", "Household Consumption (chain vol.)",         "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH21.HY.ZH", "Government Consumption (chain vol.)",        "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH22.HY.ZH", "Gross Fixed Capital Formation (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH24.HY.ZH", "Exports of Goods & Services (chain vol.)",   "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH25.HY.ZH", "Imports of Goods & Services (chain vol.)",   "macro", evds.FREQ_QUARTERLY),
    # Production method / kind of economic activity (bie_gsyhifkhe)
    Series("TP.GSYIH01.IFK.ZH", "GVA: Agriculture (chain vol.)",                 "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH02.IFK.ZH", "GVA: Industry (chain vol.)",                    "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH03.IFK.ZH", "GVA: Manufacturing (chain vol.)",               "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH04.IFK.ZH", "GVA: Construction (chain vol.)",                "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH05.IFK.ZH", "GVA: Services (chain vol.)",                    "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH06.IFK.ZH", "GVA: Information & Communication (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH07.IFK.ZH", "GVA: Finance & Insurance (chain vol.)",         "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH08.IFK.ZH", "GVA: Real Estate (chain vol.)",                 "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH09.IFK.ZH", "GVA: Professional/Admin/Support (chain vol.)",  "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH10.IFK.ZH", "GVA: Public Admin/Education/Health (chain vol.)", "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH11.IFK.ZH", "GVA: Other Services (chain vol.)",              "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH12.IFK.ZH", "GVA: Sectoral Total (chain vol.)",              "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH13.IFK.ZH", "Taxes less Subsidies (chain vol.)",             "macro", evds.FREQ_QUARTERLY),
    Series("TP.GSYIH26.IFK.ZH", "GDP at purchaser prices (chain vol., prod.)",   "macro", evds.FREQ_QUARTERLY),

    # Industrial production (TURKSTAT, SA + calendar adjusted, 2021=100)
    Series("TP.TSANAYMT2021.Y1", "Industrial Production (SA, 2021=100)", "macro", evds.FREQ_MONTHLY),

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
        conn.executemany(
            "INSERT OR REPLACE INTO evds_series(code, period_date, value, label, category) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def update_all(start: str = "01-01-2018") -> dict[str, int]:
    """Fetch + upsert every configured series. Returns per-series row counts."""
    conn = sqlite3.connect(str(DB))
    try:
        init_schema(conn)
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for s in SERIES:
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
    counts = update_all()
    total = sum(c for c in counts.values() if c >= 0)
    fails = sum(1 for c in counts.values() if c < 0)
    print(f"\n{len(counts)} series · {total} rows written · {fails} failures")
