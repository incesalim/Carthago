"""Auto-discovery of audit-report PDFs from banks' IR pages.

Most banks are tracked by hand-maintained URLs in
``data/banks/audit_report_urls.json``. Many also publish on a stable, parseable
IR page whose links embed the quarter-end date — so we can auto-discover new
quarters instead of hand-adding each URL.

The engine is generic and *config-anchored*. For a bank it learns, from that
bank's existing config entries, a per-kind *filename skeleton* (the filename
with digits, separators and quarter-month words stripped — e.g.
``TCZB-Konsolide-Olmayan-31032026.pdf`` → ``tczbkonsolideolmayanpdf``). It then
scans the IR page for links that (a) embed a real quarter-end date and (b) whose
skeleton matches a known one — which both filters out the wrong document
(tables-only, English duplicate, …) and assigns the consolidated/unconsolidated
kind. The known config entries are the test oracle: ``scripts/validate_discovery.py``
checks discovery reproduces every known period→URL before a bank is added to
``DISCOVERY_BANKS`` below.

Discovery *augments* the static config and is *fail-safe*: any network/parse
error returns ``[]`` so the caller falls back to the hand-maintained URLs. Only
``requests`` + the stdlib are imported, so the module is safe to import under
CI's minimal dependency set.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

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

# Banks auto-discovery is enabled for — each validated against the config by
# scripts/validate_discovery.py (latest period reproduced, no recent-period URL
# mismatch). Re-run that script and update this set when adding banks or when a
# bank redesigns its IR page.
DISCOVERY_BANKS: set[str] = {
    "ALBRK", "ANADOLU", "EMLAK", "EXIM", "FIBA", "HALKB", "ING",
    "PASHA", "TEB", "TFKB", "TSKB", "VAKIFK", "ZIRAAT",
}

# ---------------------------------------------------------------------------
# Periods & quarter-end dates
# ---------------------------------------------------------------------------
_QTR_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}  # quarter -> (m, d)
_Q_BY_M = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
_Q_IDX = {3: 1, 6: 2, 9: 3, 12: 4}
_TR_MONTH_NUM = {  # quarter-end Turkish month names → month number
    "mart": 3, "haziran": 6, "eylul": 9, "eylül": 9, "aralik": 12, "aralık": 12,
}


def _period_for(year: int, month: int) -> str | None:
    q = _Q_BY_M.get(month)
    return f"{year}{q}" if q else None


# ---------------------------------------------------------------------------
# Date encodings. Banks change format over time, so we try every encoding on
# each link and accept only real quarter-end dates (which also filters upload
# timestamps like ...20260521111045.pdf). Order: specific/longer first.
# ---------------------------------------------------------------------------
class _Fmt:
    def __init__(self, pattern: str, order: str):
        self.re = re.compile(pattern, re.I)
        self.order = order

    def parse(self, m: re.Match) -> tuple[int, int, int] | None:
        g = m.groups()
        try:
            if self.order == "ymd":
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            elif self.order == "dmy":
                d, mo, y = int(g[0]), int(g[1]), int(g[2])
            elif self.order == "tr_dmy":
                d, mo, y = int(g[0]), _TR_MONTH_NUM[g[1].lower()], int(g[2])
            elif self.order == "ym":
                y, mo = int(g[0]), int(g[1])
                d = _QTR_END.get(_Q_IDX.get(mo, 0), (0, 0))[1]
            else:
                return None
        except (ValueError, KeyError):
            return None
        # Accept only genuine quarter-end dates.
        if mo not in _Q_BY_M or (mo, d) != _QTR_END[_Q_IDX[mo]]:
            return None
        return y, mo, d


_FORMATS: list[_Fmt] = [
    _Fmt(r"(20\d\d)-(\d{2})-(\d{2})", "ymd"),               # 2026-03-31
    _Fmt(r"(\d{2})\.(\d{2})\.(20\d\d)", "dmy"),             # 31.03.2026
    _Fmt(r"(\d{2})-(\d{2})-(20\d\d)", "dmy"),               # 31-03-2026
    _Fmt(r"(\d{2})_(\d{2})_(20\d\d)", "dmy"),               # 31_03_2026
    _Fmt(r"(\d{2}) (\d{2}) (20\d\d)", "dmy"),               # 31 03 2026
    _Fmt(r"(20\d\d)(\d{2})(\d{2})", "ymd"),                 # 20260331
    _Fmt(r"(\d{2})(\d{2})(20\d\d)", "dmy"),                 # 31032026
    _Fmt(r"(\d{1,2})-(mart|haziran|eylul|eylül|aralik|aralık)-(20\d\d)", "tr_dmy"),  # 31-mart-2026
    _Fmt(r"(20\d\d)(0[369]|12)", "ym"),                     # 202603 (year-month)
]


def _extract_qend(s: str) -> tuple[int, int, int] | None:
    """First valid quarter-end date in a string, or None."""
    for fmt in _FORMATS:
        for m in fmt.re.finditer(s):
            ymd = fmt.parse(m)
            if ymd:
                return ymd
    return None


# ---------------------------------------------------------------------------
# Filename skeletons (digits / separators / quarter-month words stripped)
# ---------------------------------------------------------------------------
_MONTH_WORDS = re.compile(
    r"(mart|haziran|eylul|eylül|aralik|aralık|march|june|september|december)", re.I)
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _path(u: str) -> str:
    return re.sub(r"^https?://[^/]+", "", u).split("?")[0].lower()


def _filename(u: str) -> str:
    return _path(u).rstrip("/").split("/")[-1]


def _skeleton(filename: str) -> str:
    s = _UUID_RE.sub("", filename.lower())  # re-uploads append a UUID — drop it
    s = _MONTH_WORDS.sub("", s)
    s = re.sub(r"\d+", "", s)
    return re.sub(r"[-_.\s]+", "", s)


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------
_HREF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
_ABS_DOC_RE = re.compile(r"""https?://[^\s"'<>]+?\.(?:pdf|vsf)""", re.I)


def _candidate_urls(html: str, base: str) -> list[str]:
    urls: set[str] = set()
    for m in _HREF_RE.finditer(html):
        urls.add(urljoin(base, m.group(1)))
    for m in _ABS_DOC_RE.finditer(html):
        urls.add(m.group(0))
    return list(urls)


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers=_UA, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# The generic engine
# ---------------------------------------------------------------------------
def discover_from_ir(ticker: str, bank_cfg: dict) -> list[tuple[str, str, str]]:
    """Discovered ``(period, kind, url)`` for a bank from its IR page. Raises on
    network/parse error (the public ``discover_targets`` swallows that)."""
    known: dict[tuple[str, str], str] = {}
    templates: dict[str, set[str]] = {}  # kind -> {filename skeleton, ...}
    for kind, pm in bank_cfg.get("urls", {}).items():
        nk = "unconsolidated" if kind == "unconsolidated_zip" else kind
        for period, url in pm.items():
            known[(nk, period.upper())] = url
            templates.setdefault(nk, set()).add(_skeleton(_filename(url)))
    if not known:
        return []

    # Gate: the bank must encode the quarter-end date in its URLs. Opaque
    # (document-file-NNN.vsf) and upload-timestamp URLs yield nothing here, so
    # they're left to the static config rather than mis-discovered.
    if not any(
        (ymd := _extract_qend(url)) and _period_for(ymd[0], ymd[1]) == period
        for (_k, period), url in known.items()
    ):
        return []

    # Preferred skeleton per kind = the latest config entry's naming. When a
    # page lists several matching docs for one period (full report vs tables-only,
    # TR vs EN, naming that drifted over the years), this picks the one matching
    # the current convention instead of whichever appears first.
    preferred: dict[str, str] = {}
    for kind in templates:
        latest_p = max(p for (k, p) in known if k == kind)
        preferred[kind] = _skeleton(_filename(known[(kind, latest_p)]))

    resp = _get(bank_cfg.get("ir_page", ""))
    base = str(resp.url)
    out: dict[tuple[str, str], str] = {}
    chosen: dict[tuple[str, str], str] = {}  # (kind, period) -> skeleton chosen
    for url in _candidate_urls(resp.text, base):
        ymd = _extract_qend(url)
        if not ymd:
            continue
        period = _period_for(ymd[0], ymd[1])
        if not period or period < MIN_PERIOD:
            continue
        sk = _skeleton(_filename(url))
        for kind, skel_set in templates.items():
            if sk not in skel_set:
                continue
            key = (kind, period)
            # Keep the first match, but upgrade to the preferred naming if seen.
            if key not in out or (sk == preferred[kind] and chosen[key] != preferred[kind]):
                out[key], chosen[key] = url, sk
    return [(period, kind, url) for (kind, period), url in out.items()]


def discover_targets(ticker: str, bank_cfg: dict) -> list[tuple[str, str, str]]:
    """Auto-discovered ``(period, kind, url)`` for a bank, or ``[]`` if it isn't
    enabled for discovery.

    Never raises: on any network/parse error it logs to stderr and returns
    ``[]`` so the caller falls back to the hand-maintained static config."""
    if ticker.upper() not in DISCOVERY_BANKS:
        return []
    try:
        found = discover_from_ir(ticker, bank_cfg)
        print(f"[discover] {ticker}: {len(found)} report(s) from IR page", flush=True)
        return found
    except Exception as e:  # noqa: BLE001 — discovery must never break the sync
        print(f"[discover] {ticker}: FAILED ({type(e).__name__}: {e}) — "
              f"falling back to static config", file=sys.stderr, flush=True)
        return []
