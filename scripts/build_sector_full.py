#!/usr/bin/env python
"""The sector graduation: every NOTES table printed on BRSA's sector
template — agriculture (farming, forestry, fishery), industry (mining,
manufacturing, utilities), construction, services (trade, hospitality,
transport, financial, real estate, professional, education, health), other,
total — minted from the document layer, whatever the columns:

  risk_profile     Pillar 3 "risk profile by sector": the 17 exposure
                   classes (class_1 ... class_17) + TL, FC, total
  loans_currency   cash loans by sector: TL, %, FC, % for the current
                   period (+ the prior period alongside at some banks)
  stage_ecl        stage 2 / stage 3 / expected credit loss by sector —
                   the table the narrow bank_audit_loans_by_sector reads
  two_period       a plain current / prior pair

Columns are read off the header (the class numbers 1-17 in the risk
profile's own header row; TP/YP/%, stage words, period words elsewhere)
and stored LONG, one row per (sector row, column). The sector registry is
the narrow lane's own vocabulary (agri_farming, mfg_mining, svc_trade ...).

MINT GATE: the template's hierarchy — agriculture = Σ its items, industry
= Σ its items, services = Σ its items, and total = agriculture + industry
+ construction + services + other — on the first money column. Anchor,
dry-run (default): the stage_ecl family against the narrow lane, item by
item.

`--write` stores into bank_audit_sector_full in data/bank_audit_tables.db
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

# (role, group, pattern) — items first where a group word is contained in
# an item ("İmalat Sanayi" before "Sanayi")
SECTORS: list[tuple[str, str | None, re.Pattern]] = [
    ("agri_farming", "agri_total", re.compile(r"^CIFTCILIK|^FARMING|^LIVESTOCK|^STOCK.?BREED|^AGRICULTURE AND (LIVE|ANIMAL)")),
    ("agri_forestry", "agri_total", re.compile(r"^ORMANCILIK|^FORESTRY")),
    ("agri_fishery", "agri_total", re.compile(r"^BALIKCILIK|^FISH")),
    ("mfg_mining", "mfg_total", re.compile(r"^MADENCILIK|^MINING|^QUARRY")),
    ("mfg_production", "mfg_total", re.compile(r"^IMALAT|^MANUFACTURING|^PRODUCTION")),
    ("mfg_utilities", "mfg_total", re.compile(r"^ELEKTRIK|^ELECTRIC|^ENERGY|^UTILIT|^POWER")),
    ("svc_trade", "svc_total", re.compile(r"^TOPTAN|^WHOLESALE|^RETAIL|^TICARET$|^TRADE$")),
    ("svc_hospitality", "svc_total", re.compile(r"^OTEL|^HOTEL|^ACCOMMODATION|^TOURISM|^RESTAURANT|^HOSPITALITY")),
    ("svc_transport", "svc_total", re.compile(r"^ULASTIRMA|^ULASIM|^TRANSPORT|^LOGISTIC|^COMMUNICATION")),
    ("svc_financial", "svc_total", re.compile(r"^MALI KURULUS|^FINANCIAL INSTITUTION|^FINANCE")),
    ("svc_realestate", "svc_total", re.compile(r"^GAYRIMENKUL|^REAL.?ESTATE|^RENTING")),
    ("svc_professional", "svc_total", re.compile(r"^SERBEST MESLEK|^PROFESSIONAL|^SELF.?EMPLOY")),
    ("svc_education", "svc_total", re.compile(r"^EGITIM|^EDUCATION")),
    ("svc_health", "svc_total", re.compile(r"^SAGLIK|^HEALTH")),
    ("agri_total", None, re.compile(r"^TARIM|^AGRICULT")),
    ("mfg_total", None, re.compile(r"^SANAYI|^INDUSTR")),
    ("construction", None, re.compile(r"^INSAAT|^CONSTRUCTION")),
    ("svc_total", None, re.compile(r"^HIZMETLER|^SERVICES")),
    ("other", None, re.compile(r"^DIGER|^OTHER")),
    ("total", None, re.compile(r"^TOPLAM|^TOTAL")),
]
GROUP_ITEMS = {"agri_total": ("agri_farming", "agri_forestry", "agri_fishery"),
               "mfg_total": ("mfg_mining", "mfg_production", "mfg_utilities"),
               "svc_total": ("svc_trade", "svc_hospitality", "svc_transport", "svc_financial",
                             "svc_realestate", "svc_professional", "svc_education", "svc_health")}
TOP = ("agri_total", "mfg_total", "construction", "svc_total", "other")
_FIRST = re.compile(r"^TARIM|^AGRICULT")


_NUM_PREFIX = re.compile(r"^\d+(\.\d+)*\.?\s+")


def sector_of(label: str) -> tuple[str | None, str | None]:
    f = _NUM_PREFIX.sub("", fold(label).strip())    # "1.1 Çiftçilik" numbers its rows
    for role, group, rx in SECTORS:
        if rx.search(f):
            return role, group
    return None, None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_sector_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    family       TEXT NOT NULL,      -- risk_profile / loans_currency / stage_ecl / npl_provisions / two_period
    instance_no  INTEGER NOT NULL,
    period_label TEXT NOT NULL,      -- current / prior / mixed (both periods side by side)
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    sector       TEXT,               -- the narrow lane's vocabulary; NULL = unknown row
    sector_group TEXT,
    col_order    INTEGER NOT NULL,
    -- the column's meaning: class_1..class_17 / tl / fc / total / tl_pct /
    -- fc_pct / stage2 / stage3 / ecl / current / prior, with a _prior
    -- suffix where the prior period prints alongside; NULL = unread
    column       TEXT,
    col_label    TEXT,
    -- canonical thousand TL (scaled at mint); percentages as printed.
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order, col_order)
);
CREATE INDEX IF NOT EXISTS idx_sector_full_cell
  ON bank_audit_sector_full(family, sector, column);
"""


def _is_header_row(r: dict) -> bool:
    cells = [c for c in r["cells"] if c is not None]
    return bool(cells) and all(isinstance(c, str) and c.strip() != "-" for c in cells)


# the 17 standardised-approach exposure classes, in the regulator's order,
# for a risk profile whose columns are labelled by name instead of number
_CLASS_NAMES = [
    re.compile(r"MERKEZI YONETIM|CENTRAL GOVERNMENT|SOVEREIGN"),
    re.compile(r"BOLGESEL|REGIONAL|LOCAL"),
    re.compile(r"IDARI BIRIM|ADMINISTRATIVE|NON.?COMMERCIAL"),
    re.compile(r"COK TARAFLI|MULTILATERAL"),
    re.compile(r"ULUSLARARASI TESKILAT|INTERNATIONAL ORGANI"),
    re.compile(r"BANKALAR VE ARACI|BANKS AND (BROKER|INTERMEDIAR|SECURITIES)|BANKS AND FINANCIAL"),
    re.compile(r"KURUMSAL|CORPORATE"),
    re.compile(r"PERAKENDE|RETAIL"),
    re.compile(r"IKAMET|RESIDENTIAL"),
    re.compile(r"TICARI AMACLI|COMMERCIAL (REAL|PROPERTY|MORTGAGE|IMMOVABLE)"),
    re.compile(r"TAHSILI GECIKMIS|PAST.?DUE|OVERDUE"),
    re.compile(r"RISKI YUKSEK|HIGH(ER)?.?RISK"),
    re.compile(r"TEMINATLI MENKUL|COVERED BOND|MORTGAGE.?BACKED"),
    re.compile(r"MENKUL KIYMETLES|SECURITI[SZ]ATION|KISA VADELI|SHORT.?TERM"),
    re.compile(r"KOLEKTIF|COLLECTIVE INVESTMENT|MUTUAL FUND"),
    re.compile(r"HISSE SENEDI|EQUITY|SHARE"),
    re.compile(r"DIGER ALACAK|OTHER (RECEIVABLE|ITEM|ASSET|EXPOSURE)|^DIGER$|^OTHER$"),
]


def _classes_from_labels(col_labels: list, ncol: int) -> dict[int, str] | None:
    """Column labels naming the exposure classes, read left to right in the
    regulator's order; the TP / YP / Toplam trio closes the row."""
    out: dict[int, str] = {}
    nxt = 0
    for i in range(min(ncol, len(col_labels))):
        t = fold(str(col_labels[i] or ""))
        if not t:
            continue
        if re.search(r"^TP$|^TL$|^TRL$|^LC$", t):
            out[i] = "tl"
        elif re.search(r"^YP$|^FC$|^FX$", t):
            out[i] = "fc"
        elif re.search(r"^TOPLAM|^TOTAL", t):
            out[i] = "total"
        else:
            for k in range(nxt, len(_CLASS_NAMES)):
                if _CLASS_NAMES[k].search(t):
                    out[i] = f"class_{k + 1}"
                    nxt = k + 1
                    break
    return out if sum(1 for v in out.values() if v.startswith("class_")) >= 8 else None


def _class_header(grid: list[dict]) -> dict[int, str] | None:
    """The risk profile's own header row — 1.0 .. 17.0 then TP YP Toplam."""
    for r in grid:
        cells = r["cells"]
        nums = [(i, c) for i, c in enumerate(cells) if isinstance(c, float) and c.is_integer() and 1 <= c <= 17]
        if len(nums) >= 10 and [c for _i, c in nums] == sorted(c for _i, c in nums):
            out = {i: f"class_{int(c)}" for i, c in nums}
            rest = [i for i in range(len(cells)) if i not in out and i > nums[-1][0]]
            for i in rest:
                t = fold(str(cells[i] or ""))
                if re.search(r"^TP|^TL|^TRL|^LC", t):
                    out[i] = "tl"
                elif re.search(r"^YP|^FC|^FX", t):
                    out[i] = "fc"
                elif re.search(r"TOPLAM|TOTAL", t):
                    out[i] = "total"
            return out
    return None


def column_model(grid: list[dict], col_labels: list, heading: str | None):
    """(family, [(cell index, column name, printed label)]) or None."""
    data = [r for r in grid if not _is_header_row(r)]
    if not data:
        return None
    ncol = max(len(r["cells"]) for r in data)
    counts = [sum(1 for r in data if i < len(r["cells"]) and r["cells"][i] is not None) for i in range(ncol)]
    live = [i for i in range(ncol) if counts[i] >= len(data) / 4]
    if not live:
        return None
    classes = _class_header(grid) if len(live) >= 12 else None
    if classes is None and len(live) >= 12:
        classes = _classes_from_labels(col_labels, ncol)
    if classes is None and len(live) == 20:
        # the regulator's full template: 17 exposure classes then TL, FC,
        # total — read by position when the labels are all "Alacaklar"
        classes = {i: f"class_{k + 1}" for k, i in enumerate(live[:17])}
        classes.update({live[17]: "tl", live[18]: "fc", live[19]: "total"})
    if classes:
        cols = [(i, classes.get(i), str(col_labels[i]) if i < len(col_labels) and col_labels[i] else None)
                for i in live]
        if sum(1 for _i, c, _l in cols if c) >= 10:
            # unnamed columns between named classes take the numbers between
            known = [(k, int(c[6:])) for k, (_i, c, _l) in enumerate(cols) if c and c.startswith("class_")]
            for (ka, na), (kb, nb) in zip(known, known[1:]):
                if kb - ka == nb - na:
                    for step in range(1, kb - ka):
                        i, _c, lab = cols[ka + step]
                        cols[ka + step] = (i, f"class_{na + step}", lab)
            return "risk_profile", cols
    headers = [r for r in grid if _is_header_row(r)]
    # a column live in a quarter of the rows is the base reading; where that
    # admits a phantom the family shapes do not recognise (QNBFB and VAKBN
    # print a dead column between every pair, live in a fifth of the rows
    # because the capture parks stray cells there), a half-of-the-rows
    # reading is tried too
    strict = [i for i in range(ncol) if counts[i] >= len(data) / 2]
    for live in ([live] if strict == live or not strict else [live, strict]):
        model = _named_family(grid, col_labels, heading, headers, live)
        if model is not None:
            return model
    return None


def _named_family(grid: list[dict], col_labels: list, heading: str | None,
                  headers: list[dict], live: list[int]):
    frags = {}
    for i in live:
        toks = [str(r["cells"][i]) for r in headers if i < len(r["cells"]) and r["cells"][i]]
        if i < len(col_labels) and col_labels[i]:
            toks.append(str(col_labels[i]))
        frags[i] = fold(" ".join(toks))
    htext = fold(" ".join(frags.values()) + " " + (heading or ""))
    n = len(live)
    if re.search(r"\b(TP|YP|TL|FC|FX|TRL|LC)\b|\(%\)|%", htext) and n in (2, 4, 8):
        names = {2: ["tl", "fc"], 4: ["tl", "tl_pct", "fc", "fc_pct"],
                 8: ["tl", "tl_pct", "fc", "fc_pct", "tl_prior", "tl_pct_prior", "fc_prior", "fc_pct_prior"]}[n]
        if n == 4 and not re.search(r"%", htext) and re.search(r"ONCEKI|PRIOR|PREVIOUS", htext):
            names = ["tl", "fc", "tl_prior", "fc_prior"]
        return "loans_currency", [(i, nm, frags[i] or None) for i, nm in zip(live, names)]
    if re.search(r"TAKIPTEKI|NON.?PERFORMING|NPL|DONUK", htext) and n in (2, 4):
        names = {2: ["npl", "stage3_provision"],
                 4: ["npl", "stage3_provision", "npl_prior", "stage3_provision_prior"]}[n]
        return "npl_provisions", [(i, nm, frags[i] or None) for i, nm in zip(live, names)]
    if re.search(r"STAGE|ASAMA|KARSILIK|PROVISION|ECL|EXPECTED|BEKLENEN|TFRS 9|IFRS 9", htext) or n in (3, 6):
        if n == 3:
            names = ["stage2", "stage3", "ecl"]
        elif n == 6:
            names = ["stage2", "stage3", "ecl", "stage2_prior", "stage3_prior", "ecl_prior"]
        elif n == 4 and re.search(r"STAGE 1|ASAMA 1|1\. ASAMA|FIRST STAGE", htext):
            names = ["stage1", "stage2", "stage3", "ecl"]
        else:
            return None
        return "stage_ecl", [(i, nm, frags[i] or None) for i, nm in zip(live, names)]
    if n == 2:
        return "two_period", [(live[0], "current", frags[live[0]] or None), (live[1], "prior", frags[live[1]] or None)]
    return None


def _is_family(grid: list[dict]) -> bool:
    if len(grid) < 8:
        return False
    roles = [sector_of(r["label"] or "")[0] for r in grid]
    groups = sum(1 for g in ("agri_total", "mfg_total", "construction", "svc_total") if g in roles)
    return _FIRST.search(fold(grid[0]["label"] or "").strip()) is not None or (
        groups >= 3 and "total" in roles)


def _hierarchy_holds(rows: list[dict], col: str, step: float) -> bool:
    by: dict[str, float | None] = {}
    for x in rows:
        if x["sector"] and x["sector"] not in by:
            by[x["sector"]] = dict(x["cells"]).get(col)
    tot = by.get("total")
    if tot is None:
        return False

    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))

    for g, items in GROUP_ITEMS.items():
        head = by.get(g)
        parts = [by[i] for i in items if by.get(i) is not None]
        if head is not None and len(parts) >= 2 and not close(sum(parts), head):
            return False
    parts = [by[t] for t in TOP if by.get(t) is not None]
    return len(parts) >= 3 and close(sum(parts), tot)


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid = absorb_inline(json.loads(g), lambda lab: sector_of(lab)[0])
        if _is_family(grid):
            found.append((pg, bid, heading, json.loads(cl or "[]"), grid, unit))
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances, unread = [], 0
    for pg, bid, heading, col_labels, grid, _u in found:
        model = column_model(grid, col_labels, heading)
        if model is None:
            unread += 1
            continue
        fam, cols = model
        rows, pending = [], ""
        for r in grid:
            if _is_header_row(r):
                continue
            label = (r["label"] or "").strip()
            if not label:
                continue
            if r["cells"] and all(c is None for c in r["cells"]):
                pending = (pending + " " + label).strip()      # a wrapped head
                continue
            if pending:
                label, pending = pending + " " + label, ""
            sector, group = sector_of(label)
            cells = r["cells"]
            vals = []
            for i, name, _lab in cols:
                v = num(cells[i]) if i < len(cells) else None
                if factor is not None and name and not name.endswith("pct"):
                    v = U.scale_amount(v, factor)
                vals.append((name, v))
            rows.append({"label": label, "sector": sector, "group": group, "cells": vals,
                         "page": pg, "block_id": bid})
        # an English template prints the industry group as "Manufacturing"
        # and its item as "Production": two mfg_production rows, no group
        secs = [x["sector"] for x in rows]
        # a group row whose label the capture replaced with a header fragment
        # sits right before its first item: agriculture before farming
        for g, items in GROUP_ITEMS.items():
            if g not in secs and items[0] in secs:
                k = secs.index(items[0])
                if k > 0 and secs[k - 1] is None and any(v is not None for _n, v in rows[k - 1]["cells"]):
                    rows[k - 1]["sector"], rows[k - 1]["group"] = g, None
                    secs[k - 1] = g
        if secs.count("mfg_production") >= 2 and "mfg_total" not in secs:
            first = secs.index("mfg_production")
            rows[first]["sector"], rows[first]["group"] = "mfg_total", None
        if rows:
            instances.append({"family": fam, "cols": cols, "rows": rows, "heading": heading,
                              "period_label": ("mixed" if any(c[1] and c[1].endswith("_prior") for c in cols)
                                               else None)})
    return {"unit": unit, "step": float(factor or 1.0), "unread": unread, "instances": instances}


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

    def narrow(key) -> dict[str, tuple]:
        try:
            return {s: (s2, s3, e) for s, s2, s3, e in aud.execute(
                "SELECT sector, stage2_amount, stage3_amount, ecl_amount FROM "
                "bank_audit_loans_by_sector WHERE bank_ticker=? AND period=? AND kind=? "
                "AND period_type='current'", key)}
        except sqlite3.OperationalError:
            return {}

    detected = written = gated = unread = 0
    fams: Counter = Counter()
    anchor = [0, 0]
    anchor_cells = [0, 0]
    sector_cov = [0, 0]
    unk: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        unread += got["unread"]
        kept = []
        order: Counter = Counter()
        for inst in got["instances"]:
            names = [c[1] for c in inst["cols"] if c[1] and not c[1].endswith("pct")]
            first = ("total" if "total" in names else "tl" if "tl" in names
                     else names[0] if names else None)
            if first is None or not _hierarchy_holds(inst["rows"], first, got["step"]):
                gated += 1
                continue
            fam = inst["family"]
            if inst["period_label"] is None:
                inst["period_label"] = "current" if order[fam] == 0 else "prior" if order[fam] == 1 else "extra"
            order[fam] += 1
            fams[fam] += 1
            kept.append(inst)
            for x in inst["rows"]:
                if any(v is not None for _n, v in x["cells"]):
                    sector_cov[1] += 1
                    sector_cov[0] += int(x["sector"] is not None)
                    if x["sector"] is None:
                        unk[fold(x["label"])[:40]] += 1
            if fam == "stage_ecl" and inst["period_label"] == "current":
                ref = narrow(key)
                if ref:
                    hits = n = 0
                    for x in inst["rows"]:
                        if x["sector"] in ref:
                            c = dict(x["cells"])
                            for nm, rv in zip(("stage2", "stage3", "ecl"), ref[x["sector"]]):
                                if rv is not None and c.get(nm) is not None:
                                    n += 1
                                    hits += int(abs(c[nm] - rv) <= max(2.0, 1e-3 * abs(rv)))
                    if n:
                        anchor[1] += 1
                        anchor[0] += int(hits / n >= 0.9)
                        anchor_cells[1] += n
                        anchor_cells[0] += hits
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_sector_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            for inst in kept:
                n = n_by[inst["family"]]
                n_by[inst["family"]] += 1
                labels = {c[1]: c[2] for c in inst["cols"]}
                out.executemany(
                    "INSERT INTO bank_audit_sector_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, inst["period_label"], inst["heading"], i, x["label"],
                      x["sector"], x["group"], k, nm, labels.get(nm), v, x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for k, (nm, v) in enumerate(x["cells"])])
                written += sum(len(x["cells"]) for x in inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks with unreadable columns: "
          f"{unread} | instances gated out by the sector hierarchy: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams.most_common())}")
    print(f"  stage_ecl vs narrow loans_by_sector: filings ≥90% cells equal {anchor[0]}/{anchor[1]}"
          + (f" ({anchor[0] / anchor[1]:.1%})" if anchor[1] else "")
          + f"; cells {anchor_cells[0]}/{anchor_cells[1]}"
          + (f" ({anchor_cells[0] / anchor_cells[1]:.1%})" if anchor_cells[1] else ""))
    if sector_cov[1]:
        print(f"  value-bearing rows with a sector: {sector_cov[0]}/{sector_cov[1]} ({sector_cov[0] / sector_cov[1]:.1%})")
    for lab, c in unk.most_common(8):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_sector_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
