#!/usr/bin/env python
"""The shareholder-loans graduation: the NOTES-section table of loans to the
bank's shareholders and employees — direct loans to shareholders (legal
persons, real persons), indirect loans to shareholders, loans to employees,
total — × (cash, non-cash) × (current, prior), minted from the document
layer.

MINT GATE: the template's two identities on every printed column — direct
= legal + real persons, and total = direct + indirect + employees. No
narrow lane holds any of this; the gate is the lane's whole warrant.

`--write` stores into bank_audit_shareholder_loans_full in
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
    ("total", R(r"^TOPLAM|^TOTAL")),
    ("direct_legal", R(r"^TUZEL KISI|^CORPORATE|^LEGAL (PERSON|ENTIT)|^LOANS (TO|GRANTED TO) (CORPORATE|LEGAL)")),
    ("direct_real", R(r"^GERCEK KISI|^INDIVIDUAL|^REAL PERSON|^NATURAL PERSON|^LOANS (TO|GRANTED TO) (INDIVIDUAL|REAL)")),
    ("indirect", R(r"DOLAYLI|INDIRECT")),
    ("employees", R(r"MENSUP|EMPLOYEE|PERSONNEL|STAFF")),
    ("direct", R(r"DOGRUDAN|DIRECT")),
]
VALUES = ("cash_current", "noncash_current", "cash_prior", "noncash_prior")
_CTX = R(r"NAKDI|CASH|G\.NAKDI|NON.?CASH")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_shareholder_loans_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    cash_current     REAL,
    noncash_current  REAL,
    cash_prior       REAL,
    noncash_prior    REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order)
);
"""


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not 4 <= len(grid) <= 9 or len(grid[0]["cells"]) != 4:
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    if "direct" not in roles or "total" not in roles or "employees" not in roles:
        return False
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    return bool(_CTX.search(ctx))


def _identities_hold(rows: list[dict], step: float) -> bool:
    by: dict[str, dict] = {}
    for x in rows:
        by.setdefault(x["role"], x)
    tot = by.get("total")
    if not tot:
        return False

    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    checked = 0
    for col in VALUES:
        t = tot[col]
        if t is None:
            continue
        direct = (by.get("direct") or {}).get(col)
        legal, real = (by.get("direct_legal") or {}).get(col), (by.get("direct_real") or {}).get(col)
        if direct is not None and (legal is not None or real is not None) \
                and not close((legal or 0.0) + (real or 0.0), direct):
            return False
        if direct is None:
            direct = (legal or 0.0) + (real or 0.0)
        s = direct + ((by.get("indirect") or {}).get(col) or 0.0) + ((by.get("employees") or {}).get(col) or 0.0)
        if not close(s, t):
            return False
        checked += 1
    return checked >= 1


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid = absorb_inline(json.loads(g), role_of)
        if _is_family(grid, json.loads(cl or "[]"), heading):
            found.append((pg, bid, grid, unit))
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, grid, _u in found:
        rows = []
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            vals = [num(c) for c in r["cells"][-4:]]
            vals = [None] * (4 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": label, "role": role_of(label), "page": pg, "block_id": bid}
            row.update(zip(VALUES, vals))
            rows.append(row)
        instances.append(rows)
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


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

    detected = written = gated = 0
    per_filing: Counter = Counter()
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = [inst for inst in got["instances"] if _identities_hold(inst, got["step"])]
        gated += len(got["instances"]) - len(kept)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        for inst in kept:
            for x in inst:
                if any(x[v] is not None for v in VALUES):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
        if out is not None:
            out.execute("DELETE FROM bank_audit_shareholder_loans_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            for n, inst in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_shareholder_loans_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, i, x["label"], x["role"], *(x[v] for v in VALUES), x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the identities: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(6):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_shareholder_loans_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
