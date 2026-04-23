"""EVDS client — TCMB's Electronic Data Delivery System (v3).

Post-migration host is `evds3.tcmb.gov.tr/igmevdsms-dis`. The API key is
sent as a header named `key` (not a URL parameter). Responses return
`{"items": [{"Tarih": "DD-MM-YYYY", "TP_APIFON4": "39.50", "UNIXTIME": {...}}]}`.

Reference: https://evds3.tcmb.gov.tr/
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
API_KEY = os.getenv("EVDS_API_KEY")
HEADERS = {
    "key": API_KEY or "",
    "User-Agent": "bddk-analysis/1.0",
    "Accept": "application/json",
}

# Frequency codes (per TCMB EVDS docs)
FREQ_DAILY = 1
FREQ_WORKDAY = 2
FREQ_WEEKLY = 3
FREQ_BIWEEKLY = 4
FREQ_MONTHLY = 5
FREQ_QUARTERLY = 6
FREQ_SEMIANNUAL = 7
FREQ_ANNUAL = 8

# Simple in-process cache: {(code, start, end, freq) -> df}
_CACHE: dict[tuple, pd.DataFrame] = {}


def fetch_series(
    code: str,
    start: str,                   # "YYYY-MM-DD" or "DD-MM-YYYY"
    end: str,
    frequency: Optional[int] = None,
    aggregation: str = "avg",     # avg / last / min / max / first
    cache: bool = True,
) -> pd.DataFrame:
    """Fetch a single series. Returns DataFrame with columns [date, value].

    EVDS caps each response at 1,000 rows. For longer windows this function
    auto-chunks the request (3-year sub-windows) and stitches the pieces.
    """
    if not API_KEY:
        raise RuntimeError("EVDS_API_KEY not set in .env")

    s = _to_evds_date(start)
    e = _to_evds_date(end)
    key = (code, s, e, frequency, aggregation)
    if cache and key in _CACHE:
        return _CACHE[key].copy()

    # If window is > 3y of workdays, fetch in 3-year chunks.
    start_dt = pd.to_datetime(s, format="%d-%m-%Y")
    end_dt = pd.to_datetime(e, format="%d-%m-%Y")
    span_days = (end_dt - start_dt).days

    if span_days > 3 * 365:
        chunks = []
        cur = start_dt
        while cur < end_dt:
            chunk_end = min(cur + pd.Timedelta(days=3 * 365), end_dt)
            chunks.append(_fetch_one(
                code,
                cur.strftime("%d-%m-%Y"),
                chunk_end.strftime("%d-%m-%Y"),
                frequency, aggregation,
            ))
            cur = chunk_end + pd.Timedelta(days=1)
        if chunks:
            df = pd.concat(chunks, ignore_index=True).drop_duplicates("date").sort_values("date").reset_index(drop=True)
        else:
            df = pd.DataFrame(columns=["date", "value"])
    else:
        df = _fetch_one(code, s, e, frequency, aggregation)

    if cache:
        _CACHE[key] = df.copy()
    return df


def _fetch_one(code: str, s: str, e: str,
               frequency: Optional[int], aggregation: str) -> pd.DataFrame:
    url = (
        f"{BASE_URL}/series={code}"
        f"&startDate={s}&endDate={e}"
        f"&type=json"
    )
    if frequency is not None:
        url += f"&frequency={frequency}"
    if aggregation:
        url += f"&aggregationTypes={aggregation}"

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", []) if isinstance(data, dict) else []

    if not items:
        return pd.DataFrame(columns=["date", "value"])
    value_col = _find_value_col(items[0], code)
    df = pd.DataFrame(items)[["Tarih", value_col]].rename(
        columns={"Tarih": "date", value_col: "value"}
    )
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def fetch_many(
    codes: dict[str, str],        # {label: code}
    start: str,
    end: str,
    frequency: Optional[int] = None,
    aggregation: str = "avg",
) -> pd.DataFrame:
    """Fetch multiple series, return long-format df with columns [date, label, value]."""
    frames = []
    for label, code in codes.items():
        try:
            sub = fetch_series(code, start, end, frequency, aggregation)
            if sub.empty:
                continue
            sub = sub.copy()
            sub["label"] = label
            sub["code"] = code
            frames.append(sub)
        except Exception as ex:
            print(f"[evds] WARN {code} ({label}): {ex}")
            continue
        # Gentle pacing so TCMB doesn't rate-limit us.
        time.sleep(0.15)
    if not frames:
        return pd.DataFrame(columns=["date", "label", "value", "code"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
def _to_evds_date(v: str) -> str:
    """Accept 'YYYY-MM-DD' or 'DD-MM-YYYY', always return 'DD-MM-YYYY'."""
    if len(v) == 10 and v[2] == "-":
        return v
    d = pd.to_datetime(v)
    return d.strftime("%d-%m-%Y")


def _find_value_col(item: dict, code: str) -> str:
    """EVDS names value columns like 'TP_APIFON4'. Derive from code when possible."""
    cand = code.replace(".", "_")
    if cand in item:
        return cand
    for k in item:
        if k not in ("Tarih", "UNIXTIME", "YEARWEEK"):
            return k
    raise ValueError(f"No value column found in item: {item}")
