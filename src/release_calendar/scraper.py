"""Scrape TCMB's published release calendar → release_calendar.

TCMB publishes a "Monetary Policy Committee Meeting and Reports Calendar" as one
HTML <table> with four columns — MPC Decision · Summary of the MPC Meeting
(minutes) · Inflation Report · Financial Stability Report — each cell a date in
"Month D, YYYY" form. The table is injected by the WCM portal's JS, but the full
markup is served to any request that sends browser-like headers (a bare UA gets a
date-less page), so requests + lxml parse it — no JS/browser, so it runs under
CI's minimal deps and in a plain Actions runner, exactly like the news lane which
already scrapes www.tcmb.gov.tr.

This retires the hand-transcribed MPC_DATES in web/app/lib/ahead.ts: the four
event kinds flow into D1 and the "Ahead" strips read them. MPC_DATES stays only
as the render-time fallback, still guarded by scripts/check_calendar_fresh.py.

Run: python -m src.release_calendar.scraper [db_path]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import requests
from lxml import html as lh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.release_calendar.schema import init_schema  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "bddk_data.db"

SOURCE = "tcmb"
URL = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/"
    "Announcements/Calendar"
)
# A bare UA returns the WCM shell WITHOUT the calendar table; these three headers
# make the server render the full page. (Verified 2026-07-15.)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30

# The four table columns, in order, → (kind, display title). A column whose cell
# is blank for a given row simply yields no event.
COLUMNS = [
    ("mpc_decision", "Monetary Policy Committee Decision"),
    ("mpc_minutes", "Summary of the MPC Meeting"),
    ("inflation_report", "Inflation Report"),
    ("financial_stability_report", "Financial Stability Report"),
]

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})")

DB_COLUMNS = ["source", "kind", "event_date", "title", "source_url", "downloaded_at"]


# --------------------------------------------------------------------------- #
# Parsing (pure — unit-tested without network)
# --------------------------------------------------------------------------- #
def parse_date(cell: str) -> str | None:
    """'January 22, 2026' → '2026-01-22'. Blank / non-date → None."""
    m = _DATE_RE.search(cell or "")
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"


def parse_calendar(html_text: str, source_url: str = URL) -> list[dict]:
    """Parse TCMB's calendar HTML → event rows (no `downloaded_at`; the DB fills it).

    Finds the one table whose header names the MPC, then reads each data row's
    four cells left-to-right against COLUMNS. Deterministic; returns [] if the
    table is absent (a scrape that got the date-less shell), so the caller can
    fail loudly rather than wipe good rows.
    """
    doc = lh.fromstring(html_text)
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for table in doc.xpath("//table"):
        rows = table.xpath(".//tr")
        if not rows:
            continue
        header = " ".join(rows[0].text_content().split())
        if "Monetary Policy Committee" not in header:
            continue
        for row in rows[1:]:
            cells = row.xpath("./td")
            for idx, (kind, title) in enumerate(COLUMNS):
                if idx >= len(cells):
                    continue
                iso = parse_date(cells[idx].text_content())
                if not iso or (kind, iso) in seen:
                    continue
                seen.add((kind, iso))
                events.append(
                    {"source": SOURCE, "kind": kind, "event_date": iso,
                     "title": title, "source_url": source_url}
                )
    events.sort(key=lambda e: (e["event_date"], e["kind"]))
    return events


# --------------------------------------------------------------------------- #
# Fetch + write
# --------------------------------------------------------------------------- #
def fetch(url: str = URL) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def write_db(conn: sqlite3.Connection, events: list[dict]) -> int:
    init_schema(conn)
    placeholders = ",".join(["?"] * len(DB_COLUMNS))
    # `downloaded_at` is omitted from the row dicts, so it takes the table's
    # CURRENT_TIMESTAMP default — which push_to_d1.py filters on.
    cols = [c for c in DB_COLUMNS if c != "downloaded_at"]
    conn.executemany(
        f"INSERT OR REPLACE INTO release_calendar ({','.join(cols)}) "
        f"VALUES ({','.join(['?'] * len(cols))})",
        [tuple(e[c] for c in cols) for e in events],
    )
    conn.commit()
    return len(events)


def main(db_path: str | None = None) -> int:
    events = parse_calendar(fetch())
    if not events:
        print("release_calendar: no events parsed — TCMB page shape changed?", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(db_path or DB))
    try:
        n = write_db(conn, events)
    finally:
        conn.close()
    by_kind: dict[str, int] = {}
    for e in events:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
    print(f"release_calendar: wrote {n} events — " + ", ".join(f"{k}:{v}" for k, v in sorted(by_kind.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
