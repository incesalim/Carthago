"""Discover and download TBB quarterly digital-banking ``.xls`` reports.

TBB publishes one report per quarter under a predictable slug,
``{year}-{month}-dijital-internet-ve-mobil-bankacilik-istatistikleri`` (e.g.
``2026-mart-…``). The period picker on the page is an AJAX taxonomy dropdown,
which is brittle to scrape — so discovery instead *constructs* the quarter
slugs and verifies each with a cheap request. Each report page exposes three
Drupal download nodes (``/download/node/<nid>/field_raporlar_ekler/<fid>``) for
the PDF / Word / Excel; we pick the Excel by its Content-Disposition filename.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = "https://www.tbb.org.tr/istatistiki-raporlar/"
SUFFIX = "-dijital-internet-ve-mobil-bankacilik-istatistikleri"

# Quarter month-slug → quarter-end month number (the reports are quarterly).
QUARTER_MONTHS = {"mart": 3, "haziran": 6, "eylul": 9, "aralik": 12}

_DOWNLOAD_RE = re.compile(r'/download/node/\d+/field_raporlar_ekler/\d+')
_HEADERS = {
    # TBB returns 403 to the default python-requests UA; present a browser UA.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


@dataclass
class Report:
    period: str   # YYYY-MM (quarter-end)
    year: int
    month_slug: str
    url: str
    xls_url: str | None = None  # resolved when discovered with require_xls


def report_url(year: int, month_slug: str) -> str:
    return f"{BASE}{year}-{month_slug}{SUFFIX}"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def discover_reports(
    start_year: int,
    end_year: int,
    session: requests.Session | None = None,
    require_xls: bool = True,
) -> list[Report]:
    """Return the quarterly reports that exist for ``start_year..end_year``
    (inclusive), newest first.

    TBB serves a 200 placeholder for not-yet-published quarters, so a HEAD on
    the slug is not enough. With ``require_xls`` (default) each candidate is
    confirmed by resolving its Excel link — placeholders return ``None`` and are
    dropped, and the resolved URL is cached on the ``Report``.
    """
    s = session or _session()
    found: list[Report] = []
    for year in range(end_year, start_year - 1, -1):
        for month_slug, mm in sorted(QUARTER_MONTHS.items(), key=lambda kv: -kv[1]):
            url = report_url(year, month_slug)
            rep = Report(f"{year:04d}-{mm:02d}", year, month_slug, url)
            try:
                if require_xls:
                    rep.xls_url = find_xls_url(url, session=s)
                    if not rep.xls_url:
                        continue
                else:
                    if s.head(url, timeout=30, allow_redirects=True).status_code != 200:
                        continue
            except requests.RequestException:
                continue
            found.append(rep)
    return found


def find_xls_url(report: Report | str, session: requests.Session | None = None) -> str | None:
    """Resolve the Excel download URL on a report page. Accepts a ``Report`` or
    a report-page URL. Returns the absolute ``.xls`` URL, or ``None``."""
    s = session or _session()
    page_url = report.url if isinstance(report, Report) else report
    r = s.get(page_url, timeout=60)
    r.raise_for_status()
    links = list(dict.fromkeys(_DOWNLOAD_RE.findall(r.text)))  # dedupe, keep order
    for rel in links:
        full = "https://www.tbb.org.tr" + rel
        try:
            h = s.head(full, timeout=30, allow_redirects=True)
            disp = h.headers.get("Content-Disposition", "")
            ctype = h.headers.get("Content-Type", "")
        except requests.RequestException:
            continue
        if ".xls" in disp.lower() or "ms-excel" in ctype.lower():
            return full
    return None


def download_xls(
    report: Report | str,
    dest_dir: str | Path,
    session: requests.Session | None = None,
) -> Path | None:
    """Download a report's ``.xls`` into ``dest_dir``. The filename is the
    period when known (``tbb_digital_<period>.xls``), else derived from the URL.
    Returns the local path, or ``None`` if no Excel link was found."""
    s = session or _session()
    xls = report.xls_url if isinstance(report, Report) and report.xls_url else None
    if not xls:
        xls = find_xls_url(report, session=s)
    if not xls:
        return None
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = (
        f"tbb_digital_{report.period}.xls"
        if isinstance(report, Report)
        else f"tbb_digital_{xls.rsplit('/', 1)[-1]}.xls"
    )
    dest = dest_dir / name
    with s.get(xls, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
    return dest
