#!/usr/bin/env python
"""The leverage-ratio graduation: BRSA's numbered 1-15 template, minted from
the document layer on the shared numbered-template machinery.

The narrow `bank_audit_liquidity` keeps ONE number of this disclosure
(`leverage_ratio`, row 15). The wide lane keeps all 15 rows — on-balance-
sheet exposure, derivatives, securities-financing, off-balance-sheet
conversions, Tier 1 capital, total exposure — in both printed columns
(current period and the prior year-end, side by side in one table).

Validators, dry-run (default): row 15's current column vs narrow
`leverage_ratio`; its prior column vs the prior YEAR-END's narrow row; and
the template's own identity, row 15 = Tier 1 (13) / total exposure (14),
which is point-in-time-tight (the rows are the same three-month averages the
ratio is computed from).

`--write` stores into bank_audit_leverage_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import numbered_template as NT  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

_SIG = {
    13: re.compile(r"^ANA SERMAYE|^TIER (I|1) CAPITAL"),
    14: re.compile(r"TOPLAM RISK TUTARI|TOTAL (RISKS?|EXPOSURE)"),
    15: re.compile(r"KALDIRAC ORANI|LEVERAGE RATIO"),
}
ROLE_BY_ROW = {
    1: "on_balance_sheet_assets", 2: "tier1_deductions",
    3: "on_balance_sheet_exposure", 6: "derivatives_exposure",
    9: "sft_exposure", 12: "off_balance_sheet_exposure",
    13: "tier1_capital", 14: "total_exposure", 15: "leverage_ratio",
}

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_leverage_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- current period and the prior YEAR-END, the two printed columns.
    -- Canonical thousand TL, scaled at mint; row 15 is the percent, never
    -- scaled. NULL = the filing printed "-".
    amount       REAL,
    amount_prior REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_leverage_full_row
  ON bank_audit_leverage_full(template_row);
"""


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    return NT.assemble(
        tab, key, sig=_SIG, max_row=15, bottom_row=14, n_values=2,
        percent_rows={15}, role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("amount", "amount_prior"),
        # a leverage ratio is single digits; "9,127" read as 9127 is 9.127%
        percent_repair_floor=1000)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
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

    def narrow(key):
        return [v for (v,) in aud.execute(
            "SELECT leverage_ratio FROM bank_audit_liquidity WHERE bank_ticker=? "
            "AND period=? AND kind=?", key) if v is not None]

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_liquidity "
        "WHERE leverage_ratio IS NOT NULL")}

    detected = written = 0
    inst_count: Counter = Counter()
    rows_per: list[int] = []
    cur_a, pri_a, ident = [0, 0], [0, 0], [0, 0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            rows_per.append(len(inst))
            by_row = {x["template_row"]: x for x in inst}
            for col in ("amount", "amount_prior"):
                t1 = by_row.get(13, {}).get(col)
                ex = by_row.get(14, {}).get(col)
                r = by_row.get(15, {}).get(col)
                if None not in (t1, ex, r) and ex:
                    d = abs(t1 / ex * 100 - r)
                    ident[2] += 1
                    ident[0] += int(d <= 0.05)
                    ident[1] += int(d <= 0.5)
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        wide = cur.get(15, {}).get("amount")
        have = narrow(key)
        if wide is not None and have:
            cur_a[1] += 1
            ok = any(abs(wide - v) <= 0.06 for v in have)
            cur_a[0] += int(ok)
            if not ok and len(mism) < 10:
                mism.append((key, wide, sorted(set(have))))
        pwide = cur.get(15, {}).get("amount_prior")
        phave = narrow((key[0], NT.prior_year_end(key[1]), key[2]))
        if pwide is not None and phave:
            pri_a[1] += 1
            pri_a[0] += int(any(abs(pwide - v) <= 0.06 for v in phave))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(got['instances'])} "
                  f"rows={[len(v) for v in got['instances'].values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_leverage_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_leverage_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["amount"], x["amount_prior"], x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    import statistics
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"narrow leverage present locally {len(both)}")
    if rows_per:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}; "
              f"rows per instance: median {statistics.median(rows_per):.0f}")
    for name, b in (("current leverage vs narrow", cur_a),
                    ("prior column vs prior-YEAR-END narrow", pri_a)):
        print(f"  {name:38} {b[0]:4}/{b[1]:4}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    if ident[2]:
        print(f"  identity 15 = 13/14: within 0.05: {ident[0]}/{ident[2]} "
              f"({ident[0] / ident[2]:.1%})   within 0.5: {ident[1]}/{ident[2]} "
              f"({ident[1] / ident[2]:.1%})")
    for key, wide, vals in mism:
        print(f"    {' '.join(key):32} wide={wide} narrow={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_leverage_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
