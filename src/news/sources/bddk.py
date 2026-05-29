"""BDDK (Bankacılık Düzenleme ve Denetleme Kurumu) duyuru scraper.

The full announcement list lives at /Duyuru/Liste — a single ~800 KB HTML
page with all ~1100 historical Duyuru links. Each row has a stable date
(`<span class="gorunenTarih">DD.MM.YYYY</span>`) plus a Turkish title.
Detail pages are at /Duyuru/Detay/{id}.

Filtering: BDDK's Duyuru feed mixes high-signal regulatory decisions
(Kurul Kararı — license grants/revocations, capital adequacy directives,
fines) with low-signal operational noise (Monthly Bulletin / Fintürk
data publication notices, internal HR posts about staff exams). The
NOISE_PATTERNS list below drops the noise at scrape time; cleanup of
already-stored rows is in scripts/sync_news.py.

Note: BDDK does not publish English versions of its announcements;
language is always 'tr'.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone

import requests

from src.news.loader import NewsItem
from src.news._htmltext import extract_body
from src.scrapers._http import bddk_verify


# Title patterns to drop. Case-insensitive on the part that matters.
# Each entry is documented with an example of what it catches.
NOISE_PATTERNS: list[re.Pattern[str]] = [
    # "İnteraktif Aylık Bülten 2026 Mart verileri yayımlanmıştır"
    # "Fintürk 2026 Mart verileri yayımlanmıştır."
    # — routine BDDK data-portal publication notices; the actual data
    #   they announce is already in our `balance_sheet` / `weekly_series` tables.
    re.compile(r"verileri\s+yay[ıi]mlanm[ıi][şs]t[ıi]r", re.IGNORECASE),
    # "2025 Yılı Görevde Yükselme ve Ünvan Değişikliği sınavında başarılı olan personel"
    # — internal HR: promotion exam results.
    re.compile(r"G[oö]revde\s+Y[uü]kselme", re.IGNORECASE),
    re.compile(r"[ÜU]nvan\s+De[gğ]i[şs]ikli[gğ]i", re.IGNORECASE),
    # Generic personnel/recruitment notices.
    re.compile(r"personel\s+(alımı|belli\s+olmu[şs])", re.IGNORECASE),
    # Internal exam announcements.
    re.compile(r"s[ıi]nav[ıi]\s+(?:duyurusu|takvimi)", re.IGNORECASE),
]


def is_noise(title: str) -> bool:
    """True if the title looks like BDDK operational/internal noise."""
    return any(p.search(title) for p in NOISE_PATTERNS)

BASE = "https://www.bddk.org.tr"
LIST_URL = f"{BASE}/Duyuru/Liste"
BODY_MAX_CHARS = 4000

# Markers that signal we've fallen out of the announcement body into site
# boilerplate (cookie notice, copyright, etc.).
_BODY_NOISE = (
    "Kurumumuzun internet adresi",
    "BDDK web sitesi",
    "Web sitemizde yayınlanan çalışmalardan",
    "Bu sitede yer alan bilgi",
    "Telif Hakkı",
    "Çerez Politika",
    # Contact-info footer block (rendered as a <table>): phone/call-centre/
    # address. These markers stop the extractor before that footer table.
    "Çağrı Merkezi",
    "Finanskent Mahallesi",
)

# Match the whole <a><span class="icon">…</span><span class="text">…</span></a>
# block. Captures: id, displayed date, title text after the date span.
_ROW_RE = re.compile(
    r'<a[^>]+href="/Duyuru/Detay/(?P<id>\d+)"[^>]*>\s*'
    r'<span class="icon">.*?</span>\s*'
    r'<span class="text">\s*'
    r'<span class="gorunenTarih">(?P<date>\d{2}\.\d{2}\.\d{4})</span>\s*'
    r'(?P<title>[^<]+?)\s*'
    r'</span>\s*'
    r'</a>',
    re.DOTALL,
)


def fetch_body(url: str, timeout: int = 30) -> str | None:
    """Fetch a BDDK Duyuru detail page and extract the announcement body.

    The detail page is wrapped in a lot of site chrome; the actual
    announcement text is in the first <p>/<table> blocks before boilerplate
    starts (cookie notice, copyright, terms). We collect them in document
    order — tables as Markdown — and stop at the first boilerplate marker."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                         timeout=timeout, verify=bddk_verify())
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return extract_body(r.text, _BODY_NOISE, BODY_MAX_CHARS)


def _to_iso(raw: str) -> str:
    """BDDK dates are 'DD.MM.YYYY' (Turkey time, date-only)."""
    try:
        d = datetime.strptime(raw, "%d.%m.%Y")
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    return d.replace(tzinfo=timezone.utc).isoformat()


def fetch(limit: int | None = 200) -> list[NewsItem]:
    """Fetch the most recent BDDK announcements (newest first).

    `limit=None` returns the full historical list (~1100 rows).
    """
    r = requests.get(LIST_URL, headers={"User-Agent": "Mozilla/5.0"},
                     timeout=45, verify=bddk_verify())
    r.raise_for_status()
    text = r.text

    items: list[NewsItem] = []
    for m in _ROW_RE.finditer(text):
        item_id = m.group("id")
        title = html_lib.unescape(m.group("title")).strip()
        if not title or is_noise(title):
            continue
        items.append(NewsItem(
            source="bddk",
            external_id=item_id,
            published_at=_to_iso(m.group("date")),
            ticker=None,
            category="duyuru",
            title=title,
            summary=None,
            url=f"{BASE}/Duyuru/Detay/{item_id}",
            language="tr",
            raw_json=json.dumps({"date": m.group("date"), "title": title}, ensure_ascii=False),
        ))

    # Newest first
    items.sort(key=lambda x: x.published_at, reverse=True)
    if limit is not None:
        items = items[:limit]
    return items
