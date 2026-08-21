#!/usr/bin/env python
"""The NPL-by-borrower graduation: the NOTES-section table of non-performing
loans by borrower class — loans to individuals and corporates, banks, other
loans and receivables — each as gross, provision and net, by group (III
limited collectibility, IV doubtful, V loss), current and prior, minted
from the document layer.

Stored LONG: one row per (period, borrower class, measure, group). MINT
GATE: net = gross - provision for every (class, group) the filing prints,
per period. Anchor, dry-run (default): Σ gross across classes per group vs
the NPL movement's closing balance for the same group — the narrow
bank_audit_npl_movement and the wide bank_audit_npl_movement_full alike.

`--write` stores into bank_audit_npl_by_borrower_full in
data/bank_audit_tables.db (local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
CLASSES: list[tuple[str, re.Pattern]] = [
    ("individuals_corporates", R(r"GERCEK VE TUZEL|INDIVIDUALS? AND CORPORATE|REAL PERSONS? AND (LEGAL|CORPORATE)|"
                                 r"CORPORATES? AND INDIVIDUAL|INDIVIDUALS AND (LEGAL|COMPANIES)|LOANS (GRANTED )?TO (CUSTOMERS|REAL|INDIVIDUALS)")),
    ("banks", R(r"^BANKALAR|^BANKS|^LOANS TO BANKS|^DUE FROM BANKS")),
    ("other", R(r"^DIGER|^OTHER")),
]
_MEASURE = [("gross", R(r"\(BRUT\)|\(GROSS\)|BRUT|GROSS")),
            ("provision", R(r"KARSILIK|PROVISION|ALLOWANCE|ECL|BEKLENEN ZARAR")),
            ("net", R(r"\(NET\)|NET"))]
# a period head ("Cari Dönem (Net)", "Prior Period (Net)"), never the NPL
# movement's "Önceki Dönem Sonu Bakiyesi"
_MONTHS = (r"OCAK|SUBAT|MART|NISAN|MAYIS|HAZIRAN|TEMMUZ|AGUSTOS|EYLUL|EKIM|KASIM|ARALIK|"
           r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER")
_PERIOD_HEAD = R(r"^(CARI|ONCEKI) DONEM(?! SONU| BASI)|^(CURRENT|PRIOR|PREVIOUS) PERIOD(?! END| BALANCE)|"
                 r"^\d{1,2} (MARCH|JUNE|SEPTEMBER|DECEMBER) (CURRENT|PRIOR) PERIOD|"
                 r"^\d{1,2}[ ./]*(" + _MONTHS + r")[ ./]*\d{4}")        # AKTIF: "31 Mart 2026 (Net)"
_PRIOR = R(r"ONCEKI|PRIOR|PREVIOUS")
_GROUP_HDR = R(r"III|IV|V\b|GRUP|GROUP|SINIRLI|SUPHELI|ZARAR|SUBSTANDARD|DOUBTFUL|UNCOLLECT|LOSS")
GROUPS = ("group_iii", "group_iv", "group_v")


def classify(label: str, last_class: str | None) -> tuple[str | None, str | None]:
    """(borrower class, measure) for a row; a bare "Karşılık Tutarı (-)" takes
    the class of the gross row above it."""
    f = fold(label).strip()
    if _PERIOD_HEAD.search(f):
        return None, None
    cls = next((c for c, rx in CLASSES if rx.search(f)), None)
    if re.search(r"KARSILIK|PROVISION|ALLOWANCE|ECL|BEKLENEN ZARAR", f) and cls in (None, "other") \
            and not re.search(r"KREDI|LOAN|RECEIVABLE|BANKA|BANK", f):
        return last_class, "provision"
    if cls is None:
        return None, None
    measure = next((m for m, rx in _MEASURE if rx.search(f)), None)
    return cls, measure


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_npl_by_borrower_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    period_label TEXT NOT NULL,      -- current / prior
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    borrower_class TEXT,             -- individuals_corporates / banks / other; NULL on a period head
    measure      TEXT,               -- gross / provision / net
    npl_group    TEXT NOT NULL,      -- group_iii / group_iv / group_v
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, period_label, row_order, npl_group)
);
CREATE INDEX IF NOT EXISTS idx_npl_by_borrower_full_cell
  ON bank_audit_npl_by_borrower_full(borrower_class, measure, npl_group);
"""


def _width_ok(grid: list[dict]) -> bool:
    """Three group columns; a fourth and fifth are tolerated only when they
    hold nothing but the digits of a date head (AKTIF) or nothing at all
    (YKBNK's empty lead column)."""
    n = len(grid[0]["cells"])
    if n == 3:
        return True
    if n not in (4, 5):
        return False
    for r in grid:
        if not (r["label"] or "").strip():
            continue                            # a stray page number on a label-less line
        if any(c is not None for c in r["cells"][:-3]) and not _PERIOD_HEAD.search(fold(r["label"] or "").strip()):
            return False
    return True


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not 6 <= len(grid) <= 24 or not _width_ok(grid):
        return False
    labels = [fold(r["label"] or "") for r in grid]
    if not any(_PERIOD_HEAD.search(lab) for lab in labels):
        return False
    cls_rows = sum(1 for lab in labels if any(rx.search(lab) for _c, rx in CLASSES))
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    return cls_rows >= 3 and bool(_GROUP_HDR.search(ctx))


def _periods_of(grid, pg, bid, factor) -> list[dict]:
    """Split the block on its period head rows into {label, rows}."""
    out, cur, cur_label = [], [], None
    last_class = None
    for r in grid:
        label = (r["label"] or "").strip()
        if not label:
            continue
        f = fold(label)
        if _PERIOD_HEAD.search(f):
            if cur:
                out.append({"label": cur_label or ("current" if not out else "prior"), "rows": cur})
            cur = []
            # AKTIF heads its periods with dates: the second date is the prior
            cur_label = "prior" if _PRIOR.search(f) or (out and not re.search(r"CARI|CURRENT", f)) else "current"
            last_class = None
        cls, measure = classify(label, last_class)
        if cls and measure == "gross":
            last_class = cls
        vals = [num(c) for c in r["cells"][-3:]]
        vals = [None] * (3 - len(vals)) + vals
        if factor is not None:
            vals = [U.scale_amount(v, factor) for v in vals]
        cur.append({"label": label, "class": cls, "measure": measure, "cells": dict(zip(GROUPS, vals)),
                    "page": pg, "block_id": bid})
    if cur:
        out.append({"label": cur_label or ("current" if not out else "prior"), "rows": cur})
    return out


def _identity_holds(rows: list[dict], step: float) -> bool:
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    by: dict[tuple[str, str], dict] = {}
    for x in rows:
        if x["class"] and x["measure"]:
            by.setdefault((x["class"], x["measure"]), x["cells"])
    checked = 0
    for cls in {c for c, _m in by}:
        g, p, n = by.get((cls, "gross")), by.get((cls, "provision")), by.get((cls, "net"))
        if not (g and n):
            continue
        for grp in GROUPS:
            if g.get(grp) is None or n.get(grp) is None:
                continue
            prov = (p or {}).get(grp) or 0.0
            if not close(g[grp] - prov, n[grp]):
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
        grid = absorb_inline(json.loads(g), lambda lab: classify(lab, None)[0],
                             keep=lambda lab: bool(_PERIOD_HEAD.search(fold(lab).strip())))
        if _is_family(grid, json.loads(cl or "[]"), heading):
            found.append((pg, bid, grid, unit))
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, grid, _u in found:
        instances.append(_periods_of(grid, pg, bid, factor))
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

    def narrow_closing(key) -> dict[str, float]:
        got = {}
        try:
            for gc, c in aud.execute(
                    "SELECT group_code, closing_balance FROM bank_audit_npl_movement WHERE bank_ticker=? "
                    "AND period=? AND kind=? AND period_type='current'", key):
                g = gmap.get((gc or "").strip().upper())
                if g and c is not None:
                    got.setdefault(g, c)
        except sqlite3.OperationalError:
            pass
        return got

    detected = written = gated = 0
    per_filing: Counter = Counter()
    anchor = [0, 0]
    class_cov = [0, 0]
    unk: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for periods in got["instances"]:
            good = [p for p in periods if _identity_holds(p["rows"], got["step"])]
            gated += len(periods) - len(good)
            if good:
                kept.append(good)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        ref = narrow_closing(key)
        for periods in kept:
            for p in periods:
                for x in p["rows"]:
                    if any(v is not None for v in x["cells"].values()):
                        class_cov[1] += 1
                        class_cov[0] += int(x["class"] is not None or _PERIOD_HEAD.search(fold(x["label"])) is not None)
                        if x["class"] is None and not _PERIOD_HEAD.search(fold(x["label"])):
                            unk[fold(x["label"])[:45]] += 1
                if p["label"] == "current" and ref:
                    gross = defaultdict(float)
                    for x in p["rows"]:
                        if x["measure"] == "gross" and x["class"]:
                            for g, v in x["cells"].items():
                                if v is not None:
                                    gross[g] += v
                    pairs = [(gross[g], ref[g]) for g in GROUPS if g in ref and g in gross]
                    if pairs:
                        anchor[1] += 1
                        anchor[0] += int(all(abs(a - b) <= max(2.0, 1e-3 * abs(b)) for a, b in pairs))
        if out is not None:
            out.execute("DELETE FROM bank_audit_npl_by_borrower_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            for n, periods in enumerate(kept):
                for p in periods:
                    out.executemany(
                        "INSERT INTO bank_audit_npl_by_borrower_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(*key, n, p["label"], i, x["label"], x["class"], x["measure"], g, v, x["page"], x["block_id"], got["unit"])
                         for i, x in enumerate(p["rows"]) for g, v in x["cells"].items()])
                    written += 3 * len(p["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | period instances refused (net ≠ gross − provision): {gated}")
    if per_filing:
        print(f"blocks per filing kept: {dict(sorted(per_filing.items()))}")
    if anchor[1]:
        print(f"  Σ gross per group vs narrow NPL closing (all groups within 0.1%): {anchor[0]}/{anchor[1]} ({anchor[0] / anchor[1]:.1%})")
    if class_cov[1]:
        print(f"  value-bearing rows classified: {class_cov[0]}/{class_cov[1]} ({class_cov[0] / class_cov[1]:.1%})")
    for lab, c in unk.most_common(6):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_npl_by_borrower_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
