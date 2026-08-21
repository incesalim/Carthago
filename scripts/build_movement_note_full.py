#!/usr/bin/env python
"""The movement-notes graduation: the NOTES-section roll-forwards printed as
opening balance → movements → closing balance, two columns (current, prior)
— minted from the document layer under a family registry:

  securities_movement   opening, FX differences on monetary assets,
                        purchases, disposals (sale / redemption),
                        impairment, valuation effect, closing — printed for
                        FVOCI and for amortised-cost securities
  investment_movement   opening, purchases, bonus shares, dividends from
                        current-year profit, sales / liquidations,
                        revaluation, impairment, closing; then the memo
                        rows capital commitments and share percentage —
                        printed for associates, subsidiaries and joint
                        ventures

Rows carry a registry role, the label kept. MINT GATE, per column: closing
= opening + Σ movement rows under the sign convention the filing prints
(signed figures, or positive figures on deduction rows / "(-)" labels —
whichever balances; recorded). `subject` is decided by the numbers: the
current closing against the narrow balance-sheet lines (FVOCI / amortised
cost; associates / subsidiaries / joint ventures), else 'unknown' with the
heading kept.

`--write` stores into bank_audit_movement_note_full in
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
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
ROLES: list[tuple[str, re.Pattern]] = [
    ("opening", R(r"^DONEM BASI|^BALANCE AT (THE )?BEGINNING|^BEGINNING|^OPENING")),
    ("closing", R(r"^DONEM SONU (DEGERI|TOPLAMI|BAKIYESI)|^DONEM SONU$|^BALANCE AT (THE )?END|^CLOSING|^END OF (THE )?PERIOD|^ENDING")),
    ("share_pct", R(r"^DONEM SONU SERMAYE KATILMA|^SHARE (PERCENTAGE|HOLDING)|^SHAREHOLDING PERCENTAGE|^PARTICIPATION (RATE|PERCENTAGE)")),
    ("capital_commitments", R(r"^SERMAYE TAAHHUT|^CAPITAL COMMITMENT")),
    ("movements_subtotal", R(r"^DONEM ICI HAREKET|^DONEM ICINDEKI HAREKET|^MOVEMENTS? (DURING|IN) (THE )?PERIOD|^MOVEMENTS? DURING")),
    ("fx_difference", R(r"^PARASAL VARLIKLARDA|^FOREIGN (CURRENCY|EXCHANGE) DIFFERENCE|^FX DIFFERENCE|^KUR FARK|^CURRENCY")),
    ("purchases", R(r"^YIL ICINDEKI ALIM|^ALISLAR|^ALIMLAR|^PURCHASES?|^ACQUISITIONS|^ADDITIONS|^DONEM ICI ALIM")),
    ("bonus_shares", R(r"^BEDELSIZ|^BONUS SHARE")),
    ("dividends", R(r"^CARI YIL PAYINDAN|^DIVIDENDS?|^PROFIT FROM CURRENT")),
    ("disposals", R(r"^SATIS VE ITFA|^SATISLAR|^SATIS|^SALES|^DISPOSAL|^REDEMPTION|^ITFA")),
    ("impairment", R(r"^DEGER AZAL|^DEGER DUSUS|^IMPAIRMENT|^PROVISION FOR (IMPAIRMENT|DIMINUTION)|^ALLOWANCE")),
    ("revaluation", R(r"^YENIDEN DEG|^REVALUATION")),
    ("valuation", R(r"^DEGERLEME ETKISI|^DEGERLEME FARK|^VALUATION (EFFECT|DIFFERENCE|INCREASE)|^(INCREASE|CHANGE)S? ?/? ?(DECREASE)?S? IN (FAIR )?VALUE|^FAIR VALUE (CHANGE|DIFFERENCE)|^MARK.?TO.?MARKET")),
    ("transfers", R(r"^TRANSFER|^SINIFLAMA|^RECLASSIFICATION")),
    ("other", R(r"^DIGER|^OTHER")),
]
DEDUCTION_ROLES = {"disposals", "impairment"}
MEMO_ROLES = {"share_pct", "capital_commitments", "movements_subtotal"}   # the subtotal heads its items
_DEDUCT_LABEL = R(r"\(\s*-\s*\)")
_INVESTMENT = R(r"BEDELSIZ|BONUS SHARE|SERMAYE TAAHHUT|CAPITAL COMMITMENT|KATILMA PAYI|SHARE PERCENTAGE|SHAREHOLDING|ISTIRAK|BAGLI ORTAKLIK|ASSOCIATE|SUBSIDIAR|JOINT VENTURE")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_movement_note_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    family       TEXT NOT NULL,      -- securities_movement / investment_movement
    instance_no  INTEGER NOT NULL,
    -- securities: fvoci / amortised_cost / unknown; investments: associates /
    -- subsidiaries / joint_ventures / unknown — decided by the closing
    -- balance against the narrow balance sheet; heading kept alongside
    subject      TEXT NOT NULL,
    convention   TEXT NOT NULL,      -- signed / deductions_labelled
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- AS PRINTED, canonical thousand TL (scaled at mint); share_pct as printed.
    current      REAL,
    prior        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_movement_note_full_cell
  ON bank_audit_movement_note_full(family, subject, row_role);
"""


def _is_family(grid: list[dict]) -> str | None:
    if not 4 <= len(grid) <= 16 or len(grid[0]["cells"]) != 2:
        return None
    roles = [role_of(r["label"] or "") for r in grid]
    if roles[0] != "opening" or "closing" not in roles:
        return None
    text = " | ".join(fold(r["label"] or "") for r in grid)
    return "investment_movement" if _INVESTMENT.search(text) else "securities_movement"


def _convention(rows: list[dict], step: float) -> str | None:
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    opening = next((x for x in rows if x["role"] == "opening"), None)
    closing = next((x for x in rows if x["role"] == "closing"), None)
    if not opening or not closing:
        return None
    mids = [x for x in rows if x["role"] not in ("opening", "closing") and x["role"] not in MEMO_ROLES
            and not x.get("after_closing")]
    for conv in ("signed", "deductions_labelled"):
        checked = ok = 0
        for col in ("current", "prior"):
            o, c = opening[col], closing[col]
            if o is None or c is None:
                continue
            s = o
            for x in mids:
                v = x[col]
                if v is None:
                    continue
                if conv == "deductions_labelled" and v > 0 and (
                        _DEDUCT_LABEL.search(fold(x["label"])) or x["role"] in DEDUCTION_ROLES):
                    s -= v
                else:
                    s += v
            checked += 1
            ok += int(close(s, c))
        if checked and ok == checked:
            return conv
    return None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, item_title, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, item_title, g, unit in blocks:
        grid = absorb_inline(json.loads(g), role_of)
        fam = _is_family(grid)
        if fam:
            found.append((fam, pg, bid, heading, item_title, grid, unit))
    if not found:
        return None
    unit = found[0][6]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for fam, pg, bid, heading, item_title, grid, _u in found:
        rows, seen_closing = [], False
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            role = role_of(label)
            vals = [num(c) for c in r["cells"][-2:]]
            vals = [None] * (2 - len(vals)) + vals
            if factor is not None and role != "share_pct":
                vals = [U.scale_amount(v, factor) for v in vals]
            rows.append({"label": label, "role": role, "current": vals[0], "prior": vals[1],
                         "after_closing": seen_closing, "page": pg, "block_id": bid})
            if role == "closing":
                seen_closing = True
        instances.append({"family": fam, "rows": rows, "heading": heading, "item_title": item_title})
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


_SUBJECTS = {
    "securities_movement": [
        ("fvoci", R(r"^GERCEGE UYGUN DEGER FARKI DIGER KAPSAMLI|^FINANCIAL ASSETS (MEASURED )?AT FAIR VALUE THROUGH OTHER|^SATILMAYA HAZIR|^AVAILABLE.?FOR.?SALE")),
        ("amortised_cost", R(r"^ITFA EDILMIS MALIYETI|^FINANCIAL ASSETS (MEASURED )?AT AMORTI|^VADEYE KADAR|^HELD.?TO.?MATURITY")),
    ],
    "investment_movement": [
        ("associates", R(r"^ISTIRAKLER|^ASSOCIATES|^INVESTMENTS IN ASSOCIATES")),
        ("subsidiaries", R(r"^BAGLI ORTAKLIKLAR|^SUBSIDIARIES|^INVESTMENTS IN SUBSIDIARIES")),
        ("joint_ventures", R(r"^BIRLIKTE KONTROL|^JOINT VENTURES|^ENTITIES UNDER COMMON CONTROL|^JOINTLY CONTROLLED")),
    ],
}


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

    def bs_lines(key) -> list[tuple[str, float]]:
        try:
            return [(fold(n or "").strip(), v) for n, v in aud.execute(
                "SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                "AND period=? AND kind=? AND statement='assets'", key) if v is not None]
        except sqlite3.OperationalError:
            return []

    def subject_of(fam, closing, key) -> str:
        if closing is None:
            return "unknown"
        for name, rx in _SUBJECTS[fam]:
            for label, v in bs_lines(key):
                if rx.search(label) and abs(closing - v) <= max(2.0, 1e-3 * abs(v)):
                    return name
        return "unknown"

    detected = written = gated = 0
    fams: Counter = Counter()
    subjects: Counter = Counter()
    convs: Counter = Counter()
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            conv = _convention(inst["rows"], got["step"])
            if conv is None:
                gated += 1
                continue
            inst["convention"] = conv
            closing = next((x["current"] for x in inst["rows"] if x["role"] == "closing"), None)
            inst["subject"] = subject_of(inst["family"], closing, key)
            fams[inst["family"]] += 1
            subjects[(inst["family"], inst["subject"])] += 1
            convs[conv] += 1
            kept.append(inst)
            for x in inst["rows"]:
                if x["current"] is not None or x["prior"] is not None:
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_movement_note_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            for inst in kept:
                n = n_by[inst["family"]]
                n_by[inst["family"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_movement_note_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, inst["subject"], inst["convention"], inst["heading"], i,
                      x["label"], x["role"], x["current"], x["prior"], x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"])])
                written += len(inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the closing identity: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams)} | conventions: {dict(convs)}")
        print("subjects (closing vs narrow balance sheet): " + ", ".join(
            f"{f}.{s}={c}" for (f, s), c in sorted(subjects.items())))
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(8):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_movement_note_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
