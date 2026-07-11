"""Scrape per-bank ADVERTISED lending & deposit rates → bank_advertised_rates.

Two public comparison pages, both server-rendered (parseable with requests +
lxml only — no JS/browser, so it runs under CI's minimal deps and in a plain
Actions runner):

  LOANS  — doviz.com/kredi/{ihtiyac,konut,tasit}-kredisi. Each page is a single
           HTML <table>: Banka · Kredi Adı · Faiz Oranı (MONTHLY %) · min/max
           vade (months). One POINT rate per bank per product.
  DEPOSITS — hangikredi.com/yatirim-araclari/mevduat-faiz-oranlari. The visible
           table server-renders only the first ~8 banks (rest lazy-load), but
           the FULL per-bank list is embedded in the page's __NEXT_DATA__ JSON
           at props.pageProps.deposit.interestRateTable.interestRates — each a
           min–max advertised BAND (ANNUAL %) with term/amount eligibility bands.

Politeness / ToS: these are affiliate comparison aggregators. We fetch each page
once per weekly run with a real UA and store source + source_url on every row.
doviz robots.txt permits /kredi/*; we take deposits from hangikredi (its /kredi/*
is disallowed — we never touch it). Idempotent per day via INSERT OR REPLACE.

Bank-name → ticker resolution reuses src/news/bank_tagger (the same Turkish
alias matcher the news lane uses), plus a small local map for the digital
sub-brands the aggregators list that the news aliases don't cover.

Run: python -m src.rates.scraper [db_path]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from lxml import html as lh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.news.bank_tagger import _fold, match_banks  # noqa: E402
from src.rates.schema import init_schema  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "bddk_data.db"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
TIMEOUT = 25

DOVIZ_LOANS = [
    ("https://www.doviz.com/kredi/ihtiyac-kredisi", "loan_consumer"),
    ("https://www.doviz.com/kredi/konut-kredisi", "loan_mortgage"),
    ("https://www.doviz.com/kredi/tasit-kredisi", "loan_vehicle"),
]
HANGIKREDI_DEPOSIT = "https://www.hangikredi.com/yatirim-araclari/mevduat-faiz-oranlari"

# Names the aggregators use that src/news/bank_aliases.json doesn't cover. Two
# groups, both folded-substring → ticker:
#
#  1. NEW-ENTRANT BANKS — licensed banks in their own right, added to the `banks`
#     dimension by web/migrations/0022 (universe is 37, not the old 31). These are
#     NOT their former parent: Enpara Bank != QNB, Ziraat Dinamik != Ziraat
#     Bankası, Hayat Finans is its own participation bank. bank_aliases.json still
#     only lists the original 31, so they must be resolved here.
#  2. DIGITAL SUB-BRANDS — marketing brands of an existing bank (no separate
#     licence), which DO map to the parent.
#
# Longer, more-specific keys must precede any bare prefix they contain
# (e.g. "ziraat dinamik" before anything matching "ziraat").
EXTRA_ALIASES = {
    # 1. new-entrant banks (own ticker in `banks`)
    "enpara": "ENPARA",          # Enpara Bank A.Ş. — own licence, ex-QNB digital
    "ziraat dinamik": "ZIRAATD", # Ziraat Dinamik Banka A.Ş. — own licence
    "hayat finans": "HAYATK",    # Hayat Finans Katılım Bankası A.Ş.
    "colendi": "COLENDI",
    "dünya katılım": "DUNYAK",
    "t.o.m.": "TOMK",
    # 2. digital sub-brands of an existing bank → parent ticker
    "cepteteb": "TEB",           # TEB's digital brand
    "on dijital": "ODEA",        # Odeabank's digital brand
    "n kolay": "AKTIF",          # Aktifbank's retail brand
    "odea": "ODEA",              # bare "Odea" (news alias needs the "Bank" suffix)
}
# Institutions that appear on the aggregators but are NOT banks in the audited
# universe (fintechs, banks we don't cover). Resolve to NULL and suppress the
# "unmapped" warning — these NULLs are expected, not misses.
KNOWN_UNAUDITED = (
    "getirfinans", "getir finans", "türk ticaret bankas",
)

COLUMNS = [
    "source", "rate_type", "raw_bank_name", "bank_ticker", "product_name",
    "currency", "rate", "rate_min", "rate_max", "rate_basis", "term_min",
    "term_max", "term_unit", "amount_min", "amount_max", "snapshot_date",
    "source_url", "downloaded_at",
]


# --------------------------------------------------------------------------- #
# Parsing helpers (pure — unit-tested without network)
# --------------------------------------------------------------------------- #
def parse_pct(s: str | None) -> float | None:
    """'%5,06' → 5.06 · '%0 (Faizsiz)' → 0.0 · '%12.5' → 12.5. TR decimal comma."""
    if s is None:
        return None
    # `*` not `?` on the separator group: a number may carry BOTH a thousands
    # separator and a decimal one ("1.234,56"), and stopping at the first would
    # silently truncate it to 1.234.
    m = re.search(r"-?\d+(?:[.,]\d+)*", s)
    if not m:
        return None
    raw = m.group(0)
    if "," in raw and "." in raw:      # '1.234,56' → thousands dot, decimal comma
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:                   # '5,06' → decimal comma
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_int(s: str | None) -> int | None:
    """'12 Ay' → 12 · '400 Gün' → 400."""
    if s is None:
        return None
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else None


def resolve_ticker(name: str) -> str | None:
    """Bank display name → canonical ticker, or None if not in the audited 31.

    Local sub-brand map first, then the shared news alias matcher. A name that
    matches several tickers is treated as unresolved (None) rather than guessed.
    """
    folded = _fold(name)
    for sub, ticker in EXTRA_ALIASES.items():
        if sub in folded:
            return ticker
    if any(nb in folded for nb in KNOWN_UNAUDITED):
        return None
    hits = match_banks(name)
    if len(hits) == 1:
        return next(iter(hits))
    return None


def _is_expected_null(name: str) -> bool:
    """True for names we knowingly leave unresolved (outside the audited 31)."""
    return any(nb in _fold(name) for nb in KNOWN_UNAUDITED)


def _row(**kw) -> dict:
    """Build a full-width row dict; snapshot_date/downloaded_at filled at write."""
    base = {c: None for c in COLUMNS}
    base.update(product_name="", currency="TRY")
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Fetch + parse each source
# --------------------------------------------------------------------------- #
def _get(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def parse_doviz_loans(html_text: str, url: str, rate_type: str) -> list[dict]:
    """Parse one doviz loan page's table into point-rate rows."""
    doc = lh.fromstring(html_text)
    tables = doc.xpath("//table")
    if not tables:
        return []
    rows_out: list[dict] = []
    body = tables[0].xpath(".//tbody/tr") or tables[0].xpath(".//tr")
    for tr in body:
        cells = [c.text_content().strip() for c in tr.xpath("./td|./th")]
        if len(cells) < 5 or "%" not in cells[2]:  # skip header/footer rows
            continue
        bank, product, rate_s, min_s, max_s = cells[:5]
        rows_out.append(_row(
            source="doviz.com", rate_type=rate_type, raw_bank_name=bank,
            bank_ticker=resolve_ticker(bank), product_name=product or "",
            currency="TRY", rate=parse_pct(rate_s), rate_basis="monthly",
            term_min=parse_int(min_s), term_max=parse_int(max_s),
            term_unit="months", source_url=url,
        ))
    return rows_out


def parse_hangikredi_deposits(html_text: str, url: str) -> list[dict]:
    """Parse the __NEXT_DATA__ deposit table (full per-bank list, TL only)."""
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S
    )
    if not m:
        return []
    data = json.loads(m.group(1))
    entries = (
        data.get("props", {}).get("pageProps", {}).get("deposit", {})
        .get("interestRateTable", {}).get("interestRates", [])
    )
    rows_out: list[dict] = []
    for e in entries:
        # currencyId 1 = TL; skip FX/gold variants (out of scope this pass).
        if e.get("currencyId") not in (1, None):
            continue
        name = e.get("bankName")
        if not name:
            continue
        rows_out.append(_row(
            source="hangikredi", rate_type="deposit_tl", raw_bank_name=name,
            bank_ticker=resolve_ticker(name), product_name="", currency="TRY",
            rate_min=e.get("minimumRate"), rate_max=e.get("maximumRate"),
            rate_basis="annual", term_min=e.get("minimumMaturity"),
            term_max=e.get("maximumMaturity"), term_unit="days",
            amount_min=e.get("minimumAmount"), amount_max=e.get("maximumAmount"),
            source_url=url,
        ))
    return rows_out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def collect_rows() -> tuple[list[dict], dict[str, int]]:
    """Fetch every source; return (rows, per-source counts; -1 on error)."""
    rows: list[dict] = []
    counts: dict[str, int] = {}

    try:
        dep = parse_hangikredi_deposits(_get(HANGIKREDI_DEPOSIT), HANGIKREDI_DEPOSIT)
        rows += dep
        counts["deposit_tl"] = len(dep)
    except Exception as ex:  # noqa: BLE001 — one bad source must not kill the run
        counts["deposit_tl"] = -1
        print(f"  [err] deposit_tl  {type(ex).__name__}: {ex}")
    time.sleep(1.0)

    for url, rate_type in DOVIZ_LOANS:
        try:
            lo = parse_doviz_loans(_get(url), url, rate_type)
            rows += lo
            counts[rate_type] = len(lo)
        except Exception as ex:  # noqa: BLE001
            counts[rate_type] = -1
            print(f"  [err] {rate_type}  {type(ex).__name__}: {ex}")
        time.sleep(1.0)

    return rows, counts


def update_all(db: Path = DB) -> dict[str, int]:
    """Scrape every source and upsert into bank_advertised_rates."""
    rows, counts = collect_rows()

    now = datetime.now()
    snap = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        r["snapshot_date"] = snap
        r["downloaded_at"] = ts

    conn = sqlite3.connect(str(db))
    try:
        init_schema(conn)
        placeholders = ",".join("?" * len(COLUMNS))
        conn.executemany(
            f"INSERT OR REPLACE INTO bank_advertised_rates ({','.join(COLUMNS)}) "
            f"VALUES ({placeholders})",
            [tuple(r[c] for c in COLUMNS) for r in rows],
        )
        conn.commit()
    finally:
        conn.close()

    resolved = sum(1 for r in rows if r["bank_ticker"])
    # Names we knowingly leave NULL (non-audited banks/fintechs) are expected —
    # only surface the ones that are genuinely unmapped, i.e. worth an alias.
    unmapped = sorted({
        r["raw_bank_name"] for r in rows
        if not r["bank_ticker"] and not _is_expected_null(r["raw_bank_name"])
    })
    for rate_type, n in counts.items():
        tag = "ok " if n >= 0 else "err"
        print(f"  [{tag}] {rate_type:14} → {n} rows")
    print(f"\n{len(rows)} rows · {resolved} resolved to a ticker "
          f"· {len(rows) - resolved} left NULL on {snap}")
    if unmapped:
        print(f"  [warn] unmapped bank names (add to EXTRA_ALIASES?): {unmapped}")
    return counts


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB
    update_all(db_path)
