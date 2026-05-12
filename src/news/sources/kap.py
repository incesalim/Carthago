"""KAP (Kamuyu Aydınlatma Platformu) disclosure scraper.

Endpoint: POST https://www.kap.org.tr/tr/api/disclosure/members/byCriteria
Response: bare JSON list of disclosures, ~70/day, filterable by date range.

Filter: client-side on `stockCodes` against the BIST-listed bank tickers
in `data/banks/bddk_bank_list.json` so non-bank disclosures are dropped.

Detail URL pattern: https://www.kap.org.tr/tr/Bildirim/{disclosureIndex}
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.news.loader import NewsItem

REPO_ROOT = Path(__file__).resolve().parents[3]
BIST_BANKS_FILE = REPO_ROOT / "data" / "banks" / "bddk_bank_list.json"

ENDPOINT = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
DETAIL_URL = "https://www.kap.org.tr/tr/Bildirim/{idx}"

# Headers needed to pass KAP's WAF (User-Agent + Origin + Referer must all
# be present and look like a real browser). Discovered via the kap-client
# package; documented in src/news/sources/kap.py docstring.
HEADERS = {
    "Origin": "https://www.kap.org.tr",
    "Referer": "https://www.kap.org.tr/tr/bildirim-sorgu",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
}


def _bist_ticker_set() -> set[str]:
    """Load BIST-listed bank tickers. Used to filter KAP rows to banking
    sector only — KAP returns disclosures across all BIST companies."""
    tickers: set[str] = set()
    if BIST_BANKS_FILE.exists():
        data = json.loads(BIST_BANKS_FILE.read_text(encoding="utf-8"))
        # Schema: {"banks": [{"bist_ticker": "AKBNK", "listed": True, ...}, ...]}
        for b in data.get("banks", []):
            if not b.get("listed"):
                continue
            t = b.get("bist_ticker") or b.get("ticker")
            if t:
                tickers.add(t.upper())
    # Hard-coded fallback so the pipeline still works if the JSON disappears.
    tickers.update({
        "AKBNK", "ALBRK", "GARAN", "HALKB", "ICBCT", "ISCTR", "QNBFB",
        "SKBNK", "TSKB", "VAKBN", "YKBNK",
    })
    return tickers


def _to_iso(raw: str | None) -> str:
    """KAP returns 'DD.MM.YYYY HH:MM:SS' (TR local time, no offset).
    Convert to ISO-8601 UTC; assume Europe/Istanbul (UTC+3, no DST since 2016)."""
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.strptime(raw, "%d.%m.%Y %H:%M:%S")
        # Treat as Europe/Istanbul (UTC+3, no DST)
        dt_utc = dt - timedelta(hours=3)
        return dt_utc.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return raw


def fetch(
    days_back: int = 30,
    request_timeout: int = 45,
    max_retries: int = 3,
) -> list[NewsItem]:
    """Fetch KAP disclosures for BIST-listed banks in the trailing window."""
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=days_back)
    body = {
        "fromDate": from_date.isoformat(),
        "toDate": to_date.isoformat(),
        "memberType": "", "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
        "disclosureClass": "", "subjectList": [], "isLate": "",
        "mainSector": "", "sector": "", "subSector": "", "marketOid": "",
        "index": "", "bdkReview": "", "bdkMemberOidList": [], "year": "",
        "term": "", "ruleType": "", "period": "",
        "fromSrc": False, "srcCategory": "", "disclosureIndexList": [],
    }

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(ENDPOINT, headers=HEADERS, json=body, timeout=request_timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            r.raise_for_status()
            rows = r.json()
            break
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"KAP fetch failed after {max_retries} retries: {last_err}")

    bist_banks = _bist_ticker_set()
    items: list[NewsItem] = []
    for row in rows:
        codes_raw = (row.get("stockCodes") or "").replace(" ", "")
        if not codes_raw:
            continue
        # A disclosure may list multiple tickers (e.g. "YKB,YKBNK"); match any.
        codes = [c for c in codes_raw.split(",") if c]
        bank_match = next((c for c in codes if c in bist_banks), None)
        if not bank_match:
            continue
        disclosure_idx = row.get("disclosureIndex")
        if disclosure_idx is None:
            continue
        items.append(NewsItem(
            source="kap",
            external_id=str(disclosure_idx),
            published_at=_to_iso(row.get("publishDate")),
            ticker=bank_match,
            category=row.get("disclosureCategory") or row.get("disclosureClass"),
            title=row.get("subject") or row.get("kapTitle") or "(no subject)",
            summary=row.get("summary"),
            url=DETAIL_URL.format(idx=disclosure_idx),
            language="tr",
            raw_json=json.dumps(row, ensure_ascii=False, default=str),
        ))
    return items
