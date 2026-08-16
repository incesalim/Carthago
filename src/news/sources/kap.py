"""KAP (Kamuyu Aydınlatma Platformu) disclosure scraper.

Endpoint: POST https://www.kap.org.tr/tr/api/disclosure/members/byCriteria
Response: bare JSON list of disclosures, ~70/day, filterable by date range.

Filter, in two passes:

1. `stockCodes` against the BIST-listed bank tickers in
   `data/banks/bddk_bank_list.json` — 12 banks, every disclosure kind;
2. for a **financial report only**, the KAP member's own title against the
   audit fleet — which adds the 23 banks that file on KAP as debt issuers and
   carry no ticker at all.

Pass 2 exists because pass 1 alone made a bank's *publication* invisible. KAP
drops `stockCodes` for an unlisted member, and the row was skipped before
anything looked at it: on 2026-08-16, 35 of our 38 banks had filed 2026Q2 on
KAP and this lane could see 4 of the 13 the audit pipeline was missing. It is
narrowed to financial reports on purpose — an unlisted member's bond notices
are not bank news anyone reads, and `bank_earnings` only needs the filing.

Detail URL pattern: https://www.kap.org.tr/tr/Bildirim/{disclosureIndex}
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.news.loader import NewsItem

REPO_ROOT = Path(__file__).resolve().parents[3]
BIST_BANKS_FILE = REPO_ROOT / "data" / "banks" / "bddk_bank_list.json"
KAP_MAP_FILE = REPO_ROOT / "data" / "banks" / "kap_company_map.json"

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


# --- pass 2: KAP members with no ticker --------------------------------------

# Fleet banks the ownership map does not carry — the 2026-07 digital and
# participation entrants. Titles exactly as KAP prints them. Takasbank and
# Colendi are deliberately absent: neither files a financial report on KAP.
_EXTRA_MEMBER_TITLES = {
    "DÜNYA KATILIM BANKASI A.Ş.": "DUNYAK",
    "HAYAT FİNANS KATILIM BANKASI A.Ş.": "HAYATK",
    "T.O.M. KATILIM BANKASI A.Ş.": "TOMK",
    "ENPARA BANK A.Ş.": "ENPARA",
    "ZİRAAT DİNAMİK BANKA A.Ş.": "ZIRAATD",
}

# Only these subjects are matched by title. A financial report is the one
# disclosure whose absence we need to detect; everything else from an unlisted
# member stays out of the news lane.
_FINANCIAL_REPORT_RX = re.compile(r"finansal\s+rapor|financial\s+report", re.I)


def _normalise_title(s: str) -> str:
    """Fold a KAP member title to a comparable key.

    Turkish-aware: `.upper()` maps ``i``→``I`` but KAP writes ``İ``, so the
    dotted forms are folded explicitly before the punctuation is stripped.
    ``T.O.M. KATILIM`` and ``TOM KATILIM`` must land on the same key.
    """
    s = (s or "").replace("İ", "I").replace("ı", "i")
    s = s.upper().replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U")
    s = s.replace("Ö", "O").replace("Ç", "C").replace("Â", "A")
    # Punctuation is DELETED, not spaced out: KAP writes both "T.O.M. KATILIM"
    # and "TOM KATILIM", and spacing the dots would keep those apart. Both
    # sides of every comparison come through here, so the fold only has to be
    # consistent, not reversible.
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", "", s)).strip()


def _member_title_map() -> dict[str, str]:
    """Normalised KAP member title → our bank ticker, for the whole fleet."""
    out: dict[str, str] = {}
    if KAP_MAP_FILE.exists():
        data = json.loads(KAP_MAP_FILE.read_text(encoding="utf-8"))
        for ticker, entry in data.get("banks", {}).items():
            title = entry.get("kap_title")
            if title:
                out[_normalise_title(title)] = ticker.upper()
    for title, ticker in _EXTRA_MEMBER_TITLES.items():
        out[_normalise_title(title)] = ticker
    return out


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


# KAP answers a byCriteria query with at most this many rows, silently — no
# flag, no continuation token, the list simply stops. In filing season the
# platform publishes ~300 disclosures a day, so a 30-day window asks for ~8,400
# and is served ~a week of them. Measured 2026-08-16: 2026-07-20→08-16 returned
# exactly 2000 rows against 8,379 counted a day at a time.
#
# Requesting a range wider than the cap is therefore a silent truncation, and it
# is invisible in the daily lane because the days it drops are the OLD ones —
# which the previous day's run already stored. It only bites when a query wants
# real history: this lane's own backfill, and the filing-season check that asks
# "who has filed this quarter".
_ROW_CAP = 2000
# ~300/day observed at the peak; 3 days keeps a chunk at ~a third of the cap.
_CHUNK_DAYS = 3


def _post_window(from_date, to_date, request_timeout: int, max_retries: int) -> list[dict]:
    """One byCriteria call for a closed date range, with KAP's retry etiquette."""
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
            r = requests.post(ENDPOINT, headers=HEADERS, json=body,
                              timeout=request_timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"KAP fetch failed after {max_retries} retries: {last_err}")


def fetch(
    days_back: int = 30,
    request_timeout: int = 45,
    max_retries: int = 3,
) -> list[NewsItem]:
    """Fetch KAP disclosures for fleet banks in the trailing window.

    Paged in `_CHUNK_DAYS` slices so the window actually covers `days_back` —
    see `_ROW_CAP`. Duplicates across slice boundaries are dropped on
    disclosureIndex; the loader is idempotent regardless.
    """
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=days_back)

    rows: list[dict] = []
    seen_idx: set = set()
    start = from_date
    while start <= to_date:
        end = min(start + timedelta(days=_CHUNK_DAYS - 1), to_date)
        chunk = _post_window(start, end, request_timeout, max_retries)
        if len(chunk) >= _ROW_CAP:
            print(f"[kap] WARNING: {start}..{end} returned {len(chunk)} rows — "
                  f"at the {_ROW_CAP} cap, some disclosures were dropped",
                  flush=True)
        for row in chunk:
            idx = row.get("disclosureIndex")
            if idx is not None and idx in seen_idx:
                continue
            if idx is not None:
                seen_idx.add(idx)
            rows.append(row)
        start = end + timedelta(days=1)

    bist_banks = _bist_ticker_set()
    by_title = _member_title_map()
    items: list[NewsItem] = []
    for row in rows:
        codes_raw = (row.get("stockCodes") or "").replace(" ", "")
        # A disclosure may list multiple tickers (e.g. "YKB,YKBNK"); match any.
        codes = [c for c in codes_raw.split(",") if c]
        bank_match = next((c for c in codes if c in bist_banks), None)
        if not bank_match:
            # Pass 2. An unlisted KAP member has no stockCodes at all, so this
            # is the only handle on it. Financial reports only — see module doc.
            subject = row.get("subject") or row.get("kapTitle") or ""
            if _FINANCIAL_REPORT_RX.search(subject):
                bank_match = by_title.get(
                    _normalise_title(row.get("kapTitle") or ""))
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
