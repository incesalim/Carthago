"""EVDS scraper — pull selected TCMB series and write to evds_series table.

Designed to run inside scripts/refresh.py weekly.
Idempotent via INSERT OR REPLACE on (code, period_date).

Reuses the existing EVDS client at src/dashboard/evds.py (hosted in the
legacy Dash module since that's where it was first written).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# Reuse the existing client
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.dashboard import evds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "bddk_data.db"


class Series(NamedTuple):
    code: str
    label: str
    category: str  # rates / fx / inflation / cbrt
    freq: int      # 1=daily, 3=weekly, 5=monthly


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
