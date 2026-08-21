#!/usr/bin/env python
"""The NPL-movement graduation: the NOTES-section movement of non-performing
loans by group (III limited collectibility, IV doubtful, V loss) — opening
balance, additions, transfers in from / out to the other groups,
collections, write-offs, sold portfolio (with its corporate / retail / card
/ other split), closing balance, provision, net balance — minted from the
document layer; the table behind the narrow bank_audit_npl_movement lane.

Stored LONG: one row per (movement row, group). Rows carry a registry
role, the label kept verbatim; rows the registry does not know (FX
differences, reclassifications) keep a NULL role and still enter the sums.

MINT GATE, per group on the current instance: net = closing - provision,
AND closing = opening + additions + transfers in - transfers out -
collections - write-offs - sold (signs from the "(+)" / "(-)" the template
prints), tolerating one unregistered row. Anchor, dry-run (default): each
group's opening / closing / provision / net against the narrow lane.

`--write` stores into bank_audit_npl_movement_full in
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
from src.audit_reports.numbered_template import fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
ROLES: list[tuple[str, re.Pattern]] = [
    ("opening", R(r"^ONCEKI DONEM SONU|^DONEM BASI|^PRIOR PERIOD END|^BEGINNING|^OPENING|^BALANCE AT (THE )?BEGINNING|"
                  r"^BALANCES AT (THE )?BEGINNING|^PREVIOUS PERIOD END")),
    ("additions", R(r"^DONEM ICINDE INTIKAL|^ADDITIONS|^TRANSFERS? (DURING|IN THE PERIOD)|^INTIKAL")),
    ("transfers_in", R(r"^DIGER DONUK ALACAK HESAPLARINDAN GIRIS|^TRANSFERS? FROM OTHER|^TRANSFERS? FROM")),
    ("transfers_out", R(r"^DIGER DONUK ALACAK HESAPLARINA CIKIS|^TRANSFERS? TO OTHER|^TRANSFERS? TO")),
    ("collections", R(r"^DONEM ICINDE TAHSILAT|^COLLECTIONS|^TAHSILAT")),
    ("write_offs", R(r"^KAYITTAN DUSULEN|^AKTIFTEN SILINEN|^WRITE.?OFF|^WRITTEN.?OFF")),
    ("sold", R(r"^SATILAN|^SOLD|^PORTFOLIO SALE|^SALES? OF")),
    ("sold_corporate", R(r"^KURUMSAL VE TICARI|^CORPORATE AND COMMERCIAL|^CORPORATE")),
    ("sold_retail", R(r"^BIREYSEL KREDI|^RETAIL LOAN|^CONSUMER LOAN")),
    ("sold_cards", R(r"^KREDI KART|^CREDIT CARD")),
    ("sold_other", R(r"^DIGER$|^OTHER$|^DIGER \(|^OTHER \(")),
    ("fx_difference", R(r"^KUR FARK|^FOREIGN EXCHANGE|^FX (DIFFERENCE|EFFECT)|^CURRENCY")),
    ("closing", R(r"^DONEM SONU BAKIYE|^CURRENT PERIOD END|^BALANCE AT (THE )?END|^END OF (THE )?PERIOD|^PERIOD END|^CLOSING")),
    ("provision", R(r"^KARSILIK|^OZEL KARSILIK|^SPECIFIC PROVISION|^PROVISION|^EXPECTED (CREDIT )?LOSS|^BEKLENEN ZARAR")),
    ("net", R(r"^BILANCODAKI NET|^NET BALANCE|^NET (BOOK )?VALUE|^BILANCO DEGERI")),
]
GROUPS = ("group_iii", "group_iv", "group_v")
SIGNS = {"opening": 1, "additions": 1, "transfers_in": 1, "transfers_out": -1, "collections": -1,
         "write_offs": -1, "sold": -1, "fx_difference": 1}
_GROUP_HDR = R(r"III|IV|V\.|GRUP|GROUP|SINIRLI|SUPHELI|ZARAR|LIMITED|DOUBTFUL|LOSS|UNCOLLECT")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_npl_movement_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    period_label TEXT NOT NULL,      -- current / prior / extra
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    npl_group    TEXT NOT NULL,      -- group_iii / group_iv / group_v
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order, npl_group)
);
CREATE INDEX IF NOT EXISTS idx_npl_movement_full_cell
  ON bank_audit_npl_movement_full(row_role, npl_group);
"""


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not 6 <= len(grid) <= 18 or len(grid[0]["cells"]) != 3:
        return False
    roles = [role_of(r["label"] or "") for r in grid]
    if roles.count("closing") < 1 or "opening" not in roles or "net" not in roles:
        return False
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    return bool(_GROUP_HDR.search(ctx)) or True


def _rows_of(grid, pg, bid, factor):
    rows = []
    for r in grid:
        label = (r["label"] or "").strip()
        if not label:
            continue
        cells = r["cells"]
        if all(isinstance(c, str) and c.strip() != "-" for c in cells if c is not None) and any(cells):
            continue                                          # a header row
        vals = [num(c) for c in cells[-3:]]
        vals = [None] * (3 - len(vals)) + vals
        if factor is not None:
            vals = [U.scale_amount(v, factor) for v in vals]
        rows.append({"label": label, "role": role_of(label), "cells": dict(zip(GROUPS, vals)),
                     "page": pg, "block_id": bid})
    return rows


def _identity_holds(rows: list[dict], step: float) -> bool:
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    by: dict[str, dict] = {}
    for x in rows:
        if x["role"] and x["role"] not in by:
            by[x["role"]] = x["cells"]
    if "closing" not in by:
        return False
    checked = 0
    for g in GROUPS:
        close_v = by["closing"].get(g)
        if close_v is None:
            continue
        prov, net = (by.get("provision") or {}).get(g), (by.get("net") or {}).get(g)
        if prov is not None and net is not None and not close(close_v - prov, net):
            return False
        if by.get("opening", {}).get(g) is None:
            continue
        s = sum(sg * (by[r].get(g) or 0.0) for r, sg in SIGNS.items() if r in by)
        # unregistered rows (a wrapped "Loans (+)" / "Loans (-)", FX
        # differences) enter with the sign the template prints on them
        signed = 0.0
        unsigned = 0.0
        for x in rows:
            v = x["cells"].get(g)
            if x["role"] is not None or v is None:
                continue
            lab = fold(x["label"])
            if re.search(r"\(\s*-\s*\)", lab):
                signed -= v
            elif re.search(r"\(\s*\+\s*\)", lab):
                signed += v
            else:
                unsigned += v
        s += signed
        if not (close(s, close_v) or close(s + unsigned, close_v) or close(s - unsigned, close_v)):
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
        grid, col_labels = json.loads(g), json.loads(cl or "[]")
        if _is_family(grid, col_labels, heading):
            found.append((pg, bid, heading, grid, unit))
    if not found:
        return None
    unit = found[0][4]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, heading, grid, _u in found:
        rows = _rows_of(grid, pg, bid, factor)
        text = fold(heading or "") + " " + fold(rows[0]["label"] if rows else "")
        hint = ("prior" if re.search(r"ONCEKI DONEM\b(?! SONU)|PRIOR PERIOD\b(?! END)|PREVIOUS PERIOD\b(?! END)", text)
                else None)
        instances.append({"rows": rows, "hint": hint, "heading": heading})
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


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

    gmap = {"III": "group_iii", "IV": "group_iv", "V": "group_v"}

    def narrow(key, label) -> dict[tuple[str, str], float]:
        got = {}
        try:
            for gc, o, c, p, n in aud.execute(
                    "SELECT group_code, opening_balance, closing_balance, provision, net_balance "
                    "FROM bank_audit_npl_movement WHERE bank_ticker=? AND period=? AND kind=? "
                    "AND period_type=?", (*key, label)):
                g = gmap.get((gc or "").strip().upper())
                if g:
                    for role, v in (("opening", o), ("closing", c), ("provision", p), ("net", n)):
                        if v is not None:
                            got[(role, g)] = v
        except sqlite3.OperationalError:
            pass
        return got

    detected = written = gated = 0
    per_filing: Counter = Counter()
    labels: Counter = Counter()
    anchor_cells = [0, 0]
    anchor_filings = [0, 0]
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        order = 0
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"]):
                gated += 1
                continue
            inst["label"] = inst["hint"] or ("current" if order == 0 else "prior" if order == 1 else "extra")
            order += 1
            labels[inst["label"]] += 1
            kept.append(inst)
            for x in inst["rows"]:
                if any(v is not None for v in x["cells"].values()):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
            if inst["label"] in ("current", "prior"):
                ref = narrow(key, inst["label"])
                if ref:
                    by: dict[str, dict] = {}
                    for x in inst["rows"]:
                        if x["role"] and x["role"] not in by:
                            by[x["role"]] = x["cells"]
                    hits = n = 0
                    for (role, g), v in ref.items():
                        w = (by.get(role) or {}).get(g)
                        if w is not None:
                            n += 1
                            hits += int(abs(w - v) <= max(2.0, 1e-3 * abs(v)))
                    if n:
                        anchor_cells[0] += hits
                        anchor_cells[1] += n
                        anchor_filings[1] += 1
                        anchor_filings[0] += int(hits == n)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        if out is not None:
            out.execute("DELETE FROM bank_audit_npl_movement_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            for n_i, inst in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_npl_movement_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n_i, inst["label"], i, x["label"], x["role"], g, v, x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for g, v in x["cells"].items()])
                written += 3 * len(inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the identities: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))} | labels: {dict(labels)}")
    if anchor_cells[1]:
        print(f"  vs narrow npl_movement: cells {anchor_cells[0]}/{anchor_cells[1]} ({anchor_cells[0] / anchor_cells[1]:.1%}); "
              f"instances fully equal {anchor_filings[0]}/{anchor_filings[1]} ({anchor_filings[0] / anchor_filings[1]:.1%})")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(8):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_npl_movement_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
