"""BDDK (Bankacılık Düzenleme ve Denetleme Kurumu) duyuru scraper.

The full announcement list lives at /Duyuru/Liste — a single ~800 KB HTML
page with all ~1100 historical Duyuru links. Each row has a stable date
(`<span class="gorunenTarih">DD.MM.YYYY</span>`) plus a Turkish title.
Detail pages are at /Duyuru/Detay/{id}.

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

BASE = "https://www.bddk.org.tr"
LIST_URL = f"{BASE}/Duyuru/Liste"

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
    r = requests.get(LIST_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
    r.raise_for_status()
    text = r.text

    items: list[NewsItem] = []
    for m in _ROW_RE.finditer(text):
        item_id = m.group("id")
        title = html_lib.unescape(m.group("title")).strip()
        if not title:
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
