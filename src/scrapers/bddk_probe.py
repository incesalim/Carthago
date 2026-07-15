"""Lightweight BDDK publication probe — "has month M been published yet?".

BDDK publishes no forward calendar, so the only authoritative answer to "is the
data out?" is BDDK itself. This is the one-request probe the incremental
extractor (scripts/update_monthly.py) uses to decide what to scrape — factored
out here so the daily health check can ask the same question without pulling in
the full BDDKAPIScraper.

Needs only `requests` + the cert helper (BDDK omits an intermediate cert; see
src/scrapers/_http.bddk_verify).
"""
from __future__ import annotations

import requests

from src.scrapers._http import bddk_verify

MONTHLY_PROBE_URL = "https://www.bddk.org.tr/BultenAylik/tr/Home/BasitRaporGetir"
_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0",
}


def monthly_is_published(year: int, month: int, timeout: int = 20) -> bool:
    """True iff BDDK returns rows for (year, month) — i.e. the month is out.

    Raises on a network / HTTP / parse error, so the caller can distinguish
    "not published" from "couldn't check".
    """
    payload = {
        "tabloNo": "1", "yil": str(year), "ay": str(month),
        "paraBirimi": "TL", "taraf[0]": "10001",
    }
    r = requests.post(
        MONTHLY_PROBE_URL, headers=_HEADERS, data=payload,
        timeout=timeout, verify=bddk_verify(),
    )
    r.raise_for_status()
    rows = r.json().get("Json", {}).get("data", {}).get("rows", [])
    return bool(rows)
