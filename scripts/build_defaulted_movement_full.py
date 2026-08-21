#!/usr/bin/env python
"""The defaulted-exposure movement graduation: BRSA's numbered 1-6 Pillar 3
CR2 form ("changes in stock of defaulted loans and debt securities"), minted
from the document layer on the shared numbered-template machinery.

Rows: opening defaulted stock (end of previous period), newly defaulted,
returned to non-defaulted, amounts written off, other changes, closing
defaulted stock. One or two columns (current; prior year where printed).

Banks disagree on signs. AKBNK prints every line positive and the closing is
opening + new - returned - write-offs - other; AKTIF prints the deductions
negative and everything sums. Each instance is stored AS PRINTED together
with the `convention` under which its own arithmetic balanced — that is the
MINT GATE; an instance that balances under none is refused.

Anchors, dry-run (default): closing stock vs CR1's current defaulted stock
(bank_audit_credit_quality_full, the lane minted just before this one) on
either perimeter banks use — loans + debt securities, or the CR1 total
including off-balance-sheet receivables — and vs the narrow NPL-movement
closing sum (groups III+IV+V); opening stock vs CR1's prior stock likewise.

`--write` stores into bank_audit_defaulted_movement_full in
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
    1: re.compile(r"^ONCEKI RAPORLAMA|TARIHINDEKI TEMERRUT|^DEFAULTED LOANS AND DEBT "
                  r"SECURITIES AT (THE )?END OF (THE )?PREVIOUS|^DEFAULTED .* AT (THE )?BEGINNING"),
    4: re.compile(r"^AKTIFTEN SILINEN|^AMOUNTS? WRITTEN.?OFF|^WRITE.?OFFS?|^WRITTEN.?OFF"),
    6: re.compile(r"^RAPORLAMA DONEMI SONUNDAKI|TARIHINDEKI TEMERRUT|^DEFAULTED LOANS AND DEBT "
                  r"SECURITIES AT (THE )?END OF (THE )?(CURRENT )?REPORTING|^DEFAULTED .* AT (THE )?END"),
}
ROLE_BY_ROW = {1: "opening", 2: "newly_defaulted", 3: "returned_to_performing",
               4: "written_off", 5: "other_changes", 6: "closing"}
VALUES = ("amount", "amount_prior")
_REL = 1e-5

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_defaulted_movement_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- AS PRINTED, canonical thousand TL (scaled at mint). NULL = "-".
    amount       REAL,
    amount_prior REAL,
    -- which arithmetic balanced this instance's `amount` column:
    --   signed            closing = 1 + 2 + 3 + 4 + 5 (deductions printed negative)
    --   deductions_3_4    closing = 1 + 2 - 3 - 4 + 5
    --   deductions_3_4_5  closing = 1 + 2 - 3 - 4 - 5
    convention   TEXT NOT NULL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
"""

CONVENTIONS = (
    ("signed", (1, 1, 1, 1, 1)),
    ("deductions_3_4", (1, 1, -1, -1, 1)),
    ("deductions_3_4_5", (1, 1, -1, -1, -1)),
)


def _is_cr2(grid: list[dict]) -> bool:
    if not 1 <= NT.live_value_columns(grid, 6) <= 6:
        return False
    return any(NT.rowno(r, 6) == 1 and _SIG[1].search(
        NT.fold(NT._LABEL_PREFIX.sub("", (r["label"] or "").strip())))
        for r in grid)


def convention_of(inst: list[dict], col: str = "amount") -> str | None:
    by = {x["template_row"]: x.get(col) for x in inst}
    close = by.get(6)
    if close is None or by.get(1) is None:
        return None
    for name, signs in CONVENTIONS:
        s = sum(sg * (by.get(n) or 0.0) for n, sg in zip((1, 2, 3, 4, 5), signs))
        if abs(s - close) <= max(2.0, _REL * abs(close)):
            return name
    return None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=6, bottom_row=6, n_values=2,
        percent_rows=set(), role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=VALUES, block_filter=_is_cr2, row_live_cells=True)
    if got is None:
        return None
    kept, gated = {}, 0
    for lab, inst in got["instances"].items():
        if all(x["amount"] is None for x in inst) and any(x["amount_prior"] is not None for x in inst):
            for x in inst:                      # a one-column print: the block
                x["amount"], x["amount_prior"] = x["amount_prior"], None   # model parked it right
        conv = convention_of(inst)
        if conv is None:
            gated += 1
            continue
        for x in inst:
            x["convention"] = conv
        kept[lab] = inst
    got["instances"], got["gated"] = kept, gated
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

    def cr1_defaulted(key, label) -> dict[str, float] | None:
        """CR1's defaulted stock on the two perimeters banks run CR2 on:
        loans + debt securities (rows 1-2), or the CR1 total including
        off-balance-sheet receivables (row 4)."""
        try:
            by = {r: v for r, v in tab.execute(
                "SELECT template_row, defaulted_gross FROM bank_audit_credit_quality_full "
                "WHERE bank_ticker=? AND period=? AND kind=? AND period_label=?",
                (*key, label))}
        except sqlite3.OperationalError:
            return None
        if not by:
            return None
        out = {}
        if by.get(1) is not None or by.get(2) is not None:
            out["loans_debt"] = (by.get(1) or 0.0) + (by.get(2) or 0.0)
        if by.get(4) is not None:
            out["incl_off_balance"] = by[4]
        return out or None

    def npl_closing(key) -> float | None:
        try:
            rows = [v for (v,) in aud.execute(
                "SELECT closing_balance FROM bank_audit_npl_movement WHERE "
                "bank_ticker=? AND period=? AND kind=? AND period_type='current'",
                key) if v is not None]
        except sqlite3.OperationalError:
            return None
        return sum(rows) if rows else None

    def close(a, b, rel=1e-3):
        return abs(a - b) <= max(2.0, rel * abs(b))

    detected = written = gated = 0
    inst_count: Counter = Counter()
    convs: Counter = Counter()
    a_close_cr1 = [0, 0]
    a_open_cr1 = [0, 0]
    a_close_npl = [0, 0]
    a_prior_col = [0, 0]
    perimeters: Counter = Counter()
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        gated += got["gated"]
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            convs[inst[0]["convention"]] += 1
            if any(x["amount_prior"] is not None for x in inst):
                a_prior_col[1] += 1
                a_prior_col[0] += int(convention_of(inst, "amount_prior") is not None)
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        c6, c1 = cur.get(6, {}).get("amount"), cur.get(1, {}).get("amount")
        if c6 is not None:
            ref = cr1_defaulted(key, "current")
            if ref:
                a_close_cr1[1] += 1
                hit = next((p for p, v in ref.items() if close(c6, v)), None)
                a_close_cr1[0] += int(hit is not None)
                perimeters[hit or "neither"] += 1
                if hit is None and len(mism) < 8:
                    mism.append((key, "closing vs CR1", c6, ref["loans_debt"]))
            ref = npl_closing(key)
            if ref is not None:
                a_close_npl[1] += 1
                a_close_npl[0] += int(close(c6, ref))
        if c1 is not None:
            ref = cr1_defaulted(key, "prior")
            if ref:
                a_open_cr1[1] += 1
                a_open_cr1[0] += int(any(close(c1, v) for v in ref.values()))
        if out is not None:
            out.execute("DELETE FROM bank_audit_defaulted_movement_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_defaulted_movement_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["amount"], x["amount_prior"], x["convention"], x["page"],
                      x["block_id"], got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances refused (balance under no convention): {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
        print(f"conventions: {dict(convs.most_common())}")
    for name, b in (("prior column balances under some convention too", a_prior_col),
                    ("closing vs CR1 current defaulted, either perimeter (0.1%)", a_close_cr1),
                    ("opening vs CR1 prior defaulted, either perimeter (0.1%)", a_open_cr1),
                    ("closing vs narrow NPL closing sum III+IV+V (0.1%)", a_close_npl)):
        print(f"  {name:58} {b[0]:5}/{b[1]:5}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    if perimeters:
        print(f"  CR2 perimeter by filing: {dict(perimeters.most_common())}")
    for key, what, a, b in mism:
        print(f"    {' '.join(key):32} {what}: cr2={a:,.0f} ref={b:,.0f} ({a / b - 1:+.1%})")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_defaulted_movement_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
