"""Thin rate-limited client for the tefas.gov.tr JSON fund API.

TEFAS exposes two POST endpoints behind the fon-verileri SPA (the HTML pages
sit behind an F5/TSPD JS challenge, but the API itself answers plain JSON
requests with browser-ish headers):

- ``fonGnlBlgSiraliGetir`` — per fund per day: NAV price, AUM
  (``portfoyBuyukluk``, TL), investor count, units outstanding.
- ``dagilimSiraliGetirT`` — per fund per day portfolio allocation across
  ~55 sparse percentage fields (see ``normalize.ASSET_ROLLUP``); plus a
  ``bilFiyat`` TL value we ignore.

Server-side constraints (probed 2026-06-11): ~6 requests/minute (429 beyond,
resets in ~65 s), max 30 calendar days per request, ``basSira``/``bitSira``
row-index pagination (one YAT day ≈ 2,000 rows so multi-week windows can
exceed a single page). Be polite: this lane runs once daily plus a one-time
backfill — never parallelize requests.
"""
from __future__ import annotations

import time
from datetime import date

import requests

BASE = "https://www.tefas.gov.tr/api/funds"
INFO_ENDPOINT = "fonGnlBlgSiraliGetir"
ALLOCATION_ENDPOINT = "dagilimSiraliGetirT"

FUND_TYPES = ["YAT", "EMK", "BYF", "GYF", "GSYF"]

PAGE_SIZE = 100_000
MAX_WINDOW_DAYS = 29        # API rejects ranges over ~30 days
MIN_INTERVAL_S = 11.0       # ~5.5 req/min, under the ~6/min server limit
_RETRY_429_SLEEP_S = 70.0   # observed reset is ~65 s
_MAX_RETRIES = 3

_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/tr/fon-verileri",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

_last_request_at = 0.0


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def _pace() -> None:
    global _last_request_at
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _post(session: requests.Session, endpoint: str, payload: dict) -> dict:
    backoff = 5.0
    for attempt in range(_MAX_RETRIES + 1):
        _pace()
        try:
            resp = session.post(f"{BASE}/{endpoint}", json=payload, timeout=60)
        except requests.RequestException:
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code == 429:
            if attempt == _MAX_RETRIES:
                resp.raise_for_status()
            time.sleep(_RETRY_429_SLEEP_S)
            continue
        if resp.status_code >= 500:
            if attempt == _MAX_RETRIES:
                resp.raise_for_status()
            time.sleep(backoff)
            backoff *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")


def fetch_window(
    session: requests.Session,
    endpoint: str,
    fon_tipi: str,
    start: date,
    end: date,
) -> list[dict]:
    """All rows for one fund type over ``start..end`` (inclusive), paginating
    through ``basSira``/``bitSira``. Out-of-range pages come back with
    ``resultList: null`` and an 'Index out of bounds' errorMessage — treated
    as end-of-data, while any other errorMessage raises."""
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError(f"window {start}..{end} exceeds {MAX_WINDOW_DAYS} days")
    rows: list[dict] = []
    bas = 1
    while True:
        payload = {
            "fonTipi": fon_tipi,
            "fonKodu": None,
            "basTarih": start.strftime("%Y%m%d"),
            "bitTarih": end.strftime("%Y%m%d"),
            "basSira": bas,
            "bitSira": bas + PAGE_SIZE - 1,
            "dil": "TR",
        }
        data = _post(session, endpoint, payload)
        page = data.get("resultList")
        if page is None:
            msg = data.get("errorMessage") or ""
            if bas > 1 and "out of bounds" in msg.lower():
                break  # walked past the last row
            if msg and "out of bounds" not in msg.lower():
                raise RuntimeError(f"{endpoint} {fon_tipi} {start}..{end}: {msg}")
            break  # empty window (holiday / not yet published)
        rows.extend(page)
        total = data.get("toplamSayi") or 0
        if len(page) < PAGE_SIZE and bas + len(page) - 1 >= total:
            break
        if not page:
            break
        bas += len(page)
    return rows


def fetch_info(session, fon_tipi: str, start: date, end: date) -> list[dict]:
    return fetch_window(session, INFO_ENDPOINT, fon_tipi, start, end)


def fetch_allocation(session, fon_tipi: str, start: date, end: date) -> list[dict]:
    return fetch_window(session, ALLOCATION_ENDPOINT, fon_tipi, start, end)
