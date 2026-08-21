#!/usr/bin/env python
"""The earnings-per-share graduation: the three-row note — net profit
attributable to ordinary shareholders, weighted average number of shares
(printed in thousands), earnings per share (full TL) — current and prior,
minted from the document layer.

MINT GATE: the note's own division — eps = profit / shares, allowing the
share count to be printed in thousands or in units (a factor of 1,000
either way), within 1% (EPS prints to four or five decimals). Anchor,
dry-run (default): the current net profit vs the narrow P&L's net profit /
group share lines, same filing.

`--write` stores into bank_audit_eps_full in data/bank_audit_tables.db
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
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
ROLES: list[tuple[str, re.Pattern]] = [
    ("eps", R(r"HISSE BASINA|PER SHARE|PER 1\.?000 SHARES")),
    ("shares", R(r"HISSE(LERIN|LER)? ?(AGIRLIKLI|ADEDI|SAYISI)|HISSE ADEDI|ADI HISSELERIN|NUMBER OF (ISSUED |ORDINARY |COMMON )?SHARES|"
                 r"AMOUNT OF SHARES|SHARES? (ISSUED|OUTSTANDING)|WEIGHTED AVERAGE|NUMBER OF ([A-Z]+ ){0,3}SHARES")),
    ("net_profit", R(r"NET (DONEM )?KAR|NET PROFIT|NET INCOME|DAGITILABILIR|DISTRIBUTABLE|ATTRIBUTABLE|GRUBUN KAR|GRUP.?UN KAR|GROUP.?S PROFIT|PROFIT FOR THE|^DONEM KAR")),
]
_PL_PROFIT = R(r"^DONEM NET KAR|^NET PROFIT|^NET INCOME|^GRUBUN KAR|^GROUP.?S? (PROFIT|SHARE)|^NET DONEM KAR|^PROFIT ATTRIBUTABLE|^CURRENT PERIOD (NET )?PROFIT")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_eps_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    -- canonical thousand TL (profit, scaled at mint); shares as printed
    -- (thousands at nearly every bank — `share_factor` says which reading
    -- made the division close: 1 = thousands, 1000 = units); eps in full TL.
    net_profit_current   REAL,
    net_profit_prior     REAL,
    shares_current       REAL,
    shares_prior         REAL,
    eps_current          REAL,
    eps_prior            REAL,
    share_factor         REAL NOT NULL,
    profit_label  TEXT,
    shares_label  TEXT,
    eps_label     TEXT,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no)
);
"""


def _division_factor(profit, shares, eps) -> float | None:
    if profit is None or shares is None or eps is None or shares == 0 or eps == 0:
        return None
    for f in (1.0, 1000.0, 0.001):
        if abs(profit / shares * f - eps) <= max(1e-5, 0.01 * abs(eps)):
            return f
    return None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, grid_json, declared_unit FROM bank_audit_document_tables "
        "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, g, unit in blocks:
        grid = absorb_inline(json.loads(g), role_of)
        if not 2 <= len(grid) <= 8 or len(grid[-1]["cells"]) not in (1, 2):
            continue                       # one column: a block per period, dated above
        roles = {role_of(r["label"] or ""): r for r in grid if role_of(r["label"] or "")}
        if {"eps", "shares", "net_profit"} <= set(roles):
            found.append((pg, bid, roles, unit))
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, roles, _u in found:
        def pair(role, scale):
            r = roles[role]
            vals = [num(c) for c in r["cells"][-2:]]
            if len(r["cells"]) == 1:        # a single-period block: current only
                vals = [vals[0], None]
            vals = [None] * (2 - len(vals)) + vals
            if scale and factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            return vals, (r["label"] or "").strip()
        (pc, pp), pl = pair("net_profit", True)
        (sc, sp), sl = pair("shares", False)
        (ec, ep), el = pair("eps", False)
        instances.append({"profit": (pc, pp), "shares": (sc, sp), "eps": (ec, ep),
                          "labels": (pl, sl, el), "page": pg, "block_id": bid})
    return {"unit": unit, "instances": instances}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
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

    def narrow_profit(key) -> list[float]:
        try:
            return [v for n, v in aud.execute(
                "SELECT item_name, amount FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?", key)
                if v is not None and _PL_PROFIT.search(fold(n or "").strip())]
        except sqlite3.OperationalError:
            return []

    detected = written = gated = 0
    factors: Counter = Counter()
    anchor = [0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            f = _division_factor(inst["profit"][0], inst["shares"][0], inst["eps"][0])
            if f is None:
                gated += 1
                continue
            inst["factor"] = f
            factors[f] += 1
            kept.append(inst)
            ref = narrow_profit(key)
            if ref and inst["profit"][0] is not None:
                anchor[1] += 1
                ok = any(abs(inst["profit"][0] - v) <= max(2.0, 1e-3 * abs(v)) for v in ref)
                anchor[0] += int(ok)
                if not ok and len(mism) < 5:
                    mism.append((key, inst["profit"][0], ref[:2]))
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_eps_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            for n, inst in enumerate(kept):
                out.execute("INSERT INTO bank_audit_eps_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (*key, n, *inst["profit"], *inst["shares"], *inst["eps"], inst["factor"],
                             *inst["labels"], inst["page"], inst["block_id"], got["unit"]))
                written += 1
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused (eps ≠ profit / shares): {gated}")
    if factors:
        print(f"instances kept: {sum(factors.values())} | share factor: {dict(factors)}")
    if anchor[1]:
        print(f"  net profit vs narrow P&L net profit / group share: {anchor[0]}/{anchor[1]} ({anchor[0] / anchor[1]:.1%})")
    for key, p, ref in mism:
        print(f"    {' '.join(key):32} note={p:,.0f} narrow={ref}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_eps_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
