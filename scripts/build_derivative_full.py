#!/usr/bin/env python
"""The derivatives graduation: the third NOTES-section family minted from the
document layer — BRSA's derivative breakdown by instrument (forwards, swaps,
futures, options, other, total) x (current TL, current FC, prior TL, prior
FC), 393 captured tables across 14 banks.

The same six-row template prints SEVERAL times per filing — for derivative
assets and liabilities held for trading, and for hedging — so every stored
instance carries its `context`, read off the block's own heading and the
contents item it sits under ('assets' / 'liabilities', with 'hedging_'
prefixed where the heading says so), plus the raw heading for the cases the
regexes cannot classify.

The mint gate is the template's arithmetic: total = forwards + swaps +
futures + options + other, checked on every column that prints a total; an
instance is stored only if no column fails. No narrow lane holds any of this.

`--write` stores into bank_audit_derivative_full in data/bank_audit_tables.db
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

ROLES: list[tuple[str, re.Pattern]] = [
    ("forward", re.compile(r"^VADELI (ISLEM|DOVIZ)|^FORWARD")),
    ("swap", re.compile(r"^SWAP")),
    ("futures", re.compile(r"^FUTURES|^FUTURE ")),
    ("options", re.compile(r"^OPSIYON|^OPTION")),
    ("other", re.compile(r"^DIGER|^OTHER")),
    ("total", re.compile(r"^TOPLAM|^TOTAL")),
]
COMPONENTS = ("forward", "swap", "futures", "options", "other")
VALUES = ("current_tl", "current_fc", "prior_tl", "prior_fc")
_HEDGE = re.compile(r"RISKTEN KORUNMA|HEDG")
_ASSET = re.compile(r"VARLIK|ASSET|POZITIF|POSITIVE|AKTIF")
_LIAB = re.compile(r"YUKUMLULUK|BORC|LIABILIT|NEGATIF|NEGATIVE|PASIF")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


def context_of(heading: str | None, item_title: str | None) -> str:
    h, i = fold(heading), fold(item_title)
    side = ("assets" if _ASSET.search(h) else "liabilities" if _LIAB.search(h)
            else "assets" if _ASSET.search(i) else "liabilities" if _LIAB.search(i)
            else "unknown")
    return ("hedging_" if _HEDGE.search(h) else "") + side


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_derivative_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    -- which of the filing's derivative tables this is: assets / liabilities,
    -- hedging_assets / hedging_liabilities, or unknown — read off the block's
    -- heading and its contents item, both kept alongside.
    context      TEXT NOT NULL,
    heading      TEXT,
    item_title   TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    current_tl   REAL,
    current_fc   REAL,
    prior_tl     REAL,
    prior_fc     REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_derivative_full_ctx
  ON bank_audit_derivative_full(context, row_role);
"""


_TITLE = re.compile(r"TUREV|DERIVATIVE")


def _normalise(grid: list[dict]) -> list[dict]:
    """The grid from its first instrument row on: the period / "TP YP"
    header rows the capture puts above it (AKBNK, HSBC, ICBCT, ISCTR,
    KLNMA...) are dropped. Where the first instrument row is the swap, the
    forward row's figures may have been glued onto the note title above the
    header lines (QNBFB, ZIRAAT: "2.2 Positive differences related to
    derivative..." carrying the forward's four figures) — that row comes
    back as the forward."""
    first = next((i for i, r in enumerate(grid) if role_of(r["label"] or "") in ("forward", "swap")), None)
    if first is None:
        return grid
    if role_of(grid[first]["label"] or "") == "swap":
        j = first - 1
        while j >= 0 and not any(num(c) is not None for c in grid[j]["cells"]):
            j -= 1
        if j >= 0 and _TITLE.search(fold(grid[j]["label"] or "")) and role_of(grid[j]["label"] or "") is None:
            return [{**grid[j], "label": "Vadeli İşlemler"}] + grid[first:]
    return grid[first:]


def _is_family(grid: list[dict]) -> bool:
    if not 5 <= len(grid) <= 8:
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    # the template always has a swap row; BURGAN's "Forward foreign exchange
    # commitments ... Total" is the commitments note, not this
    return roles[0] in ("forward", "swap") and "swap" in roles and "total" in roles \
        and roles.count("total") == 1


def _identity_holds(inst: list[dict]) -> bool:
    by: dict = {}
    for x in inst:
        by.setdefault(x["role"], x)
    tot = by.get("total")
    if not tot:
        return False
    checked = 0
    for col in VALUES:
        t = tot[col]
        if t is None:
            continue
        s = sum((by[c][col] or 0.0) for c in COMPONENTS if c in by)
        if abs(s - t) > max(2.0, 1e-5 * abs(t)):
            return False
        checked += 1
    return checked >= 1


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, item_title, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = [(pg, bid, h, it, grid, unit)
             for pg, bid, h, it, g, unit in blocks
             if _is_family(grid := _normalise(absorb_inline(
                 json.loads(g), role_of, keep=lambda lab: role_of(lab) in COMPONENTS)))]   # ISCTR: a valueless "Futures"
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, heading, item_title, grid, _u in found:
        rows = []
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            vals = [num(c) for c in r["cells"][-4:]]
            vals = [None] * (4 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": label, "role": role_of(label), "page": pg,
                   "block_id": bid}
            row.update(zip(VALUES, vals))
            rows.append(row)
        instances.append({"context": context_of(heading, item_title),
                          "heading": heading, "item_title": item_title,
                          "rows": rows})
    return {"unit": unit, "instances": instances}


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
    contexts: Counter = Counter()
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
            contexts[i["context"]] += 1
        if args.verbose:
            print(f"{' '.join(key)}: {[i['context'] for i in kept]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_derivative_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for n, i in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_derivative_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, i["context"], i["heading"], i["item_title"], k,
                      x["label"], x["role"], *(x[v] for v in VALUES), x["page"],
                      x["block_id"], got["unit"]) for k, x in enumerate(i["rows"])])
                written += len(i["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by total = Σ instruments: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
        print(f"contexts: {dict(contexts.most_common())}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_derivative_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
