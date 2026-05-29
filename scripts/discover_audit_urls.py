"""Crawl each bank's IR page and propose new quarterly audit-report URLs.

This script does NOT update data/banks/audit_report_urls.json on its own —
it prints proposed additions so a human can sanity-check them first. Run
this each quarter (or whenever D1 is missing a period for some banks)
instead of hand-walking every IR page.

Usage:
  python scripts/discover_audit_urls.py                            # latest quarter, all banks missing it
  python scripts/discover_audit_urls.py --period 2026Q1            # specific quarter
  python scripts/discover_audit_urls.py --ticker AKTIF             # one bank
  python scripts/discover_audit_urls.py --apply                    # write proposals into audit_report_urls.json

How it works:
  1. Read data/banks/audit_report_urls.json for the IR-page URL per bank.
  2. For each missing (bank, period, kind) tuple, fetch the IR page.
  3. Find every <a href="...pdf"> link on the page (recursively up to depth 2
     for IR pages that just list sub-pages).
  4. Score links: must look like a quarterly audit report PDF AND match the
     target period (date in URL/text matches Q-end date, or 'Q1'/'2026', etc.).
  5. Highest-scoring candidate per (bank, kind) goes into the proposal.

Limitations the user should know about:
  - JS-rendered IR pages (rare) → returns nothing for that bank. Add manually.
  - Multi-step nav (click 'Annual Reports' → click 'Q1 2026' → PDF) → handle
    via bank-specific override functions in _BANK_OVERRIDES below.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "data" / "banks" / "audit_report_urls.json"
sys.stdout.reconfigure(encoding="utf-8")

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
    "Accept-Language": "en,tr;q=0.8",
}


# ---------------------------------------------------------------------------
# Period heuristics — turn a quarter code like 2026Q1 into all the substrings
# we expect to see in a PDF filename or surrounding link text.
# ---------------------------------------------------------------------------

_Q_END_DATES = {
    "Q1": ("31", "03"),  # 31 Mart / 31 March
    "Q2": ("30", "06"),
    "Q3": ("30", "09"),
    "Q4": ("31", "12"),
}
_Q_MONTHS_TR = {"Q1": "Mart", "Q2": "Haziran", "Q3": "Eylül", "Q4": "Aralık"}
_Q_MONTHS_EN = {"Q1": "March", "Q2": "June", "Q3": "September", "Q4": "December"}


def _period_tokens(period: str) -> list[str]:
    """Return substrings that, if present in a URL or link text, are strong
    evidence the PDF is for `period`. Used as the scoring signal."""
    yyyy = period[:4]
    q = period[-2:]
    day, mm = _Q_END_DATES[q]
    return [
        # date-based — most reliable
        f"{day}{mm}{yyyy}",          # 31032026
        f"{day}.{mm}.{yyyy}",        # 31.03.2026
        f"{day}-{mm}-{yyyy}",        # 31-03-2026
        f"{day}/{mm}/{yyyy}",        # 31/03/2026 (AKTIF, HSBC)
        f"{day}_{mm}_{yyyy}",
        f"{yyyy}{mm}{day}",          # 20260331 (US-style)
        f"{yyyy}-{mm}-{day}",
        f"{yyyy}/{mm}/{day}",
        f"{yyyy}.{mm}.{day}",
        # month-name + year (space and dash separators)
        f"{_Q_MONTHS_TR[q]} {yyyy}",
        f"{_Q_MONTHS_TR[q].lower()} {yyyy}",
        f"{_Q_MONTHS_TR[q].lower()}-{yyyy}",
        f"{_Q_MONTHS_EN[q]} {yyyy}",
        f"{_Q_MONTHS_EN[q].lower()} {yyyy}",
        f"{_Q_MONTHS_EN[q].lower()}-{yyyy}",
        # day + month-name + year (very common in Turkish URLs/text)
        f"{int(day)} {_Q_MONTHS_TR[q]} {yyyy}",
        f"{int(day)} {_Q_MONTHS_TR[q].lower()} {yyyy}",
        f"{int(day)}-{_Q_MONTHS_TR[q].lower()}-{yyyy}",
        f"{int(day)} {_Q_MONTHS_EN[q]} {yyyy}",
        f"{int(day)}-{_Q_MONTHS_EN[q].lower()}-{yyyy}",
        # quarter code
        f"{q} {yyyy}", f"{q}-{yyyy}", f"{q}_{yyyy}", f"{q.lower()}-{yyyy}",
        f"{yyyy}{q}", f"{yyyy}-{q}", f"{yyyy}_{q}",
    ]


_UNCONS_PAT = re.compile(
    # "konsolide olmayan" with any combination of spaces/dashes/underscores
    # between the two words, OR English negators (non/un) preceding consolidated.
    # Also any standalone 'solo' (Turkish banks commonly tag the
    # unconsolidated file `<name>-solo.pdf`).
    r"(?:konsolide[\s\-_]*olmayan"
    r"|non[\s\-_]*consolidated|unconsolidated"
    r"|(?<![A-Za-z])solo(?![A-Za-z]))",
    re.IGNORECASE,
)
_CONS_POS_PAT = re.compile(
    r"(?:konsolide|consolidated|_kons[\s\-_]|/kons[\s\-_]|/cons/)",
    re.IGNORECASE,
)


def _kind_score(hay: str, kind: str) -> int:
    """Score how well a URL+text matches `kind`.

    The tricky case: "konsolide olmayan" (Turkish for 'non-consolidated')
    contains the substring "konsolide" — naive substring matching would
    flag it as consolidated. We detect the negator first; if found, the
    link is unconsolidated regardless of how many 'konsolide' tokens
    appear.
    """
    is_uncons = bool(_UNCONS_PAT.search(hay))
    is_cons = bool(_CONS_POS_PAT.search(hay)) and not is_uncons
    if kind == "consolidated":
        return 5 if is_cons else (-10 if is_uncons else 0)
    return 5 if is_uncons else (-10 if is_cons else 0)


# ---------------------------------------------------------------------------
# IR-page fetch + PDF link extraction
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    url: str
    score: int
    text: str       # surrounding link text
    source: str     # source page where we found it


def _fetch(url: str, referer: str | None = None) -> str | None:
    headers = dict(UA)
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        print(f"    fetch {url}: {type(e).__name__}", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"    fetch {url}: HTTP {r.status_code}", file=sys.stderr)
        return None
    # IR pages are HTML — chardet often guesses wrong; trust Content-Type.
    enc = r.apparent_encoding or "utf-8"
    return r.content.decode(enc, errors="replace")


def _fetch_rendered(url: str, wait_ms: int = 3000) -> str | None:
    """Playwright fallback for IR pages that load content via JavaScript.

    Some banks (ISCTR, TFKB, VAKBN, ALNTF, ATBANK, ZIRAATK as observed) serve
    a near-empty HTML shell to plain HTTP clients — the actual list of
    financial reports is fetched and injected after page load. We fall back
    here when the static path returns very few links.
    """
    try:
        from playwright.sync_api import sync_playwright  # imported lazily
    except ImportError:
        print(f"    [{url}] playwright not installed — pip install playwright "
              "&& playwright install chromium", file=sys.stderr)
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA["User-Agent"])
            page = ctx.new_page()
            # Some IR pages cookie-banner-block content until scrolled; wait
            # for network-idle, then give a bonus delay for slow XHRs.
            # Use 'domcontentloaded' (faster) — IR pages often have lingering
            # XHR / tracking pixels that prevent 'networkidle' from ever firing.
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Give SPAs time to inject content after DOMContentLoaded.
            page.wait_for_timeout(wait_ms)
            # Best-effort: scroll to trigger lazy-loaded sections.
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"    [{url}] playwright: {type(e).__name__}: {str(e)[:120]}",
              file=sys.stderr)
        return None


def _find_pdf_links(html: str, base: str) -> list[tuple[str, str]]:
    """Return [(absolute_url, link_text)] for every <a href> that looks like
    a PDF (.pdf extension OR linked text mentions 'pdf', 'rapor', 'report')."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        is_pdf = href.lower().endswith(".pdf") or ".pdf?" in href.lower()
        # Some sites don't put .pdf in the URL (CDN-served via UUID). Treat
        # any link whose surrounding text mentions audit/report as a candidate.
        looks_report = bool(re.search(
            r"\b(?:pdf|rapor|raporu|report|denetim|financial|finansal|brsa|bddk)\b",
            (href + " " + text).lower(),
        ))
        if not (is_pdf or looks_report):
            continue
        out.append((urljoin(base, href), text))
    return out


def _score_link(url: str, text: str, period: str, kind: str) -> int:
    """Higher score = stronger evidence this link is the (period, kind) PDF.

    Returns 0 if the link is provably for the WRONG kind (e.g. URL says
    'Unconsolidated' but we asked for 'consolidated') — prevents the
    fallback from offering a wrong-kind URL as the best consolidated
    candidate just because nothing better exists on the page.
    """
    hay = (url + " " + text).lower()
    # Also produce a "compressed" haystack with all separator characters
    # stripped — handles cases like 'TFKB 31 03 2026 konsolide.pdf' where
    # the date uses space separators that none of our literal tokens catch.
    hay_compact = re.sub(r"[\s\-_./]", "", hay)
    period_hits = sum(
        1 for tok in _period_tokens(period)
        if tok.lower() in hay or re.sub(r"[\s\-_./]", "", tok.lower()) in hay_compact
    )
    if period_hits == 0:
        return 0
    # Kind disambiguation — handles "konsolide olmayan" (= unconsolidated)
    # correctly even though it contains "konsolide" as a substring. A
    # negative score here means the URL EXPLICITLY claims the other kind.
    ks = _kind_score(hay, kind)
    if ks < 0:
        return 0
    score = period_hits * 10 + ks
    if url.lower().endswith(".pdf"):
        score += 2
    return score


# ---------------------------------------------------------------------------
# Bank-specific overrides — for IR pages that need extra logic.
# Each function takes (ir_page_url, period, kind) and returns a candidate
# URL or None.
# ---------------------------------------------------------------------------

_BANK_OVERRIDES: dict[str, Callable[[str, str, str], list[Candidate]]] = {}


def _bank_override(ticker: str):
    def wrap(fn):
        _BANK_OVERRIDES[ticker] = fn
        return fn
    return wrap


# (Add bank-specific functions here as we discover ones that need them.)


# ---------------------------------------------------------------------------
# Main discovery loop
# ---------------------------------------------------------------------------

def _discover_for_bank(
    ticker: str, entry: dict, period: str, kinds: list[str],
) -> dict[str, Candidate | None]:
    """Crawl one bank's IR page, return best candidate per kind."""
    ir_page = entry.get("ir_page")
    if not ir_page:
        print(f"  {ticker}: no ir_page configured — skipping", file=sys.stderr)
        return {k: None for k in kinds}

    out: dict[str, Candidate | None] = {}

    # Bank-specific override path.
    if ticker in _BANK_OVERRIDES:
        candidates = _BANK_OVERRIDES[ticker](ir_page, period, "consolidated")
        for k in kinds:
            best = max(
                (c for c in candidates if _score_link(c.url, c.text, period, k) > 0),
                key=lambda c: _score_link(c.url, c.text, period, k),
                default=None,
            )
            out[k] = best
        return out

    # Generic path: fetch IR page, harvest PDF links, score.
    html = _fetch(ir_page, referer=ir_page)
    links: list[tuple[str, str]] = _find_pdf_links(html, ir_page) if html else []
    print(f"  {ticker}: {len(links)} candidate links on IR page (static)")

    def _best_per_kind(links_in: list[tuple[str, str]]) -> dict[str, Candidate | None]:
        result: dict[str, Candidate | None] = {}
        for k in kinds:
            scored = [
                Candidate(url=u, score=s, text=t, source=ir_page)
                for (u, t) in links_in
                for s in (_score_link(u, t, period, k),)
                if s > 0
            ]
            scored.sort(key=lambda c: c.score, reverse=True)
            result[k] = scored[0] if scored else None
        return result

    out = _best_per_kind(links)

    # Fallback: if static returned ≤20 links OR no kinds got a hit, retry
    # with Playwright. Banks like ISCTR / TFKB / VAKBN / ALNTF render their
    # report list via JavaScript so the static HTML is near-empty.
    needs_js = (len(links) <= 20) or all(v is None for v in out.values())
    if needs_js:
        print(f"  {ticker}: retrying with Playwright (static too sparse)")
        html_js = _fetch_rendered(ir_page)
        if html_js:
            links_js = _find_pdf_links(html_js, ir_page)
            print(f"  {ticker}: {len(links_js)} candidate links (JS-rendered)")
            out_js = _best_per_kind(links_js)
            # Prefer JS result when it improves coverage / score.
            for k in kinds:
                if out[k] is None or (out_js[k] and out_js[k].score > out[k].score):
                    out[k] = out_js[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default=None,
                    help="Target period like 2026Q1. Defaults to all periods "
                         "that exist for ≥1 bank but not all.")
    ap.add_argument("--ticker", default=None, help="Crawl only this bank.")
    ap.add_argument("--apply", action="store_true",
                    help="Write the proposed URLs into audit_report_urls.json.")
    args = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    banks = cfg["banks"]
    target_period = args.period or _infer_target_period(banks)
    if not target_period:
        print("Could not infer target period — pass --period explicitly.")
        return
    print(f"target period: {target_period}\n")

    tickers = [args.ticker.upper()] if args.ticker else _missing_banks(banks, target_period)
    if not tickers:
        print(f"All banks already have {target_period} URLs — nothing to do.")
        return

    proposals: dict[str, dict[str, str]] = {}
    for ticker in tickers:
        entry = banks.get(ticker)
        if not entry:
            print(f"{ticker}: not in audit_report_urls.json — skipping")
            continue
        kinds = [k for k in ("consolidated", "unconsolidated")
                 if k in entry.get("urls", {})]
        if not kinds:
            print(f"{ticker}: no kinds configured — skipping")
            continue
        # Skip kinds that already have the target period.
        kinds = [k for k in kinds if target_period not in entry["urls"][k]]
        if not kinds:
            continue
        print(f"\n{ticker} ({entry.get('name','?')}):")
        results = _discover_for_bank(ticker, entry, target_period, kinds)
        for kind, cand in results.items():
            if cand is None:
                print(f"  → {kind}: NO MATCH (visit {entry['ir_page']} manually)")
                continue
            print(f"  → {kind}: score={cand.score} {cand.url}")
            print(f"      text: {cand.text[:120]}")
            proposals.setdefault(ticker, {})[kind] = cand.url

    if not proposals:
        print("\nNo proposals found. Banks may not have published yet, or IR pages "
              "need manual inspection.")
        return

    print(f"\n=== {sum(len(v) for v in proposals.values())} URL proposals "
          f"across {len(proposals)} banks ===")

    if args.apply:
        for ticker, by_kind in proposals.items():
            for kind, url in by_kind.items():
                banks[ticker]["urls"][kind][target_period] = url
        cfg["_updated"] = _today_iso()
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        print(f"\nWrote proposals into {CONFIG}")
    else:
        print("\n(dry-run — pass --apply to write into audit_report_urls.json)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_iso() -> str:
    import datetime as _dt
    return _dt.date.today().isoformat()


def _infer_target_period(banks: dict) -> str | None:
    """Pick the latest quarter that ≥1 bank has but ≥1 other bank doesn't."""
    all_periods: set[str] = set()
    for entry in banks.values():
        for kind_urls in entry.get("urls", {}).values():
            all_periods.update(kind_urls.keys())
    if not all_periods:
        return None
    # Sort 2026Q1 > 2025Q4 > ...
    for p in sorted(all_periods, reverse=True):
        if any(p not in entry.get("urls", {}).get(k, {})
               for entry in banks.values()
               for k in entry.get("urls", {})):
            return p
    return None


def _missing_banks(banks: dict, period: str) -> list[str]:
    out: list[str] = []
    for ticker, entry in banks.items():
        for kind, urls in entry.get("urls", {}).items():
            if period not in urls:
                out.append(ticker)
                break
    return sorted(out)


if __name__ == "__main__":
    main()
