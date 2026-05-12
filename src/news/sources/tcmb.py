"""TCMB (Türkiye Cumhuriyet Merkez Bankası) press-release scraper.

Annual archive page returns server-rendered HTML with all press releases
for a year. Stable URL pattern:

  list:    /wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}
  detail:  /wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}/ANO{year}-{nn}

Each list row is structured as:

  <a class="collection-title" href=".../ANO{year}-{nn}"...>Title (year-nn)</a>
  …whitespace…
  <div class="collection-tag">DD/MM/YYYY</div>

We capture both halves in one regex so each NewsItem carries the actual
publish date, not a fallback year-anchor.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

from src.news.loader import NewsItem

BASE = "https://www.tcmb.gov.tr"
LIST_PATH = "/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}"

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}

# Title anchor followed by the date div, with arbitrary whitespace + sibling
# markup between them. DOTALL lets `.*?` span newlines; non-greedy so we don't
# overrun into the next row.
_ROW_RE = re.compile(
    r'<a\s+class="collection-title"[^>]+href="(?P<href>/wps/[^"]*ANO(?P<year>\d{4})-(?P<num>\d+))"[^>]*>'
    r'(?P<label>[^<]+)</a>'
    r'.*?'
    r'<div\s+class="collection-tag">\s*(?P<date>\d{2}/\d{2}/\d{4})\s*</div>',
    re.IGNORECASE | re.DOTALL,
)


def _to_iso(raw: str) -> str:
    """TCMB publish dates are 'DD/MM/YYYY' (Turkey time, date-only)."""
    try:
        d = datetime.strptime(raw, "%d/%m/%Y")
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    return d.replace(tzinfo=timezone.utc).isoformat()


def fetch(years: list[int] | None = None) -> list[NewsItem]:
    """Fetch press releases for the given years (defaults to current year).
    Items returned newest-first by publish date."""
    if years is None:
        years = [datetime.now(timezone.utc).year]
    items: list[NewsItem] = []
    for year in years:
        url = BASE + LIST_PATH.format(year=year)
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            continue
        seen: set[str] = set()
        for m in _ROW_RE.finditer(r.text):
            ano = f"ANO{m.group('year')}-{m.group('num')}"
            if ano in seen:
                continue
            seen.add(ano)
            label = re.sub(r"\s+", " ", m.group("label")).strip()
            # Strip the trailing "(YYYY-NN)" tag that duplicates the ID
            label = re.sub(r"\s*\(\d{4}-\d+\)\s*$", "", label)
            date_str = m.group("date")
            items.append(NewsItem(
                source="tcmb",
                external_id=ano,
                published_at=_to_iso(date_str),
                ticker=None,
                category="press_release",
                title=label or ano,
                summary=None,
                url=BASE + m.group("href"),
                language="en",
                raw_json=json.dumps(
                    {"ano": ano, "label": label, "date": date_str},
                    ensure_ascii=False,
                ),
            ))
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items
