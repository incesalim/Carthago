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
# the same 23 rows by label, for the banks that print the template without
# its numbers (HALKB, ING, YKBNK, ZIRAAT, ANADOLU, HSBC, ICBCT, ISCTR...)
_R = re.compile
_BY_LABEL: list[tuple[int, re.Pattern]] = [
    (21, _R(r"^TOPLAM Y(KLV|UKSEK KALITELI)|^TOTAL (HQLA|HIGH.?QUALITY)")),
    (1, _R(r"^YUKSEK KALITELI LIKIT|^HIGH.?QUALITY LIQUID")),
    (22, _R(r"^TOPLAM NET NAKIT CIKIS|^TOTAL NET CASH OUTFLOW")),
    (23, _R(r"^LIKIDITE KARSILAMA ORANI|^LIQUIDITY COVERAGE RATIO")),
    (16, _R(r"^TOPLAM NAKIT CIKIS|^TOTAL CASH OUTFLOW")),
    (20, _R(r"^TOPLAM NAKIT GIRIS|^TOTAL CASH INFLOW")),
    (3, _R(r"^ISTIKRARLI MEVDUAT|^STABLE DEPOSIT")),
    (4, _R(r"^DUSUK ISTIKRARLI|^LESS STABLE")),
    (5, _R(r"^GERCEK KISI MEVDUAT VE PERAKENDE MEVDUAT DISINDA|^UNSECURED (WHOLESALE )?FUNDING( OTHER THAN)?|"
           r"^UNSECURED FUNDING OTHER|^TEMINATSIZ (TOPTAN )?BORCLAR$")),
    (2, _R(r"^GERCEK KISI MEVDUAT|^RETAIL (AND SMALL BUSINESS )?(CUSTOMERS? )?DEPOSIT|^PERAKENDE MEVDUAT")),
    (7, _R(r"^OPERASYONEL OLMAYAN|^NON.?OPERATIONAL")),
    (6, _R(r"^OPERASYONEL MEVDUAT|^OPERATIONAL DEPOSIT")),
    (8, _R(r"^DIGER TEMINATSIZ|^OTHER UNSECURED")),
    (9, _R(r"^TEMINATLI BORCLAR|^SECURED (FUNDING|BORROWING|DEBT)")),
    (11, _R(r"^TUREV (YUKUMLULUK|BORC)|^DERIVATIVES? (CASH OUTFLOW|LIABILIT|EXPOSURE)|^LIABILITIES RELATED TO DERIVATIVE|"
            r"^OUTFLOWS RELATED TO DERIVATIVE")),
    (12, _R(r"^YAPILANDIRILMIS|^(DEBTS|LIABILITIES|OUTFLOWS|OBLIGATIONS) (RELATED TO |FROM )?STRUCTURED|^STRUCTURED FINANC")),
    (13, _R(r"^FINANSAL PIYASALARA|^(PAYMENT )?COMMITMENTS? (RELATED TO |FOR )?(DEBTS TO )?FINANCIAL MARKET|"
            r"^CREDIT AND LIQUIDITY FACILIT|^OTHER OFF.?BALANCE SHEET (LIABILITIES|OBLIGATIONS)")),
    (14, _R(r"^HERHANGI BIR SARTA BAGLI OLMAKSIZIN CAYILABILIR|^(OTHER )?(UNCONDITIONALLY )?REVOCABLE|^OTHER CONTRACTUAL")),
    (15, _R(r"^DIGER SARTA BAGLI|^OTHER (IRREVOCABLE|CONTINGENT|CONDITIONAL)")),
    (10, _R(r"^DIGER NAKIT CIKIS|^OTHER CASH OUTFLOW|^ADDITIONAL REQUIREMENT")),
    (17, _R(r"^TEMINATLI ALACAK|^SECURED (RECEIVABLE|LENDING)")),
    (18, _R(r"^TEMINATSIZ ALACAK|^UNSECURED (RECEIVABLE|LENDING)|^INFLOWS FROM FULLY PERFORMING")),
    (19, _R(r"^DIGER NAKIT GIRIS|^OTHER CASH INFLOW")),
]


def _lcr_gate(rows: list[dict]) -> bool:
    """23 ≈ 21 / 22 on the weighted total column. The printed LCR is the
    quarter's average of ratios while 21 and 22 are averages of levels, so
    the identity is exact on 76% of the numbered instances and within 10%
    relative on 99.7%: that is the bar (the FC column is not checked — a
    bank with no FC outflows prints a dash)."""
    by = {x["template_row"]: x for x in rows}
    h, n, r = (by.get(k, {}).get("w_total") for k in (21, 22, 23))
    if None in (h, n, r) or not n:
        return False
    return abs(h / n * 100 - r) <= max(5.0, 0.1 * abs(r))


def _period_hint(heading: str | None, grid: list[dict]) -> str | None:
    text = NT.fold(heading or "") + " " + " ".join(NT.fold(r["label"] or "") for r in grid[:4])
    if re.search(r"ONCEKI DONEM|PRIOR PERIOD|PREVIOUS PERIOD", text):
        return "prior"
    if re.search(r"CARI DONEM|CURRENT PERIOD", text):
        return "current"
    return None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    """Both LCR instances (current, prior) of one partition, or None."""
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=23, bottom_row=21, n_values=4,
        percent_rows={23}, role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("uw_total", "uw_fc", "w_total", "w_fc"))
    if got is not None:
        return got
    return NT.assemble_by_label(
        tab, key, labels=_BY_LABEL, n_values=4, percent_rows={23}, open_rows={1, 2},
        close_row=23, min_rows=10, role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("uw_total", "uw_fc", "w_total", "w_fc"), gate=_lcr_gate,
        period_hint=_period_hint)


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


_prior_year_end = NT.prior_year_end


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
