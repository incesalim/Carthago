#!/usr/bin/env python
"""The consumer-loans graduation: the second NOTES-section family minted from
the document layer — BRSA's "consumer loans, retail credit cards and
personnel loans by maturity" note (Section 5), ~45 rows x 3 columns
(short-term, medium/long-term, total), current + prior instances.

Rows carry two roles because item labels repeat under each group: `group`
(consumer loans TL / FC-indexed / FC, retail credit cards TL / FC, personnel
loans, personnel credit cards, overdraft accounts) and `item` (housing,
vehicle, general-purpose, other, instalment, non-instalment). The label is
kept verbatim besides.

The mint gate needs no registry at all: every row prints total = short +
long, so an instance is stored only if that identity holds on at least 90%
of its value-bearing rows AND on its grand total. No narrow lane holds any of
this.

`--write` stores into bank_audit_consumer_loan_full in
data/bank_audit_tables.db (local only; never the audit snapshot, not D1).
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
from src.audit_reports.numbered_template import fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

_FIRST = re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(TP|TL)")
_TOTAL = re.compile(r"^TOPLAM$|^TOTAL$")
GROUPS: list[tuple[str, re.Pattern]] = [
    ("consumer_fc_indexed", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(DOVIZE ENDEKSLI|FC.?INDEXED|FX.?INDEXED)")),
    ("consumer_fc", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(YP|FC|FX)\b")),
    ("consumer_tl", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(TP|TL)\b")),
    ("retail_cards_fc", re.compile(r"^(BIREYSEL KREDI KARTLARI|RETAIL CREDIT CARDS|INDIVIDUAL CREDIT CARDS)\s*[-–]?\s*(YP|FC|FX)")),
    ("retail_cards_tl", re.compile(r"^(BIREYSEL KREDI KARTLARI|RETAIL CREDIT CARDS|INDIVIDUAL CREDIT CARDS)\s*[-–]?\s*(TP|TL)")),
    ("personnel_cards_fc", re.compile(r"^(PERSONEL KREDI KARTLARI|PERSONNEL CREDIT CARDS)\s*[-–]?\s*(YP|FC|FX)")),
    ("personnel_cards_tl", re.compile(r"^(PERSONEL KREDI KARTLARI|PERSONNEL CREDIT CARDS)\s*[-–]?\s*(TP|TL)")),
    ("personnel_loans_fc_indexed", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(DOVIZE ENDEKSLI|FC.?INDEXED|FX.?INDEXED)")),
    ("personnel_loans_fc", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(YP|FC|FX)\b")),
    ("personnel_loans_tl", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(TP|TL)\b")),
    ("overdraft_fc", re.compile(r"^(KREDILI MEVDUAT HESABI|OVERDRAFT ACCOUNT)\s*[-–]?\s*(YP|FC|FX)")),
    ("overdraft_tl", re.compile(r"^(KREDILI MEVDUAT HESABI|OVERDRAFT ACCOUNT)\s*[-–]?\s*(TP|TL)")),
]
ITEMS: list[tuple[str, re.Pattern]] = [
    ("housing", re.compile(r"^KONUT|^HOUSING|^MORTGAGE")),
    ("vehicle", re.compile(r"^TASIT|^VEHICLE|^AUTO")),
    ("general_purpose", re.compile(r"^IHTIYAC|^GENERAL PURPOSE|^CONSUMER LOANS$|^PERSONAL")),
    ("instalment", re.compile(r"^TAKSITLI|^WITH.?INSTAL")),
    ("non_instalment", re.compile(r"^TAKSITSIZ|^WITHOUT.?INSTAL|^NON.?INSTAL")),
    ("other", re.compile(r"^DIGER|^OTHER")),
]
VALUES = ("short_term", "long_term", "total")


def _group_of(label: str) -> str | None:
    f = fold(label)
    for g, rx in GROUPS:
        if rx.search(f):
            return g
    return None


def _item_of(label: str) -> str | None:
    f = fold(label)
    for i, rx in ITEMS:
        if rx.search(f):
            return i
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_consumer_loan_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    group_role   TEXT,
    item_role    TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    short_term   REAL,
    long_term    REAL,
    total        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_consumer_loan_full_group
  ON bank_audit_consumer_loan_full(group_role, item_role);
"""


def _is_family(grid: list[dict]) -> bool:
    if not grid or len(grid) < 8:
        return False
    first = fold(grid[0]["label"] or "")
    return bool(_FIRST.search(first)) and any(
        _TOTAL.search(fold(r["label"] or "").strip()) for r in grid)


def _identity_holds(inst: list[dict]) -> bool:
    """total = short + long on >= 90% of value-bearing rows, and on the grand
    total row itself."""
    checked = ok = 0
    grand_ok = False
    for x in inst:
        s, lg, t = x["short_term"], x["long_term"], x["total"]
        if t is None or (s is None and lg is None):
            continue
        checked += 1
        hit = abs((s or 0.0) + (lg or 0.0) - t) <= max(2.0, 1e-5 * abs(t))
        ok += int(hit)
        if x["item_role"] is None and x["group_role"] is None \
                and _TOTAL.search(fold(x["label"]).strip()):
            grand_ok = hit
    return checked >= 4 and ok / checked >= 0.9 and grand_ok


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = [(pg, bid, json.loads(g), unit) for pg, bid, g, unit in blocks
             if _is_family(json.loads(g))]
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, grid, _u in found:
        rows, group = [], None
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            g = _group_of(label)
            if g:
                group = g
            item = None if g else _item_of(label)
            vals = [num(c) for c in r["cells"][-3:]]
            vals = [None] * (3 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": label, "group_role": group if (g or item) else None,
                   "item_role": item, "page": pg, "block_id": bid}
            row.update(zip(VALUES, vals))
            rows.append(row)
        instances.append(rows)
    labels = ("current", "prior", "extra2", "extra3")
    return {"unit": unit,
            "instances": {labels[i]: inst for i, inst in enumerate(instances[:4])}}


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
    inst_count: Counter = Counter()
    role_cov = [0, 0]
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = {}
        for lab, inst in got["instances"].items():
            if _identity_holds(inst):
                kept[lab] = inst
            else:
                gated += 1
        if not kept:
            continue
        inst_count[len(kept)] += 1
        for inst in kept.values():
            for x in inst:
                if x["total"] is not None:
                    role_cov[1] += 1
                    role_cov[0] += int(x["group_role"] is not None)
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(kept)} "
                  f"rows={[len(v) for v in kept.values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_consumer_loan_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in kept.items():
                out.executemany(
                    "INSERT INTO bank_audit_consumer_loan_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["label"], x["group_role"], x["item_role"],
                      x["short_term"], x["long_term"], x["total"], x["page"],
                      x["block_id"], got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by total = short + long: {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
    if role_cov[1]:
        print(f"  value-bearing rows with a group role: {role_cov[0]}/{role_cov[1]} "
              f"({role_cov[0] / role_cov[1]:.1%})")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_consumer_loan_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
