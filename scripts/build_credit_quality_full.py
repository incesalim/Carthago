#!/usr/bin/env python
"""The credit-quality-of-assets graduation: BRSA's numbered 1-4 Pillar 3 CR1
form, minted from the document layer on the shared numbered-template
machinery.

Rows: loans, debt securities, off-balance-sheet receivables, total. Columns:
gross carrying value of defaulted and of non-defaulted exposures, allowances
/ impairments, and the net value — for the current period and the prior
year-end (two printed instances). Its sibling CR3 (credit-risk mitigation
techniques) numbers the same first rows but prints seven columns; the shape
filter keeps it out.

Validators, dry-run (default): the form's own identity net = defaulted +
non-defaulted - allowances on rows 1 and 4 (the MINT GATE — an instance is
stored only if row 4 satisfies it); row 4 = sum of rows 1-3 in each column;
and defaulted loans (row 1) against the narrow NPL-movement lane's closing
sum (groups III+IV+V, current) for the same filing, a cross-lane anchor.

`--write` stores into bank_audit_credit_quality_full in
data/bank_audit_tables.db (local only; never the audit snapshot, not D1).
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
    1: re.compile(r"^KREDILER|^LOANS"),
    2: re.compile(r"^BORCLANMA ARAC|^DEBT (SECURITIES|INSTRUMENTS)"),
    4: re.compile(r"^TOPLAM|^TOTAL"),
}
ROLE_BY_ROW = {1: "loans", 2: "debt_securities",
               3: "off_balance_sheet_receivables", 4: "total"}
VALUES = ("defaulted_gross", "non_defaulted_gross", "allowances", "net")

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_credit_quality_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    defaulted_gross     REAL,
    non_defaulted_gross REAL,
    allowances          REAL,
    net                 REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
"""


def _is_cr1(grid: list[dict]) -> bool:
    """Four value columns (CR3 prints seven) AND the loans row in row 1 — a
    four-row template whose bottom row is "Total" would otherwise admit every
    short numbered table in the Pillar 3 section (CVA, market risk...)."""
    if not 4 <= NT.live_value_columns(grid, 4) <= 5:
        return False
    return any(NT.rowno(r, 4) == 1 and _SIG[1].search(
        NT.fold(NT._LABEL_PREFIX.sub("", (r["label"] or "").strip())))
        for r in grid)


def _net_holds(x: dict) -> bool:
    d, nd, a, n = (x.get("defaulted_gross"), x.get("non_defaulted_gross"),
                   x.get("allowances"), x.get("net"))
    if n is None or (d is None and nd is None):
        return False
    return abs((d or 0.0) + (nd or 0.0) - (a or 0.0) - n) <= max(2.0, 1e-5 * abs(n))


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=4, bottom_row=4, n_values=4,
        percent_rows=set(), role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=VALUES, block_filter=_is_cr1, row_live_cells=True)
    if got is None:
        return None
    # CR2 (defaulted-loan movement, rows 1-6) often shares CR1's captured
    # block and splits off as a further instance; it is not this form.
    got["instances"] = {lab: inst for lab, inst in got["instances"].items()
                        if any(x["template_row"] == 1 and _SIG[1].search(NT.fold(x["label"]))
                               for x in inst)}
    kept = {lab: inst for lab, inst in got["instances"].items()
            if any(x["template_row"] == 4 and _net_holds(x) for x in inst)}
    got["gated"] = len(got["instances"]) - len(kept)
    got["instances"] = kept
    return got if kept else None


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

    def npl_closing(key) -> float | None:
        """The narrow lane stores one row per NPL group (III / IV / V); the
        CR1 defaulted-loans figure is their current-period closing sum."""
        try:
            rows = [v for (v,) in aud.execute(
                "SELECT closing_balance FROM bank_audit_npl_movement WHERE "
                "bank_ticker=? AND period=? AND kind=? AND period_type='current'",
                key) if v is not None]
        except sqlite3.OperationalError:
            return None
        return sum(rows) if rows else None

    detected = written = gated = 0
    inst_count: Counter = Counter()
    row_ident = [0, 0]
    sum_ident = [0, 0]
    npl_a = [0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        gated += got["gated"]
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            by = {x["template_row"]: x for x in inst}
            for n in (1, 2, 3):
                x = by.get(n)
                if x and x["net"] is not None:
                    row_ident[1] += 1
                    row_ident[0] += int(_net_holds(x))
            tot = by.get(4)
            if tot:
                for col in VALUES:
                    t = tot[col]
                    if t is None:
                        continue
                    s = sum((by.get(n, {}).get(col) or 0.0) for n in (1, 2, 3))
                    sum_ident[1] += 1
                    sum_ident[0] += int(abs(s - t) <= max(2.0, 1e-5 * abs(t)))
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        d = cur.get(1, {}).get("defaulted_gross")
        have = npl_closing(key)
        if d is not None and have:
            npl_a[1] += 1
            ok = abs(d - have) <= max(2.0, 1e-3 * abs(have))
            npl_a[0] += int(ok)
            if not ok and len(mism) < 8:
                mism.append((key, d, have))
        if out is not None:
            out.execute("DELETE FROM bank_audit_credit_quality_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_credit_quality_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      *(x[v] for v in VALUES), x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by the net identity on row 4: {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
    for name, b in (("net = defaulted + non-defaulted - allowances (rows 1-3)", row_ident),
                    ("row 4 = rows 1+2+3, per column", sum_ident),
                    ("defaulted loans vs narrow NPL closing sum III+IV+V (0.1%)", npl_a)):
        print(f"  {name:55} {b[0]:5}/{b[1]:5}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    for key, d, vals in mism:
        print(f"    {' '.join(key):32} cr1={d:,.0f} npl_sum={vals:,.0f}  "
              f"({d / vals - 1:+.1%})")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_credit_quality_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
