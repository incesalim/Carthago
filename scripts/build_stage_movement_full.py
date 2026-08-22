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
    ("opening", R(r"DONEM BASI|ONCEKI DONEM SONU|BEGIN+ING|OPENING|^BALANCES? AT (THE )?(START|BEGIN)")),
    ("closing", R(r"DONEM SONU|^BALANCES? AT (THE )?END|END OF (THE )?PERIOD|PERIOD END|CLOSING")),
    ("transfers_subtotal", R(r"^TRANSFERLER$|^TRANSFERS?$|^ASAMALAR ARASI TRANSFER|^TRANSFERS? BETWEEN (THE )?STAGES")),
    ("transfer_to_stage1", R(r"^1\.? ?ASAMAYA|TRANSFERS? TO STAGE ?1|TO 12.?MONTH")),
    ("transfer_to_stage2", R(r"^2\.? ?ASAMAYA|TRANSFERS? TO STAGE ?2")),
    ("transfer_to_stage3", R(r"^3\.? ?ASAMAYA|TRANSFERS? TO STAGE ?3")),
    ("additions", R(r"^DONEM ICI ILAVE|^DONEM ICINDE ILAVE|^DONEM ICINDE EKLENEN|^ADDITIONS|^NEW (LOANS|ASSETS)|^ORIGINAT|^ILAVE|"
                    r"^PROVISION(S)? (FOR|DURING|MADE)|^CHARGE|^DONEM ICINDE AYRILAN|^NET (CHARGE|PROVISION)|^ADDITIONAL PROVISION")),
    ("derecognised", R(r"^DONEM ICI (CIKAN|KAPANAN)|^DONEM ICINDE (CIKAN|KAPANAN)|^DERECOGNI|^DISPOSAL|^REPAYMENT|^SETTLED|^CLOSED|^REVERSAL|^IPTAL|^COLLECTION|^TAHSILAT")),
    ("sold", R(r"^SATILAN|^SOLD|^SALE|^NPL SALE|^PORTFOLIO SALE")),
    ("written_off", R(r"^AKTIFTEN SILINEN|^KAYITTAN DUSULEN|^WRITE.?OFF|^WRITTEN.?OFF")),
    ("fx_difference", R(r"^KUR FARK|^KUR KAYNAKLI|^KUR DEGISIM|^KUR ETKISI|^FOREIGN (CURRENCY|EXCHANGE)|^FX|^CURRENCY|^EXCHANGE (RATE )?DIFFERENCE|"
                        r"^TRANSFERS? TO STAGE ?\d? ?(CURRENCY|EXCHANGE|FOREIGN)")),   # ISCTR: the empty stage-3 row merged into the FX row
    ("other", R(r"^DIGER|^OTHER")),
]
_DEDUCT_LABEL = R(r"\(\s*-\s*\)")
_ECL = R(r"KARSILIK|PROVISION|EXPECTED|ECL|BEKLENEN|IMPAIRMENT|ZARAR")
_BARE_TRANSFER = R(r"^(TRANSFERS? TO STAGE|ASAMAYA TRANSFER)$")
_LOANS = R(r"KREDI|LOAN|ALACAK|RECEIVABLE|FINANSMAN")
_NOT_LOANS = R(r"NAKIT|CASH|MENKUL|SECURIT|BILANCO DISI|OFF.?BALANCE|GAYRINAKDI|NON.?CASH|BANKALAR|BANKS")
_STAGES = ("stage1", "stage2", "stage3")


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
    -- 'loans' where the heading or the note above says so, else NULL: the
    -- same three-stage roll-forward is printed for cash, securities and
    -- non-cash exposures too, and only the loan one is comparable with the
    -- narrow bank_audit_stages
    subject      TEXT,
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
    # ZIRAAT / VAKBN stack the prior period under the current one (20-21 rows)
    if not 4 <= len(grid) <= 40:
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    if "opening" not in roles or "closing" not in roles:
        return False
    # the stage vocabulary sits in the header row above the opening (DENIZ
    # prints the movement under a balance table in the same block)
    first = roles.index("opening")
    near = grid[max(0, first - 1):first + 1]
    text = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or "") + " " + " ".join(
        str(c) for r in grid[:3] + near for c in r["cells"] if isinstance(c, str)) + " "
        + " ".join(r["label"] or "" for r in near) + " " + (grid[0]["label"] or ""))
    # "12 Ay" as a stage name, not the "3-12 Ay" of a maturity band
    return bool(re.search(r"ASAMA|STAGE|(?<![\d-])12 AY|(?<![\d-])12.?MONTH|LIFETIME|OMUR BOYU", text))


def _convention(rows: list[dict], step: float) -> str | None:
    """Which sign reading makes closing = opening + Σ movements per stage."""
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    opening = next((x for x in rows if x["role"] == "opening"), None)
    closing = next((x for x in rows if x["role"] == "closing"), None)
    if not opening or not closing:
        return None
    mids = [x for x in rows if x["role"] not in ("opening", "closing")]
    # DENIZ prints "Transferler" over "1. Aşamaya / 2. Aşamaya / 3. Aşamaya":
    # the head is the sub-rows' subtotal and stays out of the sum
    if any(x["role"] == "transfers_subtotal" for x in mids) \
            and sum(x["role"] in ("transfer_to_stage1", "transfer_to_stage2", "transfer_to_stage3") for x in mids) >= 2:
        mids = [x for x in mids if x["role"] != "transfers_subtotal"]
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
                if conv == "deductions_labelled" and (
                        _DEDUCT_LABEL.search(fold(x["label"])) or x["role"] in ("derecognised", "sold", "written_off")):
                    s -= v                 # as printed: VAKBN's negative "çıkanlar" is a reversal
                else:
                    s += v
            checked += 1
            ok += int(close(s, c))
        if checked and ok == checked:
            return conv
    return None


def _row_sums_hold(rows: list[dict], step: float) -> bool:
    """total = Σ stages on ≥90% of the rows that print a total; a table
    without a total column (VAKBN) has nothing to check here and rests on
    the per-stage movement identity alone."""
    if not any(band == "total" for x in rows for band, _v in x["cells"]):
        return True
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


def _live_columns(grid: list[dict]) -> list[int]:
    return BM.live_value_columns([r for r in grid if not BM.is_header_row(r, BANDSET.header_label)])


def _no_total_models(grid: list[dict]) -> list[list[tuple[int, str]]]:
    """VAKBN prints the three stages and no total; ISCTR prints the current
    and the prior period side by side, six stage columns and no totals.
    One model per period, in print order."""
    live = _live_columns(grid)
    if len(live) == 3:
        return [list(zip(live, _STAGES))]
    if len(live) == 6:
        return [list(zip(live[:3], _STAGES)), list(zip(live[3:], _STAGES))]
    return []


def _subject(heading: str | None, grid: list[dict], rows: list[dict]) -> str | None:
    """'loans' where the table says it is the loan roll-forward. The same
    three stages are printed for cash, securities and off-balance-sheet
    exposures, and GARAN's ECL table for one of those read as the loan one
    against the narrow lane's billions."""
    first = next((i for i, r in enumerate(grid) if role_of(r["label"] or "") == "opening"), 0)
    near = grid[max(0, first - 3):first + 1]
    text = " ".join([fold(heading or "")] + [fold(r["label"] or "") for r in near]
                    + [fold(str(c)) for r in near for c in r["cells"] if isinstance(c, str)])
    if _LOANS.search(text) and not _NOT_LOANS.search(text):
        return "loans"
    return None


def _measure(heading: str | None, grid: list[dict], rows: list[dict]) -> str:
    """'ecl' where the heading, the in-grid header rows or the opening row
    speak of provisions; else by the figures: a gross-loan table carries
    most of its closing balance in stage 1, an ECL table does not."""
    first = next((i for i, r in enumerate(grid) if role_of(r["label"] or "") == "opening"), 0)
    near = grid[max(0, first - 1):first + 1]      # the header row right above the opening, not prose further up
    text = " ".join([fold(heading or "")] + [fold(r["label"] or "") for r in near]
                    + [fold(str(c)) for r in near for c in r["cells"] if isinstance(c, str)])
    if _ECL.search(text):
        return "ecl"
    # the figures decide: a gross-loan table carries most of its closing in
    # stage 1, an ECL table does not. Whichever roll-forward row the capture
    # kept whole answers — DUNYAK's closing total is missing and its opening
    # is not, and reading the incomplete one called an ECL table gross loans
    for role in ("closing", "opening"):
        cells = next((dict(x["cells"]) for x in rows if x["role"] == role), {})
        parts = [cells.get(b) for b in _STAGES]
        if all(v is not None for v in parts) and sum(parts):
            return "gross_loans" if parts[0] / sum(parts) >= 0.5 else "ecl"
    return "gross_loans"


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
        # DENIZ prints the movement under a loans / ECL balance table in one
        # block: the grid starts at the header row above the first opening
        first = next((i for i, r in enumerate(grid) if role_of(r["label"] or "") == "opening"), 0)
        if first > 1:
            grid = grid[first - 1:]
        cols = BM.column_model(grid, col_labels, BANDSET, min_named=2)
        models = [cols] if cols is not None else _no_total_models(grid)
        if not models:
            no_header += 1
            continue
        for cols in models:
            rows = []
            for r in grid:
                if BM.is_header_row(r, BANDSET.header_label):
                    continue
                label = (r["label"] or "").strip()
                if not label:
                    continue
                cells = r["cells"]
                if all(c is None or num(c) in (1.0, 2.0, 3.0) for c in cells) and any(c is not None for c in cells) \
                        and re.match(r"(STAGE ?\d?|\d\.? ?ASAMA|CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD)\b",
                                     fold(label).strip()):
                    continue                      # "Stage 1 2 3": the header's digits in a row of their own
                vals = []
                for i, band in cols:
                    v = num(cells[i]) if i < len(cells) else None
                    if factor is not None:
                        v = U.scale_amount(v, factor)
                    vals.append((band, v))
                role = role_of(label)
                if role is None and _BARE_TRANSFER.match(fold(label).strip()):
                    # ISCTR: the stage digit of "Transfer to Stage 1" sits in the first cell
                    n = num(cells[0]) if cells else None
                    if n in (1.0, 2.0, 3.0):
                        role = f"transfer_to_stage{int(n)}"
                rows.append({"label": label, "role": role, "cells": vals, "page": pg, "block_id": bid})
            # one grid may hold the current and the prior movement one under
            # the other: a second opening row starts a new instance
            parts, cur = [], []
            for x in rows:
                if x["role"] == "opening" and any(y["role"] == "closing" for y in cur):
                    parts.append(cur)
                    cur = []
                cur.append(x)
            if cur:
                parts.append(cur)
            for part in parts:
                while part and part[0]["role"] != "opening":
                    part.pop(0)                 # prose captured above the opening row
                if any(x["role"] == "closing" for x in part):
                    last = max(i for i, x in enumerate(part) if x["role"] == "closing")
                    del part[last + 1:]         # and the prose / next table captured below the closing
                # the form has three stages: a table with values in only one
                # of them is another movement note that happens to roll
                bands = {b for x in part for b, v in x["cells"] if b in _STAGES and v is not None}
                if len(bands) < 2:
                    continue
                if part:
                    instances.append({"rows": part, "heading": heading,
                                      "measure": _measure(heading, grid, part),
                                      "subject": _subject(heading, grid, part)})
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
                    "INSERT INTO bank_audit_stage_movement_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, inst["measure"], inst["subject"], inst["convention"], inst["heading"],
                      i, x["label"], x["role"],
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
