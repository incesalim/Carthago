"""TCMB (Türkiye Cumhuriyet Merkez Bankası) press-release scraper.

Annual archive page returns server-rendered HTML with all press releases
for a year, each linking to a per-release detail page. Stable URL pattern:

  list:    /wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}
  detail:  /wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases/{year}/ANO{year}-{nn}

Press-release IDs are stable (e.g. ANO2026-19 = "Summary of the MPC Meeting").
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

# Anchor pattern: <a href="/wps/.../ANO2026-19">Press Release on ... (2026-19)</a>
_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>/wps/[^"]*ANO(?P<year>\d{4})-(?P<num>\d+))"[^>]*>(?P<label>[^<]+)</a>',
    re.IGNORECASE,
)


def _to_iso(year: int, raw: str | None) -> str:
    """The list page doesn't carry per-item publish dates — pull from the
    label if present (e.g. "Briefing on May 14, 2026"). Otherwise use
    Jan 1 of the year as a stable, sortable fallback (refined by ANO num)."""
    if raw:
        # Look for 'Month DD, YYYY' inside the label
        m = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})",
            raw,
        )
        if m:
            try:
                return datetime.strptime(m.group(0), "%B %d, %Y").replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return datetime(year, 1, 1, tzinfo=timezone.utc).isoformat()


def fetch(years: list[int] | None = None) -> list[NewsItem]:
    """Fetch all press releases for the given years (defaults to current
    year). Items returned newest-first by ANO id."""
    if years is None:
        years = [datetime.now(timezone.utc).year]
    items: list[NewsItem] = []
    for year in years:
        url = BASE + LIST_PATH.format(year=year)
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            continue
        # Dedup by ANO id since the page sometimes lists each link twice
        seen: set[str] = set()
        for m in _LINK_RE.finditer(r.text):
            ano = f"ANO{m.group('year')}-{m.group('num')}"
            if ano in seen:
                continue
            seen.add(ano)
            label = re.sub(r"\s+", " ", m.group("label")).strip()
            # Strip the trailing "(YYYY-NN)" tag that duplicates the ID
            label = re.sub(r"\s*\(\d{4}-\d+\)\s*$", "", label)
            items.append(NewsItem(
                source="tcmb",
                external_id=ano,
                published_at=_to_iso(int(m.group("year")), label),
                ticker=None,
                category="press_release",
                title=label or ano,
                summary=None,
                url=BASE + m.group("href"),
                language="en",
                raw_json=json.dumps({"ano": ano, "label": label}, ensure_ascii=False),
            ))
    # Newest-first by external_id (string sort works since ANO format is fixed-width)
    items.sort(key=lambda x: x.external_id, reverse=True)
    return items
