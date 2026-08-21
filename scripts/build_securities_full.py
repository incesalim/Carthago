#!/usr/bin/env python
"""The securities graduation: the fourth NOTES-section family minted from the
document layer — BRSA's securities breakdown by instrument and listing (debt
securities / investment funds / share certificates, each quoted and unquoted;
impairment; total) x (current, prior), 381 captured tables across 18 banks.

The template prints once per measurement portfolio — fair value through
profit or loss, through other comprehensive income, amortised cost — so each
instance carries a `portfolio` context read off its block heading (and the
raw heading, for the ones the regexes cannot place).

Rows carry (group_role, item_role) because "quoted on a stock exchange"
repeats under every group. The mint gate is the template's arithmetic: each
group = quoted + unquoted where both print, and total = Σ groups -
impairment, checked on the current column. No narrow lane holds any of this.

`--write` stores into bank_audit_securities_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

GROUPS: list[tuple[str, re.Pattern]] = [
    ("debt_securities", re.compile(r"^BORCLANMA SENETLERI|^DEBT (SECURITIES|INSTRUMENTS)")),
    ("investment_funds", re.compile(r"^YATIRIM FON|^INVESTMENT FUND|^MUTUAL FUND")),
    ("share_certificates", re.compile(r"^HISSE SENETLERI|^SHARE CERTIFICATES|^COMMON SHARES|"
                                      r"^EQUITY (SECURITIES|SHARES|INSTRUMENTS)|^SHARES$")),
]
ITEMS: list[tuple[str, re.Pattern]] = [
    ("quoted", re.compile(r"^BORSADA ISLEM GOREN|^QUOTED|^LISTED")),
    ("unquoted", re.compile(r"^BORSADA ISLEM GORMEYEN|^UNQUOTED|^UNLISTED|^NOT (QUOTED|LISTED)")),
]
_IMPAIR = re.compile(r"^DEGER AZALMA|^DEGER DUSUS|^IMPAIRMENT|^PROVISION FOR IMPAIRMENT|"
                     r"^EXPECTED (CREDIT )?LOSS|^DEGER ARTIS|^VALUE INCREASE")
# GARAN prints a signed "Value Increase/Impairment Loss" that ADDS; HAYATK
# prints its impairment already negative. The sign convention is read off the
# label and the value: a "(-)" deduction label with a positive figure is
# subtracted, anything else is applied as printed.
_DEDUCTION_LABEL = re.compile(r"\(-\)|AZALMA|DUSUS|IMPAIRMENT|PROVISION")
_VALUATION_LABEL = re.compile(r"DEGER ARTIS|VALUE INCREASE")
_TOTAL = re.compile(r"^TOPLAM|^TOTAL")
VALUES = ("current", "prior")
_PORTFOLIO = [
    ("fvtpl", re.compile(r"KAR.?ZARARA YANSITILAN|THROUGH PROFIT|TRADING|ALIM SATIM")),
    ("fvoci", re.compile(r"DIGER KAPSAMLI|OTHER COMPREHENSIVE|AVAILABLE.?FOR.?SALE|SATILMAYA HAZIR")),
    ("amortised_cost", re.compile(r"ITFA EDILMIS|AMORTI[SZ]ED COST|HELD.?TO.?MATURITY|VADEYE KADAR")),
]


def portfolio_of(heading: str | None, item_title: str | None) -> str:
    h = fold(heading) + " " + fold(item_title)
    for name, rx in _PORTFOLIO:
        if rx.search(h):
            return name
    return "unknown"


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_securities_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    -- fvtpl / fvoci / amortised_cost / unknown, read off the block heading
    -- (kept alongside) and its contents item.
    portfolio    TEXT NOT NULL,
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    group_role   TEXT,
    item_role    TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    current      REAL,
    prior        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_securities_full_ctx
  ON bank_audit_securities_full(portfolio, group_role, item_role);
"""


def _sec_role(label: str) -> str | None:
    f = fold(label).strip()
    for name, rx in GROUPS + ITEMS:
        if rx.search(f):
            return name
    if _IMPAIR.search(f):
        return "impairment"
    if _TOTAL.search(f):
        return "total"
    return None


def _is_family(grid: list[dict]) -> bool:
    if not 4 <= len(grid) <= 14:
        return False
    first = fold(grid[0]["label"] or "").strip()
    return any(rx.search(first) for _g, rx in GROUPS[:1]) and any(
        _TOTAL.search(fold(r["label"] or "").strip()) for r in grid)


def _rows_of(grid: list[dict], pg: int, bid: int, factor) -> list[dict]:
    rows, group = [], None
    for r in grid:
        label = (r["label"] or "").strip()
        if not label:
            continue
        f = fold(label)
        g = next((name for name, rx in GROUPS if rx.search(f)), None)
        item = None
        if g:
            group = g
            item_role = "group"
        elif _IMPAIR.search(f):
            group = None
            item_role = "valuation" if _VALUATION_LABEL.search(f) else "impairment"
        elif _TOTAL.search(f):
            group, item_role = None, "total"
        else:
            item = next((name for name, rx in ITEMS if rx.search(f)), None)
            item_role = item
        vals = [num(c) for c in r["cells"][-2:]]
        vals = [None] * (2 - len(vals)) + vals
        if factor is not None:
            vals = [U.scale_amount(v, factor) for v in vals]
        row = {"label": label, "group_role": group if item_role in ("group", "quoted", "unquoted") else None,
               "item_role": item_role, "page": pg, "block_id": bid}
        row.update(zip(VALUES, vals))
        rows.append(row)
    return rows


def _identity_holds(inst: list[dict]) -> bool:
    heads = {}
    children: dict[str, list] = {}
    adjust = 0.0
    total = None
    for x in inst:
        if x["item_role"] == "group":
            heads[x["group_role"]] = x["current"]
        elif x["item_role"] in ("quoted", "unquoted") and x["group_role"]:
            children.setdefault(x["group_role"], []).append(x["current"])
        elif x["item_role"] in ("impairment", "valuation") and x["current"] is not None:
            v = x["current"]
            lab = fold(x["label"])
            if x["item_role"] == "impairment" and v > 0 and _DEDUCTION_LABEL.search(lab):
                adjust -= v                  # "(-)" label, positive figure
            else:
                adjust += v                  # already signed, or a valuation
        elif x["item_role"] == "total":
            total = x["current"]
    if total is None or not heads:
        return False
    for g, head in heads.items():
        kids = [v for v in children.get(g, []) if v is not None]
        if head is not None and len(children.get(g, [])) >= 2 and kids \
                and abs(sum(kids) - head) > max(2.0, 1e-5 * abs(head)):
            return False
    # a group head printed "-" (or not at all) contributes its children instead
    expect = 0.0
    for g in set(heads) | set(children):
        head = heads.get(g)
        kids = [v for v in children.get(g, []) if v is not None]
        expect += head if head is not None else sum(kids)
    expect += adjust
    return abs(expect - total) <= max(2.0, 1e-5 * abs(total))


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, item_title, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = [(pg, bid, h, it, grid, unit)
             for pg, bid, h, it, g, unit in blocks
             if _is_family(grid := absorb_inline(json.loads(g), _sec_role))]
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    return {"unit": unit, "instances": [
        {"portfolio": portfolio_of(h, it), "heading": h,
         "rows": _rows_of(grid, pg, bid, factor)}
        for pg, bid, h, it, grid, _u in found]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    out = None
    if args.write:
        out = sqlite3.connect(args.tables_db)
        out.executescript(DDL)

    where, params = [], []
    for col, val in (("bank_ticker", args.bank), ("period", args.period),
                     ("kind", args.kind)):
        if val:
            where.append(f"{col}=?")
            params.append(val.upper() if col != "kind" else val)
    keys = [tuple(r) for r in tab.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_document_tables"
        + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY 1,2,3",
        params)]

    detected = written = gated = 0
    per_filing: Counter = Counter()
    portfolios: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = [i for i in got["instances"] if _identity_holds(i["rows"])]
        gated += len(got["instances"]) - len(kept)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        for i in kept:
            portfolios[i["portfolio"]] += 1
        if args.verbose:
            print(f"{' '.join(key)}: {[i['portfolio'] for i in kept]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_securities_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for n, i in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_securities_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, i["portfolio"], i["heading"], k, x["label"],
                      x["group_role"], x["item_role"], x["current"], x["prior"],
                      x["page"], x["block_id"], got["unit"])
                     for k, x in enumerate(i["rows"])])
                written += len(i["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by the identities: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
        print(f"portfolios: {dict(portfolios.most_common())}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_securities_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
