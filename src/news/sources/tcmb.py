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
from src.news._htmltext import extract_body

BASE = "https://www.tcmb.gov.tr"
LIST_PATH = "/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}"

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}

# Cap stored body length so unusually long press releases don't bloat D1.
# 8 KB is enough for every TCMB release sampled (MPC meetings are ~3-4 KB).
BODY_MAX_CHARS = 8000

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


# Pattern to match the press-release content area: TCMB renders the body
# inside <div class="contentMain"> ... </div> with substantive text in <p>
# tags. We don't bound by a single class because the wrapper name has
# drifted across template versions; instead we collect every >30-char
# <p> block in document order until we hit footer boilerplate.
_FOOTER_MARKERS = (
    "Address:",  "Adres:",
    "Türkiye Cumhuriyet Merkez Bankası",
    "© Central Bank",
)


def fetch_body(url: str, timeout: int = 30) -> str | None:
    """Fetch a TCMB ANO detail page and extract the press-release body.

    Captures <p> prose and any <table> blocks (rendered as Markdown) in
    document order — TCMB macroprudential releases put the caps/ratios in a
    table, so dropping tables would discard the substance of the release."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    # include_lists: TCMB sometimes puts rate changes in a <ul> rather than a
    # table. TCMB doesn't server-render nav menus as <ul>, so this is safe.
    return extract_body(r.text, _FOOTER_MARKERS, BODY_MAX_CHARS, include_lists=True)


def fetch(years: list[int] | None = None, years_back: int = 5) -> list[NewsItem]:
    """Fetch press releases for the given years (defaults to current year
    and the prior `years_back-1` years). TCMB publishes ~50 press
    releases per year, so 5 years = ~250 items. Items returned
    newest-first by publish date."""
    if years is None:
        current = datetime.now(timezone.utc).year
        years = list(range(current, current - years_back, -1))
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
