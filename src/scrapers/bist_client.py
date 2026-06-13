"""BIST client — Borsa İstanbul equity data via the Yahoo Finance chart API.

Yahoo's public chart endpoint (`query1.finance.yahoo.com/v8/finance/chart/{SYM}`)
returns daily OHLCV + dividend events for a symbol, keyless and headless-friendly
(works in CI). Turkish symbols are `<TICKER>.IS` (e.g. GARAN.IS) and indices use
the index code (e.g. XU100.IS, XBANK.IS).

Shares outstanding are NOT in the chart payload, so `fetch_shares` uses the
`quoteSummary` endpoint (cookie + crumb handshake, as yfinance does). That path
is more brittle than the chart API, so callers treat it as best-effort and fall
back to the committed data/banks/bist_shares.json seed.

Mirrors src/scrapers/evds_client.py: same 3-tier (in-proc → disk → HTTP) cache
idiom, gentle pacing, and a CACHE_DISABLED kill switch.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

# ---------------------------------------------------------------------------
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
COOKIE_URL = "https://fc.yahoo.com/"
QUOTESUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"

# A browser UA — the chart API rejects (429/empty) some library UAs.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bddk-analysis/1.0",
    "Accept": "application/json",
}

# Disk cache — survives process restarts; mirrors data/evds_cache/.
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bist_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_CACHE: dict[tuple, pd.DataFrame] = {}
_CACHE_ENABLED = os.getenv("BIST_CACHE_DISABLED", "0") != "1"

# Shared session so the cookie/crumb persists across quoteSummary calls.
_SESSION: Optional[requests.Session] = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _SESSION = s
    return _SESSION


# ---------------------------------------------------------------------------
def _cache_path(key: tuple) -> Path:
    h = hashlib.md5(repr(key).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def _load_cache_disk(key: tuple) -> Optional[tuple[pd.DataFrame, list[dict]]]:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        df = pd.DataFrame(blob.get("prices", []))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df, blob.get("dividends", [])
    except Exception as ex:
        print(f"[bist] cache read failed ({p.name}): {ex}")
        return None


def _save_cache_disk(key: tuple, df: pd.DataFrame, dividends: list[dict]) -> None:
    try:
        out = df.copy()
        if "date" in out.columns and not out.empty:
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        _cache_path(key).write_text(
            json.dumps({"prices": out.to_dict(orient="records"), "dividends": dividends}),
            encoding="utf-8",
        )
    except Exception as ex:
        print(f"[bist] cache write failed: {ex}")


# ---------------------------------------------------------------------------
def fetch_chart(
    symbol: str,
    start: str,                 # 'YYYY-MM-DD'
    end: str,                   # 'YYYY-MM-DD'
    cache: bool = True,
    max_retries: int = 4,
) -> tuple[pd.DataFrame, list[dict]]:
    """Fetch daily OHLCV + dividend events for one Yahoo symbol.

    Returns (prices_df, dividends). prices_df columns:
    [date, open, high, low, close, volume]. dividends: [{ex_date, amount}].
    A delisted / unknown symbol returns (empty df, []) rather than raising —
    callers (the scraper) tolerate per-symbol gaps.
    """
    key = (symbol, start, end)
    if cache and _CACHE_ENABLED:
        if key in _CACHE:
            df = _CACHE[key]
            return df.copy(), _CACHE.get(("div", symbol, start, end), [])
        disk = _load_cache_disk(key)
        if disk is not None:
            df, divs = disk
            _CACHE[key] = df
            _CACHE[("div", symbol, start, end)] = divs
            return df.copy(), divs

    p1 = int(pd.Timestamp(start).timestamp())
    p2 = int(pd.Timestamp(end).timestamp()) + 86400  # inclusive of end day
    url = CHART_URL.format(symbol=symbol)
    params = {
        "period1": p1,
        "period2": p2,
        "interval": "1d",
        "events": "div",
    }

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            r = _session().get(url, params=params, timeout=25)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            df, divs = _parse_chart(r.json())
            if cache and _CACHE_ENABLED:
                _CACHE[key] = df
                _CACHE[("div", symbol, start, end)] = divs
                _save_cache_disk(key, df, divs)
            return df.copy(), divs
        except requests.HTTPError as ex:
            last_err = ex
            time.sleep(2 ** attempt)  # 1, 2, 4, 8s backoff
        except Exception as ex:
            last_err = ex
            break

    print(f"[bist] WARN {symbol}: {type(last_err).__name__}: {last_err}")
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]), []


def _parse_chart(payload: dict) -> tuple[pd.DataFrame, list[dict]]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]), []
    results = chart.get("result") or []
    if not results:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]), []
    res = results[0]
    ts = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, t in enumerate(ts):
        rows.append({
            "date": pd.to_datetime(t, unit="s").normalize(),
            "open": _g(quote.get("open"), i),
            "high": _g(quote.get("high"), i),
            "low": _g(quote.get("low"), i),
            "close": _g(quote.get("close"), i),
            "volume": _g(quote.get("volume"), i),
        })
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    # Drop bars with no close (market holidays / partial rows Yahoo pads with null).
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    divs = []
    events = (res.get("events") or {}).get("dividends") or {}
    for ev in events.values():
        amt = ev.get("amount")
        d = ev.get("date")
        if amt is None or d is None:
            continue
        divs.append({
            "ex_date": pd.to_datetime(d, unit="s").strftime("%Y-%m-%d"),
            "amount": float(amt),
        })
    divs.sort(key=lambda x: x["ex_date"])
    return df, divs


def _g(seq, i):
    if not seq or i >= len(seq):
        return None
    return seq[i]


# ---------------------------------------------------------------------------
def fetch_shares(tickers: list[str]) -> dict[str, float]:
    """Best-effort shares-outstanding lookup via Yahoo quoteSummary.

    Needs the cookie + crumb handshake. Returns {ticker: shares} for whatever
    resolves; on any failure (crumb flow changes, thin-float symbols like QNBFB
    that Yahoo returns empty) the entry is simply omitted and the caller falls
    back to the committed seed. Never raises.
    """
    out: dict[str, float] = {}
    try:
        s = _session()
        s.get(COOKIE_URL, timeout=20)
        crumb = s.get(CRUMB_URL, timeout=20).text.strip()
        if not crumb or "<" in crumb:
            return out
    except Exception as ex:
        print(f"[bist] shares: crumb handshake failed: {ex}")
        return out

    for t in tickers:
        try:
            url = QUOTESUMMARY_URL.format(symbol=f"{t}.IS")
            r = s.get(url, params={"modules": "defaultKeyStatistics", "crumb": crumb}, timeout=20)
            if r.status_code != 200:
                continue
            res = (r.json().get("quoteSummary") or {}).get("result") or []
            if not res:
                continue
            so = (res[0].get("defaultKeyStatistics") or {}).get("sharesOutstanding") or {}
            raw = so.get("raw")
            if raw:
                out[t] = float(raw)
        except Exception:
            continue
        time.sleep(0.2)
    return out
