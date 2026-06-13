"""BIST scraper — pull Borsa İstanbul prices/dividends + shares and write to D1 tables.

Writes three tables in data/bddk_data.db (see web/migrations/0012_bist.sql):
  * bist_prices    — daily OHLCV for the 12 listed banks + indices (XU100, XBANK)
  * bist_dividends — cash dividend events (banks only)
  * bist_shares    — shares outstanding per bank (for market cap)

Universe is derived at runtime from data/banks/bddk_bank_list.json (the banks
with `listed: true` + a `bist_ticker`) so it stays in lockstep with the audit
roster — never hardcode the tickers.

Designed to run inside scripts/refresh.py (non-critical step). Idempotent via
INSERT OR REPLACE. Default window is the last ~35 days (cheap daily refresh);
`--backfill` pulls ~12 years for the initial load.

Uses the Yahoo chart client at src/scrapers/bist_client.py.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.scrapers import bist_client as bist  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "bddk_data.db"
BANK_LIST = ROOT / "data" / "banks" / "bddk_bank_list.json"
SHARES_SEED = ROOT / "data" / "banks" / "bist_shares.json"

# Market indices to track. Yahoo symbol = "<code>.IS".
INDICES: list[tuple[str, str]] = [
    ("XU100", "BIST 100"),
    ("XBANK", "BIST Banks"),
]


def listed_banks() -> list[tuple[str, str]]:
    """(ticker, friendly_name) for every BIST-listed bank in the registry."""
    data = json.loads(BANK_LIST.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for b in data.get("banks", []):
        if b.get("listed") and b.get("bist_ticker"):
            out.append((b["bist_ticker"], b.get("name_tr", b["bist_ticker"])))
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS bist_prices (
    symbol        TEXT NOT NULL,
    period_date   DATE NOT NULL,
    open_price    REAL, high_price REAL, low_price REAL, close_price REAL,
    volume        REAL,
    kind          TEXT,
    label         TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, period_date)
);
CREATE INDEX IF NOT EXISTS idx_bist_prices_symbol ON bist_prices(symbol, period_date);
CREATE INDEX IF NOT EXISTS idx_bist_prices_kind   ON bist_prices(kind, period_date);

CREATE TABLE IF NOT EXISTS bist_dividends (
    symbol        TEXT NOT NULL,
    ex_date       DATE NOT NULL,
    amount        REAL,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS bist_shares (
    symbol             TEXT PRIMARY KEY,
    shares_outstanding REAL,
    nominal            REAL,
    as_of              DATE,
    source             TEXT,
    downloaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _write_prices(conn: sqlite3.Connection, symbol: str, kind: str, label: str,
                  df, dividends: list[dict]) -> int:
    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        rows.append((
            symbol, d_str,
            _f(r.get("open")), _f(r.get("high")), _f(r.get("low")), _f(r.get("close")),
            _f(r.get("volume")), kind, label,
        ))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO bist_prices"
            "(symbol, period_date, open_price, high_price, low_price, close_price, volume, kind, label) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    if dividends and kind == "bank":
        conn.executemany(
            "INSERT OR REPLACE INTO bist_dividends(symbol, ex_date, amount) VALUES (?,?,?)",
            [(symbol, d["ex_date"], float(d["amount"])) for d in dividends],
        )
    conn.commit()
    return len(rows)


def _f(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


def update_shares(conn: sqlite3.Connection, tickers: list[str]) -> int:
    """Upsert shares outstanding: committed seed, overlaid with a best-effort
    live Yahoo refresh so capital actions self-heal without breaking the run."""
    seed = json.loads(SHARES_SEED.read_text(encoding="utf-8"))
    shares: dict[str, float] = {k: float(v) for k, v in seed.get("shares", {}).items()}
    as_of = seed.get("as_of")
    source = seed.get("source", "seed")

    live = bist.fetch_shares(tickers)
    for t, n in live.items():
        if n and n > 0:
            shares[t] = n
    if live:
        as_of = datetime.now().strftime("%Y-%m-%d")
        source = "yahoo:quoteSummary (live)"

    rows = [(t, n, 1.0, as_of, source) for t, n in shares.items()]
    conn.executemany(
        "INSERT OR REPLACE INTO bist_shares(symbol, shares_outstanding, nominal, as_of, source) "
        "VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"  [ok]  shares: {len(rows)} banks ({len(live)} refreshed live)")
    return len(rows)


def update_all(backfill: bool = False) -> dict[str, int]:
    end = datetime.now()
    start = end - timedelta(days=365 * 12 if backfill else 35)
    s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    print(f"BIST window: {s} → {e} ({'backfill' if backfill else 'incremental'})")

    conn = sqlite3.connect(str(DB))
    try:
        init_schema(conn)
        counts: dict[str, int] = {}

        banks = listed_banks()
        for ticker, name in banks:
            df, divs = bist.fetch_chart(f"{ticker}.IS", s, e)
            n = _write_prices(conn, ticker, "bank", name, df, divs) if not df.empty else 0
            counts[ticker] = n
            print(f"  [{'ok ' if n else 'warn'}] {ticker:7} {name[:34]:34} → {n} bars, {len(divs)} divs")

        for code, name in INDICES:
            df, _ = bist.fetch_chart(f"{code}.IS", s, e)
            n = _write_prices(conn, code, "index", name, df, []) if not df.empty else 0
            counts[code] = n
            print(f"  [{'ok ' if n else 'warn'}] {code:7} {name:34} → {n} bars")

        update_shares(conn, [t for t, _ in banks])
    finally:
        conn.close()
    return counts


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true",
                    help="pull ~12 years of history (one-time initial load)")
    args = ap.parse_args()
    counts = update_all(backfill=args.backfill)
    total = sum(counts.values())
    empties = [k for k, v in counts.items() if v == 0]
    print(f"\n{len(counts)} symbols · {total} bars written"
          + (f" · empty: {', '.join(empties)}" if empties else ""))
