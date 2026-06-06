"""Per-bank IR-page discovery of audit-report PDFs.

Most banks are tracked by hand-maintained URLs in
``data/banks/audit_report_urls.json``. A few publish on a stable, parseable IR
page, so we can auto-discover new quarters instead of hand-adding each URL.

Discovery *augments* the static config: discovered ``(period, kind, url)``
targets are merged into the scrape list, and any failure falls back silently to
the static list. Register a bank by adding its ticker to ``DISCOVERERS``; each
discoverer takes the bank's ``ir_page`` URL and returns
``[(period, kind, url), ...]`` with ``period`` as ``YYYYQN``, ``kind`` in
``{consolidated, unconsolidated}``, and ``url`` absolute.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Callable

import requests

# The audit dataset starts 2022Q1 (see docs/PROJECT_STATE.md). Discovery is
# floored here so a deep IR archive can't silently backfill pre-2022 history;
# anything new and recent is still picked up automatically.
MIN_PERIOD = "2022Q1"

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

# Audit reports are dated at quarter-end; map the month-day to its quarter.
_QTR_BY_MMDD = {"0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "Q4"}


def _period_from_yyyymmdd(d: str) -> str | None:
    """'20260331' -> '2026Q1'. None if not a recognised quarter-end date."""
    q = _QTR_BY_MMDD.get(d[4:8])
    return f"{d[:4]}{q}" if q else None


def _get(url: str) -> str:
    r = requests.get(url, headers=_UA, timeout=60)
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------------------
# EXIM (Türk Eximbank) — unconsolidated only. The IR page lists every quarter
# as a stable link of the form /content/files/<guid>/brsa-YYYYMMDD.
# ---------------------------------------------------------------------------
_EXIM_ORIGIN = "https://www.eximbank.gov.tr"
_EXIM_IR_DEFAULT = f"{_EXIM_ORIGIN}/en/financial-informations/financial-audit-reports/brsa"
_EXIM_PAT = re.compile(r"/content/files/[0-9a-fA-F-]+/brsa-(\d{8})")


def _discover_exim(ir_page: str) -> list[tuple[str, str, str]]:
    html = _get(ir_page or _EXIM_IR_DEFAULT)
    # One PDF per quarter; keep the first (newest-listed) GUID seen per period.
    by_period: dict[str, tuple[str, str, str]] = {}
    for m in _EXIM_PAT.finditer(html):
        period = _period_from_yyyymmdd(m.group(1))
        if not period or period < MIN_PERIOD:
            continue
        by_period.setdefault(period, (period, "unconsolidated", _EXIM_ORIGIN + m.group(0)))
    return list(by_period.values())


# Ticker → discoverer. Banks absent here use the static config only.
DISCOVERERS: dict[str, Callable[[str], list[tuple[str, str, str]]]] = {
    "EXIM": _discover_exim,
}


def discover_targets(ticker: str, ir_page: str) -> list[tuple[str, str, str]]:
    """Auto-discovered ``(period, kind, url)`` for a bank, or ``[]`` if it has
    no discoverer.

    Never raises: on any network/parse error it logs to stderr and returns
    ``[]`` so the caller falls back to the hand-maintained static config."""
    fn = DISCOVERERS.get(ticker.upper())
    if not fn:
        return []
    try:
        found = fn(ir_page)
        print(f"[discover] {ticker}: {len(found)} report(s) from IR page", flush=True)
        return found
    except Exception as e:  # noqa: BLE001 — discovery must never break the sync
        print(f"[discover] {ticker}: FAILED ({type(e).__name__}: {e}) — "
              f"falling back to static config", file=sys.stderr, flush=True)
        return []
