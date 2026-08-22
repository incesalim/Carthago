#!/usr/bin/env python
"""The RWA-overview graduation: BRSA's numbered 1-25 template (the Pillar 3
OV1 form), minted from the document layer on the shared numbered-template
machinery.

The narrow lanes keep exactly one number of it — `bank_audit_capital.total_rwa`
(row 25). The wide lane keeps the whole decomposition: credit risk and its
approach, counterparty credit risk, equity, settlement, securitisation, market
risk, operational risk, below-threshold amounts and the floor — in three
printed columns: RWA current period, RWA prior year-end, and the minimum
capital requirement (8% of RWA under BRSA, which the template's own identity
makes checkable on every row).

Validators, dry-run (default): row 25 RWA vs the narrow capital lane AND vs
the graduated `bank_audit_capital_full` total_rwa role (the first wide-vs-wide
cross-anchor); the prior column vs the prior YEAR-END's narrow total_rwa; and
minimum capital = 8% x RWA on rows 1, 16, 19 and 25.

`--write` stores into bank_audit_rwa_full in data/bank_audit_tables.db
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
    1: re.compile(r"^KREDI RISKI|^CREDIT RISK"),
    16: re.compile(r"^PIYASA RISKI|^MARKET RISK"),
    19: re.compile(r"^OPERASYONEL RISK|^OPERATIONAL RISK"),
    25: re.compile(r"^TOPLAM|^TOTAL"),
}
ROLE_BY_ROW = {
    1: "credit_risk", 2: "credit_risk_standardised", 3: "credit_risk_irb",
    4: "counterparty_credit_risk", 7: "equity_positions",
    11: "settlement_risk", 12: "securitisation", 16: "market_risk",
    17: "market_risk_standardised", 18: "market_risk_internal_models",
    19: "operational_risk", 20: "operational_risk_basic_indicator",
    21: "operational_risk_standardised", 23: "below_threshold_amounts",
    24: "floor_adjustment", 25: "total_rwa",
}
_IDENTITY_ROWS = (1, 16, 19, 25)
_MIN_CAPITAL_RATE = 0.08


def _close(a: float, b: float) -> bool:
    """Two separately printed tables (OV1 vs the own-funds table's RWA row)
    round their components independently: DENIZ 2022Q4 prints 423,588,045
    here and 423,588,063 there. A 0.01% relative band absorbs that and still
    catches any real disagreement by orders of magnitude."""
    return abs(a - b) <= max(1.5, 1e-4 * abs(b))

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_rwa_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- the template's three printed columns, canonical thousand TL (scaled at
    -- mint). NULL = the filing printed "-".
    rwa          REAL,
    rwa_prior    REAL,
    min_capital  REAL,
    -- the prior period's minimum capital, where the form prints all four
    -- columns (RWA current / prior, minimum capital current / prior)
    min_capital_prior REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_rwa_full_row
  ON bank_audit_rwa_full(template_row);
"""


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    """The form prints three value columns at most banks — RWA current,
    RWA prior, minimum capital — and FOUR at others, adding the prior
    period's minimum capital. Reading four as three took the last three and
    shifted every figure one column left: HALKB's total RWA came out as its
    PRIOR total (1,203,850,144 for 1,436,786,128), which is how the capital
    note's RWA and this one disagreed at 80 filings while each stayed
    internally consistent."""
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=25, bottom_row=23, n_values=4,
        percent_rows=set(), role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("rwa", "rwa_prior", "min_capital", "min_capital_prior"))
    if got is not None and _four_columns(got):
        return got
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=25, bottom_row=23, n_values=3,
        percent_rows=set(), role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("rwa", "rwa_prior", "min_capital"))
    if got is None:
        return None
    for inst in got["instances"].values():
        for row in inst:
            row["min_capital_prior"] = None
    return got


def _four_columns(got: dict) -> bool:
    """True when the four-column reading is the right one: the form's own
    ratio, minimum capital = 8% of RWA, holds on the total row for BOTH
    period pairs. On a three-column form read as four the values shift and
    the ratio fails."""
    for inst in got["instances"].values():
        total = next((r for r in inst if r["template_row"] == 25), None)
        if total is None:
            continue
        pairs = ((total.get("rwa"), total.get("min_capital")),
                 (total.get("rwa_prior"), total.get("min_capital_prior")))
        ok = 0
        for rwa, mc in pairs:
            if rwa is None or mc is None or not rwa:
                continue
            ok += int(abs(mc / rwa - 0.08) <= 0.002)
        if ok == 2:
            return True
    return False


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

    def narrow_rwa(key):
        return [v for (v,) in aud.execute(
            "SELECT total_rwa FROM bank_audit_capital WHERE bank_ticker=? AND "
            "period=? AND kind=?", key) if v is not None]

    def wide_capital_rwa(key):
        try:
            return [v for (v,) in tab.execute(
                "SELECT amount FROM bank_audit_capital_full WHERE bank_ticker=? "
                "AND period=? AND kind=? AND row_role='total_rwa'", key)
                if v is not None]
        except sqlite3.OperationalError:
            return []

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_capital "
        "WHERE total_rwa IS NOT NULL")}

    detected = written = 0
    inst_count: Counter = Counter()
    rows_per: list[int] = []
    cur_a, wide_a, pri_a, ident = [0, 0], [0, 0], [0, 0], [0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        inst_count[len(got["instances"])] += 1
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        rows_per.append(len(cur))
        for n in _IDENTITY_ROWS:
            rwa, mc = cur.get(n, {}).get("rwa"), cur.get(n, {}).get("min_capital")
            if rwa and mc is not None:
                ident[1] += 1
                ident[0] += int(abs(mc / rwa - _MIN_CAPITAL_RATE) <= 0.0015)
        total = cur.get(25, {})
        wide = total.get("rwa")
        if wide is not None:
            have = narrow_rwa(key)
            if have:
                cur_a[1] += 1
                ok = any(_close(wide, v) for v in have)
                cur_a[0] += int(ok)
                if not ok and len(mism) < 8:
                    mism.append((key, "narrow", wide, sorted(set(have))))
            wc = wide_capital_rwa(key)
            if wc:
                wide_a[1] += 1
                wide_a[0] += int(any(_close(wide, v) for v in wc))
        pwide = total.get("rwa_prior")
        phave = narrow_rwa((key[0], NT.prior_year_end(key[1]), key[2]))
        if pwide is not None and phave:
            pri_a[1] += 1
            pri_a[0] += int(any(_close(pwide, v) for v in phave))
        if args.verbose:
            print(f"{' '.join(key)}: rows={len(cur)} unit={got['unit']}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_rwa_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_rwa_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["rwa"], x["rwa_prior"], x["min_capital"], x.get("min_capital_prior"), x["page"],
                      x["block_id"], got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    import statistics
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"narrow total_rwa present locally {len(both)}")
    if rows_per:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}; "
              f"rows per table: median {statistics.median(rows_per):.0f}")
    for name, b in (("row 25 RWA vs narrow capital total_rwa", cur_a),
                    ("row 25 RWA vs capital_full total_rwa (wide)", wide_a),
                    ("prior column vs prior-YEAR-END narrow", pri_a),
                    ("min capital = 8% x RWA (rows 1/16/19/25)", ident)):
        print(f"  {name:44} {b[0]:4}/{b[1]:4}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    for key, which, wide, vals in mism:
        print(f"    {' '.join(key):32} vs {which} wide={wide} have={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_rwa_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
