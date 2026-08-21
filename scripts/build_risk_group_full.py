#!/usr/bin/env python
"""The risk-group graduation: the NOTES-section disclosures of the bank's
own risk group — loans (cash, non-cash), deposits and derivative
transactions with (1) its associates, subsidiaries and joint ventures, (2)
its direct and indirect shareholders, (3) the other real and legal persons
in the risk group — each as opening balance, closing balance and the
period's interest / commission income (or deposit interest expense, or
derivative profit / loss), current and prior, minted from the document
layer. Stored LONG: one row per (measure, row, party, cash / non-cash).

The table carries no arithmetic of its own. What it does carry is a
cross-block identity: the prior period's closing balance must equal the
current period's opening balance, party by party. MINT GATE: where both
periods print, that identity must hold (`consistency` = 'paired'); a
filing printing one period only is kept as 'unpaired'; a failing pair is
refused.

`--write` stores into bank_audit_risk_group_full in
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
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

R = re.compile
ROLES: list[tuple[str, re.Pattern]] = [
    ("opening", R(r"^DONEM BASI|^BEGINNING|^BALANCE AT (THE )?BEGINNING|^OPENING|^FAIR VALUE AT (THE )?BEGINNING|"
                  r"^DONEM BASINDAKI|^GERCEGE UYGUN DEGER.*BASI")),
    ("closing", R(r"^DONEM SONU|^END OF|^BALANCE AT (THE )?END|^CLOSING|^FAIR VALUE AT (THE )?END|^DONEM SONUNDAKI|"
                  r"^GERCEGE UYGUN DEGER.*SONU")),
    ("income", R(r"^ALINAN FAIZ|^INTEREST AND (COMMISSION|FEE)|^INTEREST (INCOME )?RECEIVED|^FAIZ VE KOMISYON|^COMMISSION")),
    ("expense", R(r"^MEVDUAT FAIZ GIDERI|^DEPOSIT INTEREST|^INTEREST (EXPENSE|PAID) ON DEPOSIT|^KAR PAYI GIDERI|^PROFIT SHARE EXPENSE|"
                  r"^FAIZ GIDERI|^INTEREST EXPENSE")),
    ("profit_loss", R(r"^TOPLAM KAR|^TOTAL (PROFIT|INCOME|GAIN)|^KAR/ZARAR|^PROFIT/LOSS|^NET (PROFIT|GAIN)")),
    ("total", R(r"^TOPLAM|^TOTAL")),
]
PARTIES = ("associates_subsidiaries", "shareholders", "other_risk_group")
_CTX = R(r"RISK GRUBU|RISK GROUP")
_DEPOSIT = R(r"MEVDUAT|DEPOSIT|KATILMA HESAP|PARTICIPATION ACCOUNT")
_DERIV = R(r"TUREV|DERIVATIVE|FORWARD|SWAP|VADELI ISLEM")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_risk_group_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    measure      TEXT NOT NULL,      -- loans / deposits / derivatives
    instance_no  INTEGER NOT NULL,
    period_label TEXT NOT NULL,      -- current / prior
    consistency  TEXT NOT NULL,      -- paired / unpaired
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    party        TEXT NOT NULL,      -- associates_subsidiaries / shareholders / other_risk_group
    cashness     TEXT,               -- cash / non_cash; NULL where the table prints one column per party
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, measure, instance_no, row_order, party, cashness)
);
"""


def _columns(n: int):
    if n == 6:
        return [(p, c) for p in PARTIES for c in ("cash", "non_cash")]
    if n == 3:
        return [(p, None) for p in PARTIES]
    return None


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not 2 <= len(grid) <= 8 or len(grid[0]["cells"]) not in (3, 6):
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    if "opening" not in roles or "closing" not in roles:
        return False
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    return bool(_CTX.search(ctx)) or bool(re.search(r"NAKDI|CASH|ORTAK|SHAREHOLDER|ISTIRAK|SUBSIDIAR|ASSOCIATE", ctx))


def _measure_of(grid, heading) -> str:
    text = fold(heading or "") + " " + " ".join(fold(r["label"] or "") for r in grid)
    roles = {role_of(r["label"] or "") for r in grid}
    if "expense" in roles or (_DEPOSIT.search(text) and not _DERIV.search(text)):
        return "deposits"
    if "profit_loss" in roles or _DERIV.search(text):
        return "derivatives"
    return "loans"


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid = absorb_inline(json.loads(g), role_of)
        if _is_family(grid, json.loads(cl or "[]"), heading):
            found.append((pg, bid, heading, grid, unit))
    if not found:
        return None
    unit = found[0][4]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, heading, grid, _u in found:
        cols = _columns(len(grid[0]["cells"]))
        rows = []
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            vals = [num(c) for c in r["cells"][-len(cols):]]
            vals = [None] * (len(cols) - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            rows.append({"label": label, "role": role_of(label), "cells": list(zip(cols, vals)),
                         "page": pg, "block_id": bid})
        instances.append({"measure": _measure_of(grid, heading), "rows": rows, "heading": heading})
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


def _pair(instances: list[dict], step: float):
    """Order each measure's blocks into (current, prior) by the opening /
    closing hand-off and mark their consistency. Returns [(inst, label,
    consistency)] and the number refused."""
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))

    def vec(inst, role):
        row = next((x for x in inst["rows"] if x["role"] == role), None)
        return {c: v for c, v in row["cells"]} if row else {}

    out, refused = [], 0
    by_measure: dict[str, list] = {}
    for inst in instances:
        by_measure.setdefault(inst["measure"], []).append(inst)
    for measure, insts in by_measure.items():
        if len(insts) == 1:
            out.append((insts[0], "current", "unpaired"))
            continue
        a, b = insts[0], insts[1]
        # the current block prints first; its opening must be the prior's closing
        ao, bc = vec(a, "opening"), vec(b, "closing")
        pairs = [(ao[c], bc[c]) for c in ao if c in bc and ao[c] is not None and bc[c] is not None]
        if pairs and all(close(x, y) for x, y in pairs):
            out += [(a, "current", "paired"), (b, "prior", "paired")]
        else:
            bo, ac = vec(b, "opening"), vec(a, "closing")
            pairs2 = [(bo[c], ac[c]) for c in bo if c in ac and bo[c] is not None and ac[c] is not None]
            if pairs2 and all(close(x, y) for x, y in pairs2):
                out += [(b, "current", "paired"), (a, "prior", "paired")]
            elif not pairs and not pairs2:
                out += [(a, "current", "unpaired"), (b, "prior", "unpaired")]
            else:
                refused += 2
        for extra in insts[2:]:
            out.append((extra, "extra", "unpaired"))
    return out, refused


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
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

    detected = written = refused = 0
    measures: Counter = Counter()
    consistency: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept, bad = _pair(got["instances"], got["step"])
        refused += bad
        if not kept:
            continue
        for inst, label, cons in kept:
            measures[inst["measure"]] += 1
            consistency[cons] += 1
        if out is not None:
            out.execute("DELETE FROM bank_audit_risk_group_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            for inst, label, cons in kept:
                n = n_by[inst["measure"]]
                n_by[inst["measure"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_risk_group_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["measure"], n, label, cons, inst["heading"], i, x["label"], x["role"], party, cashness, v,
                      x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for (party, cashness), v in x["cells"]])
                written += sum(len(x["cells"]) for x in inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks refused (prior closing ≠ current opening): {refused}")
    if measures:
        print(f"blocks kept by measure: {dict(measures)} | consistency: {dict(consistency)}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_risk_group_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
