"""TCMB's card-rate caps → `tcmb_card_rate_caps`.

The central bank sets the maximum interest that may be charged on credit-card
and overdraft-account transactions: a reference rate, a contractual rate and a
late-payment rate for each statement-debt band in lira, the same two for cash
withdrawals, and a contractual and a late-payment rate in foreign currency.
It publishes them as one HTML table, one row per month they have been in
force, at

    https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/
        Bankacilik+Verileri/Kredi_Karti_Islemlerinde_Uygulanacak_Azami_Faiz_Oranlari

so every change of the caps is a dated event with the regulator as its source.
The page serves the current year's rows (measured 2026-11-27: twelve rows,
1/1/2026 … 1/12/2026; the December row changed the reference rate from 3.11
to 2.94).

Two things are data rather than schema:

- the debt-band thresholds, read from the header cells and stored on each row
  (`tier_floor_tl`, `tier_ceiling_tl`). TCMB moved them from 25,000 to 30,000
  TL, and a column named for a threshold would have gone wrong silently.
- which column is which. The data rows are mapped positionally and the row
  width is asserted: if TCMB adds or removes a column, this raises instead of
  assigning a rate to the wrong kind.

A cell TCMB leaves blank is stored as NULL, never as 0.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

import requests
from lxml import html as lh

URL = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/"
    "Bankacilik+Verileri/Kredi_Karti_Islemlerinde_Uygulanacak_Azami_Faiz_Oranlari"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 40

# The cells of a data row after the date, in the order TCMB prints them.
CELLS: tuple[tuple[str, str, str], ...] = (
    ("TL", "statement_under", "contractual"),
    ("TL", "statement_under", "late_payment"),
    ("TL", "statement_mid", "contractual"),
    ("TL", "statement_mid", "late_payment"),
    ("TL", "statement_over", "contractual"),
    ("TL", "statement_over", "late_payment"),
    ("TL", "cash_withdrawal", "contractual"),
    ("TL", "cash_withdrawal", "late_payment"),
    ("FX", "all", "contractual"),
    ("FX", "all", "late_payment"),
)
ROW_WIDTH = 2 + len(CELLS)          # date + reference rate + the ten above

_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_NUMBER = r"(\d{1,3}(?:\.\d{3})*)"
_UNDER = re.compile(_NUMBER + r"\s*TL\s+alt[ıi]nda", re.I)
_BETWEEN = re.compile(_NUMBER + r"\s*-\s*" + _NUMBER + r"\s*TL\s+aras[ıi]nda", re.I)
_OVER = re.compile(_NUMBER + r"\s*TL\s+[üu]zerinde", re.I)

_COLS = ("period_date", "currency", "tier", "rate_kind", "rate", "tier_floor_tl", "tier_ceiling_tl")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _number(text: str) -> float:
    """Turkish notation: `3,25` is 3.25 and `30.000` is thirty thousand."""
    return float(text.strip().replace(".", "").replace(",", "."))


def _percent(text: str) -> float | None:
    text = text.replace("\xa0", " ").strip()
    return _number(text) if re.fullmatch(r"\d{1,2},\d+", text) else None


def _thresholds(header_text: str) -> dict[str, tuple[float | None, float | None]]:
    """The statement-debt bands as TCMB words them, in lira."""
    under, between, over = _UNDER.search(header_text), _BETWEEN.search(header_text), _OVER.search(header_text)
    return {
        "statement_under": (None, _number(under.group(1)) if under else None),
        "statement_mid": ((_number(between.group(1)), _number(between.group(2))) if between else (None, None)),
        "statement_over": (_number(over.group(1)) if over else None, None),
    }


def parse_table(page_html: str) -> list[dict]:
    """One row per (date × currency × tier × rate kind); empty if there is no table."""
    root = lh.fromstring(page_html)
    for table in root.xpath("//table"):
        rows = [[re.sub(r"\s+", " ", cell.text_content()).replace("\xa0", " ").strip()
                 for cell in tr.xpath("./th|./td")]
                for tr in table.xpath(".//tr")]
        data_rows = [r for r in rows if r and _DATE.match(r[0])]
        if data_rows:
            break
    else:
        return []                       # no table carries dated rows (yet)
    header_text = " ".join(" ".join(r) for r in rows[: rows.index(data_rows[0])])
    bands = _thresholds(header_text)

    out: list[dict] = []
    for r in data_rows:
        if len(r) != ROW_WIDTH:
            raise ValueError(
                f"TCMB card-rate table has {len(r)} cells on {r[0]}; expected {ROW_WIDTH}. "
                "The columns were reassigned — read the page before mapping them again.")
        m = _DATE.match(r[0])
        period = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()   # type: ignore[union-attr]
        out.append({"period_date": period, "currency": "TL", "tier": "all", "rate_kind": "reference",
                    "rate": _percent(r[1]), "tier_floor_tl": None, "tier_ceiling_tl": None})
        for value, (currency, tier, kind) in zip(r[2:], CELLS):
            floor, ceiling = bands.get(tier, (None, None))
            out.append({"period_date": period, "currency": currency, "tier": tier, "rate_kind": kind,
                        "rate": _percent(value), "tier_floor_tl": floor, "tier_ceiling_tl": ceiling})
    return out


def changed_rates(rows: list[dict]) -> list[tuple[str, str, str, str, float | None]]:
    """The cap changes themselves, oldest first.

    The page lists a row per month whether or not anything moved. This reduces
    it to the months in which a rate differs from the month before, one entry
    per (date, currency, tier, rate kind) that moved."""
    by_date: dict[str, dict[tuple[str, str, str], float | None]] = {}
    for row in rows:
        by_date.setdefault(row["period_date"], {})[(row["currency"], row["tier"], row["rate_kind"])] = row["rate"]
    dates = sorted(by_date)
    out = []
    for earlier, later in zip(dates, dates[1:]):
        for key, rate in by_date[later].items():
            if rate != by_date[earlier].get(key):
                out.append((later, *key, rate))
    return out


# ---------------------------------------------------------------------------
# Network + storage
# ---------------------------------------------------------------------------
def fetch_rows(session: requests.Session) -> list[dict]:
    r = session.get(URL, timeout=TIMEOUT)
    r.raise_for_status()
    return parse_table(r.content.decode("utf-8", errors="replace"))


def store_rows(conn: sqlite3.Connection, rows: list[dict]) -> dict[str, int]:
    """'new' / 'changed' / 'same'. Unchanged rows keep their `downloaded_at`,
    so a monthly re-read of an unchanged table writes nothing."""
    counts = {"new": 0, "changed": 0, "same": 0}
    for row in rows:
        cur = conn.execute(
            "SELECT rate, tier_floor_tl, tier_ceiling_tl FROM tcmb_card_rate_caps "
            "WHERE period_date = ? AND currency = ? AND tier = ? AND rate_kind = ?",
            (row["period_date"], row["currency"], row["tier"], row["rate_kind"]))
        held = cur.fetchone()
        values = (row["rate"], row["tier_floor_tl"], row["tier_ceiling_tl"])
        if held is None:
            conn.execute(f"INSERT INTO tcmb_card_rate_caps ({', '.join(_COLS)}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (row["period_date"], row["currency"], row["tier"], row["rate_kind"]) + values)
            counts["new"] += 1
        elif tuple(held) != values:
            conn.execute("UPDATE tcmb_card_rate_caps SET rate = ?, tier_floor_tl = ?, tier_ceiling_tl = ?, "
                         "downloaded_at = CURRENT_TIMESTAMP WHERE period_date = ? AND currency = ? "
                         "AND tier = ? AND rate_kind = ?", values + (row["period_date"], row["currency"], row["tier"], row["rate_kind"]))
            counts["changed"] += 1
        else:
            counts["same"] += 1
    return counts
