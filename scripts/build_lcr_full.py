#!/usr/bin/env python
"""The LCR graduation: the full Liquidity Coverage Ratio template, minted from
the document layer.

Second lane after the capital pilot, same architecture, one structural gift the
own-funds table lacked: BRSA NUMBERS the LCR template's rows (1-23) and the
capture keeps that number as the row's first cell — so `template_row` is the
cross-bank, cross-language join key, and no label regex has to carry identity.
The narrow `bank_audit_liquidity` keeps two numbers of this disclosure
(`lcr_total`, `lcr_fc` — the weighted pair of row 23); the wide lane keeps all
23 rows x 4 value columns (unweighted/weighted x TL+FC/FC), for BOTH printed
tables — the filing discloses the current quarter's averages and the prior
quarter's in full.

Assembly:

  detect    a block is LCR-ish when its numbered rows carry the template's
            signature rows (1 HQLA / 21 total HQLA / 22 net outflows /
            23 LCR%). The monthly-averages mini table and the NSFR template
            (rows to 34) never match: months carry no numbers, and NSFR's
            row 23 is not the LCR row.
  instances the filing prints current-period and prior-period tables in full,
            each possibly split across blocks. A row number <= the running
            maximum starts the next instance: first instance = current,
            second = prior (the printed order), confirmed by the anchor.
  columns   last four cells are [unweighted TL+FC, unweighted FC,
            weighted TL+FC, weighted FC]; the row number itself is cell 0.
  scaling   money rows scale declared_unit -> canonical bin; template row 23
            is the ratio row (percent), never scaled. "-" stays NULL.

Validators, dry-run (default):
  - current row 23 weighted pair == narrow lcr_total / lcr_fc (the served
    figures anchor the graduation, like the capital pilot);
  - the template's own identity: LCR = total HQLA (21) / net outflows (22),
    checked on both the TL+FC and FC columns;
  - the PRIOR instance's row 23 against the prior YEAR-END's narrow row (the
    template's Onceki Donem re-prints December, like the fx lane's prior
    column) — a cross-period anchor no single-filing check can fake.

`--write` stores into bank_audit_lcr_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).

  python scripts/build_lcr_full.py                      # fleet dry-run
  python scripts/build_lcr_full.py --bank AKBNK --period 2026Q1 --verbose
  python scripts/build_lcr_full.py --write
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

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")


def fold(s: str | None) -> str:
    return (s or "").translate(_TR_FOLD).upper()


# Signature rows that make a numbered block THE LCR template. Checked against
# the row's own printed number, so an NSFR row 23 (which exists) cannot match.
_SIG = {
    1: re.compile(r"YUKSEK KALITELI LIKIT VARLIK|HIGH.?QUALITY LIQUID ASSET"),
    21: re.compile(r"TOPLAM YKLV|TOTAL HQLA|TOPLAM YUKSEK KALITELI"),
    22: re.compile(r"TOPLAM NET NAKIT CIKIS|TOTAL NET CASH OUTFLOW"),
    23: re.compile(r"LIKIDITE KARSILAMA ORANI|LIQUIDITY COVERAGE RATIO"),
}
# Canonical roles for the template rows every consumer will reach for.
ROLE_BY_ROW = {
    1: "hqla", 2: "retail_deposits", 3: "stable_deposits",
    4: "less_stable_deposits", 5: "unsecured_wholesale_funding",
    6: "operational_deposits", 7: "non_operational_deposits",
    9: "secured_funding", 16: "total_cash_outflows",
    20: "total_cash_inflows", 21: "total_hqla",
    22: "total_net_cash_outflows", 23: "lcr",
}
_ROW_IN_LABEL = re.compile(r"^(\d{1,2})\s+\S")


def _rowno(r: dict) -> int | None:
    """The template row number: the row's first cell, or the label's prefix."""
    cells = r["cells"]
    if cells and isinstance(cells[0], (int, float)) and 1 <= cells[0] <= 23 \
            and float(cells[0]).is_integer():
        return int(cells[0])
    m = _ROW_IN_LABEL.match(r["label"] or "")
    if m and 1 <= int(m.group(1)) <= 23:
        return int(m.group(1))
    return None


def _num(cell) -> float | None:
    return float(cell) if isinstance(cell, (int, float)) else None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    """Both LCR instances (current, prior) of one partition, or None."""
    blocks = tab.execute(
        "SELECT page, block_id, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    lcrish: list[tuple] = []
    for pg, bid, g, unit in blocks:
        grid = json.loads(g)
        sig = 0
        for r in grid:
            n = _rowno(r)
            if n in _SIG and _SIG[n].search(fold(r["label"])):
                sig += 1
        if sig:
            lcrish.append((pg, bid, grid, unit, sig))
    if not lcrish:
        return None
    # The template proper needs the bottom signature rows somewhere; a stray
    # cross-reference block with one look-alike row is not a table.
    if sum(s for *_x, s in lcrish) < 2:
        return None

    unit = lcrish[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances: list[list[dict]] = [[]]
    last_no = 0
    for pg, bid, grid, _u, _s in lcrish:
        for r in grid:
            n = _rowno(r)
            if n is None:
                continue
            label = re.sub(r"^\d{1,2}\s+", "", (r["label"] or "").strip())
            if not label:
                continue
            if n <= last_no and instances[-1]:
                instances.append([])
            last_no = n
            # Drop the row-number cell before taking the value columns, or a
            # narrow block hands the number itself to a value slot.
            body = r["cells"]
            if body and isinstance(body[0], (int, float)) and body[0] == n:
                body = body[1:]
            vals = [_num(c) for c in body[-4:]]
            while len(vals) < 4:
                vals.insert(0, None)
            if n != 23:
                if factor is not None:
                    vals = [U.scale_amount(v, factor) for v in vals]
            else:
                # ALBRK prints its LCR with three decimals ("186,610" meaning
                # 186.610%), which the capture's tokenizer read as a grouped
                # INTEGER. The repair keys on that: a misparse is a bare
                # integer >= 10000, while a genuinely enormous LCR — ENPARA's
                # 34,221.52%, a digital bank parked in HQLA — carries its
                # decimals and is left exactly as printed.
                vals = [v / 1000 if v is not None and v >= 10000
                        and float(v).is_integer() else v
                        for v in vals]
            instances[-1].append(
                {"template_row": n, "label": label, "role": ROLE_BY_ROW.get(n),
                 "page": pg, "block_id": bid,
                 "uw_total": vals[0], "uw_fc": vals[1],
                 "w_total": vals[2], "w_fc": vals[3]})
    # An instance must reach the template's bottom to count as a table.
    instances = [i for i in instances if any(x["template_row"] >= 21 for x in i)]
    if not instances:
        return None
    labels = ("current", "prior", "extra2", "extra3")
    return {"unit": unit,
            "instances": {labels[i]: inst
                          for i, inst in enumerate(instances[:4])}}


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_lcr_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    -- which printed table: the filing discloses the current quarter AND the
    -- prior YEAR-END in full; the prior one cross-anchors December's narrow row.
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint); template row 23 carries the
    -- LCR percentages in the weighted pair, never scaled. NULL = printed "-".
    unweighted_total REAL,
    unweighted_fc    REAL,
    weighted_total   REAL,
    weighted_fc      REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_lcr_full_row
  ON bank_audit_lcr_full(template_row);
"""


def _prior_year_end(period: str) -> str:
    """The template's "Onceki Donem" is the prior YEAR-END, not the prior
    quarter — AKBNK's 2022Q2/Q3/Q4 filings all print 203.49, which is 2021Q4.
    The fx_position lane documented the same BRSA convention for its prior
    column, and it is what makes the cross-anchor meaningful for Q2-Q4."""
    return f"{int(period[:4]) - 1}Q4"


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

    def narrow_lcr(key):
        return [(t, f) for t, f in aud.execute(
            "SELECT lcr_total, lcr_fc FROM bank_audit_liquidity "
            "WHERE bank_ticker=? AND period=? AND kind=?", key)
            if t is not None or f is not None]

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_liquidity "
        "WHERE lcr_total IS NOT NULL")}

    detected = written = 0
    inst_count = Counter()
    rows_per = []
    cur_t, cur_f, pri_t = [0, 0], [0, 0], [0, 0]
    ident = [0, 0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            rows_per.append(len(inst))
            by_row: dict = {}
            for x in inst:
                by_row.setdefault(x["template_row"], x)
            # the template's own identity, both columns
            for col in ("w_total", "w_fc"):
                h = by_row.get(21, {}).get(col)
                n = by_row.get(22, {}).get(col)
                r = by_row.get(23, {}).get(col)
                if None not in (h, n, r) and n:
                    d = abs(h / n * 100 - r)
                    ident[2] += 1
                    ident[0] += int(d <= 0.5)
                    ident[1] += int(d <= 10)
        cur = got["instances"].get("current", [])
        r23 = {x["template_row"]: x for x in cur}.get(23, {})
        have = narrow_lcr(key)
        if r23 and have:
            for wide, idx, bucket in ((r23.get("w_total"), 0, cur_t),
                                      (r23.get("w_fc"), 1, cur_f)):
                vals = {h[idx] for h in have if h[idx] is not None}
                if wide is None or not vals:
                    continue
                bucket[1] += 1
                ok = any(abs(wide - v) <= 0.06 for v in vals)
                bucket[0] += int(ok)
                if not ok and len(mism) < 10:
                    mism.append((key, ("lcr_total", "lcr_fc")[idx], wide,
                                 sorted(vals)))
        pri = got["instances"].get("prior", [])
        p23 = {x["template_row"]: x for x in pri}.get(23, {})
        phave = narrow_lcr((key[0], _prior_year_end(key[1]), key[2]))
        if p23.get("w_total") is not None and phave:
            vals = {h[0] for h in phave if h[0] is not None}
            if vals:
                pri_t[1] += 1
                pri_t[0] += int(any(abs(p23["w_total"] - v) <= 0.06
                                    for v in vals))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(got['instances'])} "
                  f"rows={[len(v) for v in got['instances'].values()]} "
                  f"unit={got['unit']}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_lcr_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_lcr_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["uw_total"], x["uw_fc"], x["w_total"], x["w_fc"],
                      x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    import statistics
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"narrow lcr present locally {len(both)}")
    if rows_per:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}; "
              f"rows per instance: median {statistics.median(rows_per):.0f}")
    for name, b in (("current lcr_total vs narrow", cur_t),
                    ("current lcr_fc    vs narrow", cur_f),
                    ("prior   lcr_total vs prior-YEAR-END narrow", pri_t)):
        print(f"  {name:41} {b[0]:4}/{b[1]:4}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    # Row 23 is the AVERAGE OF WEEKLY RATIOS, not the ratio of the averaged
    # rows 21/22 — so exact agreement is not owed. <=0.5 is the tight band;
    # <=10 covers the averaging arithmetic; beyond that is a flagged filing.
    if ident[2]:
        print(f"  identity 23 ~ 21/22:  within 0.5: {ident[0]}/{ident[2]} "
              f"({ident[0] / ident[2]:.1%})   within 10 (weekly-averaging "
              f"band): {ident[1]}/{ident[2]} ({ident[1] / ident[2]:.1%})")
    for key, which, wide, vals in mism:
        print(f"    {' '.join(key):32} {which} wide={wide} narrow={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_lcr_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
