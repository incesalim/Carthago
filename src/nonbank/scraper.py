"""BDDK non-bank financial-sector bulletin scraper (BultenAylikBdmk).

Sibling of the banking bulletin (``src/scrapers/bddk_api_scraper.py``), but the
non-bank ``<Sector>BasitRaporGetir`` endpoints return a **server-rendered HTML
page** (the banking one returns JSON). We parse the ``#TabloBasitGosterim``
balance-sheet table — 5 columns: ``Sıra | Kalem | TP | YP | Toplam`` — whose
values are in **Million TL**, Turkish-formatted ('.' thousands, ',' decimal).

Flow per (sector, period): GET the sector page to capture the anti-forgery
token + session cookie, then POST ``<Sector>BasitRaporGetir`` with
``tabloNo=1, yil, ay, paraBirimi=TL``. The returned page carries a
``Dönem: YYYY/MM`` header we check against the requested period so we never
store an unpublished month's stale fallback.
"""
from __future__ import annotations

import re
import sqlite3
import time

import lxml.html as LH

from src.nonbank.schema import init_schema
from src.scrapers._http import bddk_session

BASE = "https://www.bddk.org.tr/BultenAylikBdmk/tr/Gosterim"
BALANCE_SHEET_TABLO = "1"

# The three credit-substitution sectors BDDK machine-serves cleanly via this
# bulletin (monthly balance sheets, 2008→, validated against FKB sector totals).
# These ARE the "share of banking" story (they compete with bank lending).
ACTIVE_SECTORS = [
    {"code": "leasing",   "stem": "FinansalKiralama",    "cadence": "monthly", "start_year": 2008},
    {"code": "factoring", "stem": "Faktoring",           "cadence": "monthly", "start_year": 2008},
    {"code": "financing", "stem": "FinansmanSirketleri", "cadence": "monthly", "start_year": 2008},
]

# Deferred (Phase 3). VYŞ asset-management is a COMPLEMENT (buys NPLs from banks),
# not a lending substitute — and its bulletin feed is sparse/variant: the period
# POST returns zero-filled empty templates for most quarters while the real
# current data (a different ~53-line chart of accounts) only renders via the
# default GET. Savings-finance (Tasarruf Finansman) isn't in this bulletin at all
# (FKB-aggregate fallback). Both are kept out of the default scrape set.
DEFERRED_SECTORS = [
    {"code": "amc",       "stem": "VYS",                 "cadence": "quarterly", "start_year": 2020},
]

SECTORS = ACTIVE_SECTORS                       # default scrape set
ALL_SECTORS = ACTIVE_SECTORS + DEFERRED_SECTORS
SECTORS_BY_CODE = {s["code"]: s for s in ALL_SECTORS}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
# Applied to the report header cell text ('… Dönem: YYYY/MM, Birim: Milyon TL'),
# whose only YYYY/MM token is the rendered period.
_PERIOD_RE = re.compile(r"(\d{4})\s*/\s*(\d{1,2})")
_ROMAN_RE = re.compile(r"^[IVXLCDM]+\.")


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def _num(s: str | None) -> float | None:
    """Parse a Turkish-formatted number ('.' thousands, ',' decimal) to float.

    BDDK balance-sheet cells are integer Millions TL with grouping dots
    (e.g. '346.916' → 346916.0). Nil markers ('-', '--', '') → None.
    """
    s = (s or "").strip()
    if s in ("", "-", "--", ".", "—", "–"):
        return None
    neg = s.startswith("-")
    s = s.lstrip("-").strip().replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _is_subtotal(name: str) -> bool:
    n = name.strip()
    return bool(_ROMAN_RE.match(n)) or "TOPLAM" in n.upper()


def parse_report(html: str) -> tuple[tuple[int, int] | None, list[dict]]:
    """Parse the #TabloBasitGosterim balance-sheet table once.

    Returns (rendered_period, rows). The period is read from the table's header
    row, whose merged text is 'Kalem Dönem: YYYY/MM, Birim: Milyon TL' — the raw
    HTML stores 'Dönem' as the entity ``D&#246;nem`` and splits it from the date
    across tags, so a string regex on the markup can't bridge them; the DOM
    text_content does.
    """
    doc = LH.fromstring(html)
    tables = doc.xpath("//table[@id='TabloBasitGosterim']")
    if not tables:
        return None, []
    trs = tables[0].xpath(".//tr")

    period = None
    if trs:
        m = _PERIOD_RE.search(trs[0].text_content())
        if m:
            period = (int(m.group(1)), int(m.group(2)))

    rows: list[dict] = []
    for tr in trs:
        cells = [(c.text_content() or "").strip() for c in tr.xpath("./td|./th")]
        if len(cells) < 5:
            continue
        sira = cells[0].strip()
        if not sira.isdigit():  # header row ('Sıra')
            continue
        name = re.sub(r"\s+", " ", cells[1]).strip()
        rows.append({
            "item_order": int(sira),
            "item_name": name,
            "is_subtotal": 1 if _is_subtotal(name) else 0,
            "amount_tp": _num(cells[2]),
            "amount_yp": _num(cells[3]),
            "amount_total": _num(cells[4]),
        })
    return period, rows


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #
def new_session():
    s = bddk_session()
    s.headers.update(HEADERS)
    return s


def get_token(session, stem: str) -> str | None:
    """GET the sector page to capture the anti-forgery token (+ session cookie)."""
    r = session.get(f"{BASE}/{stem}", timeout=30)
    r.raise_for_status()
    m = _TOKEN_RE.search(r.text)
    return m.group(1) if m else None


def fetch_period(session, stem: str, year: int, month: int,
                 token: str) -> tuple[tuple[int, int] | None, list[dict]]:
    """POST one (sector, period). Returns (rendered_period, rows)."""
    r = session.post(
        f"{BASE}/{stem}BasitRaporGetir",
        data={
            "__RequestVerificationToken": token,
            "tabloNo": BALANCE_SHEET_TABLO,
            "yil": str(year),
            "ay": str(month),
            "paraBirimi": "TL",
        },
        timeout=30,
    )
    r.raise_for_status()
    r.encoding = "utf-8"
    return parse_report(r.text)


def save_rows(conn: sqlite3.Connection, sector_code: str, year: int, month: int,
              rows: list[dict], source: str = "bddk") -> int:
    conn.executemany(
        "INSERT OR REPLACE INTO nonbank_balance_sheet "
        "(sector_code, year, month, item_order, item_name, is_subtotal, "
        " amount_tp, amount_yp, amount_total, source, downloaded_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        [(sector_code, year, month, r["item_order"], r["item_name"], r["is_subtotal"],
          r["amount_tp"], r["amount_yp"], r["amount_total"], source) for r in rows],
    )
    conn.commit()
    return len(rows)


def is_quarter(month: int) -> bool:
    return month in (3, 6, 9, 12)


def _assets_total(rows: list[dict]) -> float | None:
    """The 'VARLIK TOPLAMI' (balance-sheet assets total), the report's anchor."""
    for r in rows:
        if (r["item_name"] or "").strip().upper().startswith("VARLIK TOPLAM"):
            return r["amount_total"]
    return None


def is_real_report(rows: list[dict]) -> bool:
    """Guard against zero-filled empty templates (BDDK returns these for periods
    a sector hasn't published): a real balance sheet has a positive assets total."""
    at = _assets_total(rows)
    return at is not None and at > 0


def scrape_sector(conn: sqlite3.Connection, sector: dict,
                  periods: list[tuple[int, int]], session=None,
                  sleep: float = 0.5, stop_when_unpublished: bool = False) -> int:
    """Scrape a sector across `periods` (ascending). Stores rows whose rendered
    period matches the request. If `stop_when_unpublished`, breaks at the first
    not-yet-published month (used by incremental, where months are sequential)."""
    session = session or new_session()
    token = get_token(session, sector["stem"])
    if not token:
        print(f"  [{sector['code']}] could not obtain token — skipping", flush=True)
        return 0

    total = 0
    for (y, m) in periods:
        if sector["cadence"] == "quarterly" and not is_quarter(m):
            continue
        try:
            period, rows = fetch_period(session, sector["stem"], y, m, token)
            if not rows:  # token may have rotated — refresh once and retry
                token = get_token(session, sector["stem"])
                period, rows = fetch_period(session, sector["stem"], y, m, token)
        except Exception as e:  # noqa: BLE001 — one bad period must not abort the run
            print(f"  [{sector['code']}] {y}-{m:02d} error: {e}", flush=True)
            continue

        if rows and period == (y, m) and is_real_report(rows):
            n = save_rows(conn, sector["code"], y, m, rows)
            total += n
            print(f"  [{sector['code']}] {y}-{m:02d}: {n} rows", flush=True)
        else:
            if period != (y, m):
                why = "not published yet"
            elif not rows:
                why = "no rows"
            else:
                why = "empty template (zero assets)"
            print(f"  [{sector['code']}] {y}-{m:02d}: {why} (got {period})", flush=True)
            if stop_when_unpublished:
                break
        time.sleep(sleep)
    return total


def open_db(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    return conn
