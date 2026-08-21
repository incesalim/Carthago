#!/usr/bin/env python
"""The stage-movement graduation: the TFRS 9 movement tables by stage —
stage 1 (12-month ECL), stage 2 (lifetime, significant increase), stage 3
(credit-impaired), total — for gross loans and for expected credit losses:
opening balance, additions, derecognitions / closings, sold, written off,
transfers to stage 1 / 2 / 3, FX differences, closing balance — minted from
the document layer on the band-matrix machinery (the stages are the bands).

`measure` is read off the block heading and the first row: 'ecl' where it
speaks of provisions / expected credit loss, else 'gross_loans'. Stored
LONG, one row per (movement row, stage); rows carry a registry role, the
label kept.

MINT GATE: total = Σ stages on ≥90% of the value-bearing rows, AND per
stage column closing = opening + Σ movement rows under the sign the filing
prints (signed figures, or positive figures with "(-)" deduction labels —
whichever balances; the convention is recorded).

`--write` stores into bank_audit_stage_movement_full in
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

from src.audit_reports import band_matrix as BM  # noqa: E402
from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.numbered_template import fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

R = re.compile
BANDSET = BM.BandSet(
    bands=[
        ("stage1", R(r"1\.? ?ASAMA|STAGE ?1|12 AY|12.?MONTH|ASAMA 1")),
        ("stage2", R(r"2\.? ?ASAMA|STAGE ?2|ASAMA 2|SIGNIFICANT INCREASE|ONEMLI ARTIS")),
        ("stage3", R(r"3\.? ?ASAMA|STAGE ?3|ASAMA 3|IMPAIRED|TEMERRUT|DEGER KAYBINA")),
    ],
    header_label=R(r"^\d\. ?ASAMA$|^STAGE ?\d$|CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD"),
)
ROLES: list[tuple[str, re.Pattern]] = [
    ("opening", R(r"DONEM BASI|ONCEKI DONEM SONU|BEGINNING|OPENING|^BALANCES? AT (THE )?(START|BEGIN)")),
    ("closing", R(r"DONEM SONU|^BALANCES? AT (THE )?END|END OF (THE )?PERIOD|PERIOD END|CLOSING")),
    ("transfer_to_stage1", R(r"^1\.? ?ASAMAYA|TRANSFERS? TO STAGE ?1|TO 12.?MONTH")),
    ("transfer_to_stage2", R(r"^2\.? ?ASAMAYA|TRANSFERS? TO STAGE ?2")),
    ("transfer_to_stage3", R(r"^3\.? ?ASAMAYA|TRANSFERS? TO STAGE ?3")),
    ("additions", R(r"^DONEM ICI ILAVE|^DONEM ICINDE ILAVE|^ADDITIONS|^NEW (LOANS|ASSETS)|^ORIGINAT|^ILAVE|^PROVISION(S)? (FOR|DURING|MADE)|"
                    r"^CHARGE|^DONEM ICINDE AYRILAN|^NET (CHARGE|PROVISION)")),
    ("derecognised", R(r"^DONEM ICI (CIKAN|KAPANAN)|^DONEM ICINDE (CIKAN|KAPANAN)|^DERECOGNI|^DISPOSAL|^REPAYMENT|^SETTLED|^CLOSED|^REVERSAL|^IPTAL|^COLLECTION|^TAHSILAT")),
    ("sold", R(r"^SATILAN|^SOLD|^SALE")),
    ("written_off", R(r"^AKTIFTEN SILINEN|^KAYITTAN DUSULEN|^WRITE.?OFF|^WRITTEN.?OFF")),
    ("fx_difference", R(r"^KUR FARK|^FOREIGN (CURRENCY|EXCHANGE)|^FX|^CURRENCY")),
    ("other", R(r"^DIGER|^OTHER")),
]
_DEDUCT_LABEL = R(r"\(\s*-\s*\)")
_ECL = R(r"KARSILIK|PROVISION|EXPECTED|ECL|BEKLENEN|IMPAIRMENT|ZARAR")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_stage_movement_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    measure      TEXT NOT NULL,      -- gross_loans / ecl
    convention   TEXT NOT NULL,      -- signed / deductions_labelled
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    band_order   INTEGER NOT NULL,
    band         TEXT,               -- stage1 / stage2 / stage3 / total
    -- AS PRINTED, canonical thousand TL (scaled at mint). NULL = "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order, band_order)
);
CREATE INDEX IF NOT EXISTS idx_stage_movement_full_cell
  ON bank_audit_stage_movement_full(measure, row_role, band);
"""


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not 4 <= len(grid) <= 18:
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    if "opening" not in roles or "closing" not in roles:
        return False
    text = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or "") + " " + " ".join(
        str(c) for r in grid[:3] for c in r["cells"] if isinstance(c, str)) + " " + fold(grid[0]["label"] or ""))
    return bool(re.search(r"ASAMA|STAGE|12 AY|12.?MONTH", text))


def _convention(rows: list[dict], step: float) -> str | None:
    """Which sign reading makes closing = opening + Σ movements per stage."""
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    opening = next((x for x in rows if x["role"] == "opening"), None)
    closing = next((x for x in rows if x["role"] == "closing"), None)
    if not opening or not closing:
        return None
    mids = [x for x in rows if x["role"] not in ("opening", "closing")]
    for conv in ("signed", "deductions_labelled"):
        checked = ok = 0
        for band in ("stage1", "stage2", "stage3", "total"):
            o, c = dict(opening["cells"]).get(band), dict(closing["cells"]).get(band)
            if o is None or c is None:
                continue
            s = o
            for x in mids:
                v = dict(x["cells"]).get(band)
                if v is None:
                    continue
                if conv == "deductions_labelled" and v > 0 and (
                        _DEDUCT_LABEL.search(fold(x["label"])) or x["role"] in ("derecognised", "sold", "written_off")):
                    s -= v
                else:
                    s += v
            checked += 1
            ok += int(close(s, c))
        if checked and ok == checked:
            return conv
    return None


def _row_sums_hold(rows: list[dict], step: float) -> bool:
    checked = ok = 0
    for x in rows:
        c = dict(x["cells"])
        t = c.get("total")
        parts = [c.get(b) for b in ("stage1", "stage2", "stage3") if c.get(b) is not None]
        if t is None or not parts:
            continue
        checked += 1
        ok += int(abs(sum(parts) - t) <= max(2.0 * step, 1e-5 * abs(t)))
    return checked >= 2 and ok / checked >= 0.9


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid, col_labels = json.loads(g), json.loads(cl or "[]")
        if _is_family(grid, col_labels, heading):
            found.append((pg, bid, heading, grid, col_labels, unit))
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances, no_header = [], 0
    for pg, bid, heading, grid, col_labels, _u in found:
        # "Aşama Aşama Aşama Toplam": the stage numbers sat on the header line
        # above; three undigited stage labels are stages 1, 2, 3 in order
        bare = [i for i, c in enumerate(col_labels)
                if re.fullmatch(r"\s*(ASAMA|STAGE)\s*", fold(str(c or "")))]
        if len(bare) == 3:
            col_labels = list(col_labels)
            for n, i in enumerate(bare, start=1):
                col_labels[i] = f"{n}. Aşama"
        cols = BM.column_model(grid, col_labels, BANDSET, min_named=2)
        if cols is None:
            no_header += 1
            continue
        rows = []
        for r in grid:
            if BM.is_header_row(r, BANDSET.header_label):
                continue
            label = (r["label"] or "").strip()
            if not label:
                continue
            cells = r["cells"]
            vals = []
            for i, band in cols:
                v = num(cells[i]) if i < len(cells) else None
                if factor is not None:
                    v = U.scale_amount(v, factor)
                vals.append((band, v))
            rows.append({"label": label, "role": role_of(label), "cells": vals, "page": pg, "block_id": bid})
        # one grid may hold the current and the prior movement one under the
        # other: a second opening row starts a new instance
        parts, cur = [], []
        for x in rows:
            if x["role"] == "opening" and any(y["role"] == "closing" for y in cur):
                parts.append(cur)
                cur = []
            cur.append(x)
        if cur:
            parts.append(cur)
        for part in parts:
            text = fold(heading or "") + " " + fold(part[0]["label"])
            instances.append({"rows": part, "heading": heading,
                              "measure": "ecl" if _ECL.search(text) else "gross_loans"})
    return {"unit": unit, "step": float(factor or 1.0), "no_header": no_header, "instances": instances}


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

    detected = written = gated = no_header = 0
    measures: Counter = Counter()
    convs: Counter = Counter()
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        no_header += got["no_header"]
        kept = []
        for inst in got["instances"]:
            conv = _convention(inst["rows"], got["step"])
            if conv is None or not _row_sums_hold(inst["rows"], got["step"]):
                gated += 1
                continue
            inst["convention"] = conv
            convs[conv] += 1
            measures[inst["measure"]] += 1
            kept.append(inst)
            for x in inst["rows"]:
                if any(v is not None for _b, v in x["cells"]):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_stage_movement_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            for n, inst in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_stage_movement_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, inst["measure"], inst["convention"], inst["heading"], i, x["label"], x["role"],
                      k, b, v, x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for k, (b, v) in enumerate(x["cells"])])
                written += sum(len(x["cells"]) for x in inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks without a readable stage "
          f"header: {no_header} | instances refused by the identities: {gated}")
    if measures:
        print(f"instances kept: {dict(measures)} | conventions: {dict(convs)}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(8):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_stage_movement_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
