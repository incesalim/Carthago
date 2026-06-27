"""Discover quarterly investor/earnings presentation PDFs from banks' IR sites.

Reuses the audit-lane discovery engine (``src/audit_reports/discovery.py``) —
same config-anchored, fail-safe approach: learn a filename *skeleton* from a few
known per-quarter URLs in ``data/banks/investor_presentation_urls.json``, then
scan the IR page for links that (a) resolve to a real quarter and (b) match a
known skeleton. We import the audit module's helpers rather than modify it (it
is validated and load-bearing for the audit lane).

Presentation decks differ from audit reports in one way: their filenames carry a
quarter *code* (``1q26``, ``1Ç2025``) far more often than a quarter-end *date*
(``31032026``). So this module adds ``_extract_qcode`` and resolves a URL's
period from either encoding. Banks whose deck URLs are fully opaque (UUID/CMS
filenames with no quarter token) gate to ``[]`` and stay static-config-only.

Only ``requests`` + stdlib are imported (via the audit module), so this is safe
under CI's minimal dependency set.
"""
from __future__ import annotations

import re
import sys

from src.audit_reports.discovery import (
    MIN_PERIOD,
    _candidate_urls,
    _extract_qend,
    _filename,
    _get,
    _period_for,
    _skeleton,
)

KIND = "presentation"

# Banks enabled for auto-discovery — each validated by
# scripts/diagnostics/validate_presentation_discovery.py (it reproduces the
# known period→URL mapping). Banks not listed here use static config only.
#
# GARAN/AKBNK/YKBNK validated 2026-06-27: all reproduce their seeded quarters and
# backfill older ones. GARAN/AKBNK use uniform "{Q}Q{YY}" filenames so discovery
# finds every quarter; YKBNK's interim decks use 1H/9M/full-year codes that the
# quarter-code parser doesn't read, so discovery augments its Q1s while the static
# seed carries Q2/Q3/Q4.
PRESENTATION_BANKS: set[str] = {"GARAN", "AKBNK", "YKBNK"}

# Quarter code: "1Q26", "4Q2025", "1Ç2025", "2c25". Quarter ordinal + year.
# The trailing (?!\d) (not \b — an underscore is a word char, so "1Q26_BRSA"
# has no \b after "26") rejects longer digit runs like an upload timestamp.
_QCODE_RE = re.compile(r"([1-4])\s*[qçc]\s*((?:20)?\d{2})(?!\d)", re.I)


def _extract_qcode(s: str) -> str | None:
    """First ``'YYYYQn'`` from a quarter-code token in a string, or None."""
    for m in _QCODE_RE.finditer(s):
        q = int(m.group(1))
        yr = m.group(2)
        year = int(yr) if len(yr) == 4 else 2000 + int(yr)
        if 2000 <= year <= 2099:
            return f"{year}Q{q}"
    return None


def _period_of(url: str) -> str | None:
    """Resolve a URL to a quarter from a quarter-end date OR a quarter code."""
    ymd = _extract_qend(url)
    if ymd:
        p = _period_for(ymd[0], ymd[1])
        if p:
            return p
    return _extract_qcode(url)


def discover_presentation(ticker: str, bank_cfg: dict) -> list[tuple[str, str]]:
    """Discovered ``(period, url)`` presentation decks for a bank from its IR
    page. Raises on network/parse error (the public wrapper swallows that)."""
    pm = (bank_cfg.get("urls") or {}).get(KIND) or {}
    known: dict[str, str] = {p.upper(): u for p, u in pm.items()}
    if not known:
        return []

    skeletons = {_skeleton(_filename(u)) for u in known.values()}

    # Gate: at least one known URL must encode its own quarter (date or code),
    # else the filenames are opaque and we leave the bank to static config.
    if not any(_period_of(u) == p for p, u in known.items()):
        return []

    # Preferred skeleton = the latest known quarter's naming (handles drift /
    # several decks per page — TR vs EN, earnings vs investor-day).
    latest_p = max(known)
    preferred = _skeleton(_filename(known[latest_p]))

    resp = _get(bank_cfg.get("ir_page", ""))
    out: dict[str, str] = {}
    chosen_skel: dict[str, str] = {}
    for url in _candidate_urls(resp.text, str(resp.url)):
        period = _period_of(url)
        if not period or period < MIN_PERIOD:
            continue
        sk = _skeleton(_filename(url))
        if sk not in skeletons:
            continue
        if period not in out or (sk == preferred and chosen_skel[period] != preferred):
            out[period], chosen_skel[period] = url, sk
    return sorted(out.items())


def discover_presentation_targets(ticker: str, bank_cfg: dict) -> list[tuple[str, str]]:
    """Auto-discovered ``(period, url)`` decks, or ``[]`` if the bank isn't
    enabled for discovery. Never raises — logs and falls back to ``[]`` so the
    caller keeps the hand-maintained static URLs."""
    if ticker.upper() not in PRESENTATION_BANKS:
        return []
    try:
        found = discover_presentation(ticker, bank_cfg)
        print(f"[present-discover] {ticker}: {len(found)} deck(s) from IR page", flush=True)
        return found
    except Exception as e:  # noqa: BLE001 — discovery must never break the sync
        print(f"[present-discover] {ticker}: FAILED ({type(e).__name__}: {e}) — "
              f"falling back to static config", file=sys.stderr, flush=True)
        return []
