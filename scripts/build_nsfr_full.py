#!/usr/bin/env python
"""The NSFR graduation: the full Net Stable Funding Ratio template, minted
from the document layer.

Third graduated lane, sibling of the LCR builder — BRSA numbers this template
too (rows 1-34), so `template_row` is again the cross-bank join key. The
narrow `bank_audit_liquidity` keeps ONE number of it (`nsfr`); the wide lane
keeps every row across the maturity buckets, for BOTH printed tables (current
quarter and the prior year-end, split on a row-number restart exactly like
the LCR).

What is specific to this template:

  columns   the unweighted buckets [no maturity, <6 months, 6 months-1 year,
            >=1 year] plus the rightmost WEIGHTED TOTAL — but the captured
            blocks carry phantom all-None columns (GARAN a 7th, ALBRK up to
            8), so each block first drops positions no row in the block
            fills, then takes the last five. The weighted total is always
            the rightmost live column; bucket names follow the template's
            printed order (individual bucket HEADERS are often wrap-garbled
            in the capture, the order never is).
  asf       the template prints TOTAL REQUIRED stable funding as numbered row
            33, but the AVAILABLE total's number drifts by filer — it is
            role-mapped by label (`asf_total`), and its printed number is
            kept as data.
  row 34    the NSFR percent — never unit-scaled, with the same
            integer->=10000 three-decimal repair the LCR needed (and the
            same protection for genuinely enormous digital-bank ratios).

Validators, dry-run (default): current row 34 vs narrow `nsfr`; the prior
instance vs the prior YEAR-END's narrow row; and NSFR ~ asf_total /
required(33), reported in two bands like the LCR's identity.

`--write` stores into bank_audit_nsfr_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).

  python scripts/build_nsfr_full.py                      # fleet dry-run
  python scripts/build_nsfr_full.py --bank AKBNK --verbose
  python scripts/build_nsfr_full.py --write
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

# Signature rows that make a numbered block THE NSFR template; the LCR's own
# rows 21-23 can never satisfy these, nor can the LCR builder's satisfy this.
_SIG = {
    1: re.compile(r"OZKAYNAK UNSURLARI|CAPITAL (ITEMS|INSTRUMENTS)"),
    33: re.compile(r"GEREKLI ISTIKRARLI FON|TOTAL REQUIRED STABLE FUNDING"),
    34: re.compile(r"NET ISTIKRARLI FONLAMA ORANI|NET STABLE FUNDING RATIO"),
}
ROLE_BY_ROW = {
    1: "capital_items", 2: "tier1_and_tier2", 3: "other_capital_items",
    4: "retail_deposits", 5: "stable_deposits", 6: "less_stable_deposits",
    32: "off_balance_sheet", 33: "total_required_stable_funding", 34: "nsfr",
}
# The AVAILABLE stable funding total: template row 14, whose label usually
# omits any "total" word ("14 AVAILABLE STABLE FUNDING", 267 of the fleet's
# instances) — so row 14 with an ASF-ish label carries the role, and an
# explicitly-labelled total anywhere still matches as the fallback.
_ASF = re.compile(r"(TOPLAM MEVCUT ISTIKRARLI FON|MEVCUT ISTIKRARLI FONLAMA TOPLAMI|"
                  r"TOTAL AVAILABLE STABLE FUNDING)")
_ASF14 = re.compile(r"AVAILABLE STABLE FUNDING|MEVCUT ISTIKRARLI FON")
_MAX_ROW = 34


def _role_of(n: int, label: str) -> str | None:
    role = ROLE_BY_ROW.get(n)
    if role is None and (_ASF.search(NT.fold(label)) or
                         (n == 14 and _ASF14.search(NT.fold(label)))):
        role = "asf_total"
    return role


# the 34 rows by label, for the banks that print the template without its
# numbers (ING, TEB, ZIRAAT, ANADOLU, AKTIF, ICBCT, FIBA, TSKB...)
_R = re.compile
_BY_LABEL: list[tuple[int | tuple, re.Pattern]] = [
    (34, _R(r"^NET ISTIKRARLI FONLAMA ORANI|^NET STABLE FUNDING RATIO|^NSFR")),
    (33, _R(r"^(TOPLAM )?GEREKLI ISTIKRARLI FON|^TOTAL (REQUIRED STABLE FUNDING|RSF)")),
    (14, _R(r"^(TOPLAM )?MEVCUT ISTIKRARLI FON|^TOTAL (AVAILABLE STABLE FUNDING|ASF)|^AVAILABLE STABLE FUNDING")),
    (2, _R(r"^ANA SERMAYE VE KATKI|^TIER (1|I) AND TIER (2|II)|^REGULATORY CAPITAL")),
    (3, _R(r"^DIGER OZKAYNAK|^OTHER CAPITAL (ITEMS|INSTRUMENTS)")),
    (1, _R(r"^OZKAYNAK UNSURLARI|^CAPITAL (ITEMS|INSTRUMENTS)|^CAPITAL:?$")),
    (5, _R(r"^ISTIKRARLI MEVDUAT|^STABLE DEPOSIT")),
    (6, _R(r"^DUSUK ISTIKRARLI|^LESS STABLE")),
    (4, _R(r"^GERCEK KISI VE PERAKENDE|^RETAIL DEPOSITS? AND DEPOSITS? FROM SMALL|^RETAIL (AND SMALL BUSINESS )?(CUSTOMERS? )?DEPOSIT")),
    (8, _R(r"^OPERASYONEL MEVDUAT|^OPERATIONAL DEPOSIT")),
    (10, _R(r"^BIRBIRLERINE BAGLI VARLIKLARA ESDEGER YUKUMLULUK|^LIABILITIES WITH MATCHING INTERDEPENDENT")),
    (9, _R(r"^DIGER BORCLAR|^OTHER WHOLESALE FUNDING|^OTHER FUNDING")),
    (7, _R(r"^DIGER KISILERE BORCLAR|^WHOLESALE FUNDING|^FUNDING FROM OTHER")),
    (12, _R(r"^TUREV YUKUMLULUKLER$|^TUREV YUKUMLULUKLER \(|^NSFR DERIVATIVE LIABILIT|^DERIVATIVE LIABILITIES$")),
    (13, _R(r"^YUKARIDA YER ALMAYAN DIGER (YUKUMLULUK|OZKAYNAK)|^ALL OTHER LIABILITIES AND (EQUITY|CAPITAL)|^OTHER LIABILITIES AND EQUITY")),
    (11, _R(r"^DIGER YUKUMLULUKLER|^OTHER LIABILITIES")),
    (15, _R(r"^BIRINCI KALITE LIKIT|^YUKSEK KALITELI LIKIT VARLIKLAR( \(|$)|^(TOTAL )?(NSFR )?HIGH.?QUALITY LIQUID|^TOTAL HQLA|^TOTAL NSFR HQLA")),
    (16, _R(r"^KREDI KURULUSLARI VEYA FINANSAL KURULUSLARA DEPO EDILEN|^DEPOSITS HELD AT OTHER FINANCIAL INSTITUTIONS FOR OPERATIONAL")),
    (18, _R(r"^TEMINATI BIRINCI KALITE LIKIT VARLIK OLAN|^PERFORMING LOANS TO FINANCIAL INSTITUTIONS SECURED BY LEVEL 1")),
    (19, _R(r"^KREDI KURULUSLARI VEYA FINANSAL KURULUSLARDAN TEMINATSIZ|^TEMINATSIZ VEYA TEMINATI BIRINCI KALITE|"
            r"^PERFORMING LOANS TO FINANCIAL INSTITUTIONS SECURED BY NON")),
    (20, _R(r"^FINANSAL KURULUS OLMAYAN KURUMSAL|^KREDI KURULUSLARI VEYA FINANSAL KURULUSLAR DISINDAKI|"
            r"^PERFORMING LOANS TO NON.?FINANCIAL CORPORATE")),
    ((21, 23), _R(r"^%?35|^WITH A RISK WEIGHT OF (LESS THAN OR )?EQUAL TO (OR LESS THAN )?35|^RISK WEIGHT (OF )?(LESS THAN OR EQUAL TO )?35")),
    (22, _R(r"^IKAMET AMACLI|^PERFORMING RESIDENTIAL MORTGAGE")),
    (17, _R(r"^CANLI ALACAKLAR|^PERFORMING LOANS AND SECURITIES|^PERFORMING LOANS")),
    (24, _R(r"^YUKSEK KALITELI LIKIT VARLIK NITELIGINI HAIZ OLMAYAN|^SECURITIES THAT ARE NOT IN DEFAULT")),
    (25, _R(r"^BIRBIRLERINE BAGLI YUKUMLULUKLERE ESDEGER VARLIK|^ASSETS WITH MATCHING INTERDEPENDENT")),
    (27, _R(r"^ALTIN DAHIL|^PHYSICAL(LY)? TRADED COMMODIT")),
    (28, _R(r"^TUREV SOZLESMELERIN BASLANGIC TEMINATI|^ASSETS POSTED AS INITIAL MARGIN|^INITIAL MARGIN")),
    (29, _R(r"^TUREV VARLIKLAR|^(NSFR )?DERIVATIVE ASSETS")),
    (30, _R(r"^TUREV YUKUMLULUKLERIN DEGISIM TEMINATI|^(NSFR )?DERIVATIVE LIABILITIES BEFORE DEDUCTION")),
    (31, _R(r"^YUKARIDA YER ALMAYAN DIGER VARLIK|^ALL OTHER ASSETS NOT INCLUDED")),
    (26, _R(r"^DIGER VARLIKLAR|^OTHER ASSETS")),
    (32, _R(r"^BILANCO DISI (BORC|YUKUMLULUK|ISLEM)|^OFF.?BALANCE SHEET (ITEMS|LIABILITIES)")),
]


def _nsfr_gate(rows: list[dict]) -> bool:
    """34 = 14 / 33 on the weighted total, within 0.5 pp or 5% relative —
    94.5% of the numbered instances hold it within 0.06."""
    by = {x["template_row"]: x for x in rows}
    a, r_, n = (by.get(k, {}).get("weighted_total") for k in (14, 33, 34))
    if None in (a, r_, n) or not r_:
        return False
    return abs(a / r_ * 100 - n) <= max(0.5, 0.05 * abs(n))


_TAIL_LINES = [
    (33, re.compile(r"^(TOPLAM )?GEREKLI ISTIKRARLI FON\b"), re.compile(r"^(TOTAL )?REQUIRED STABLE FUNDING\b")),
    (34, re.compile(r"^NET ISTIKRARLI FONLAMA ORANI\b"), re.compile(r"^NET STABLE FUNDING RATIO\b")),
]
_TRAILING = re.compile(r"([-+]?[\d.,]*\d)\s*$")


def parse_printed(text: str) -> float | None:
    """A number as the filing printed it, in either convention: the last
    separator is the decimal point when it has one or two digits after it,
    a thousands separator when it has three ("364,384" is 364384 and
    "142.75" is 142.75; "1.234.567,89" and "1,234,567.89" both parse)."""
    t = text.strip().replace(" ", "")
    if not re.fullmatch(r"[-+]?[\d.,]*\d", t):
        return None
    sign = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("-+")
    dot, comma = t.rfind("."), t.rfind(",")
    cut = max(dot, comma)
    if cut == -1:
        return sign * float(t)
    tail = t[cut + 1:]
    if len(tail) == 3 and (t.count(".") + t.count(",") > 1 or len(t[:cut].replace(".", "").replace(",", "")) >= 1):
        whole = t.replace(".", "").replace(",", "")           # a thousands group
        return sign * float(whole)
    whole = t[:cut].replace(".", "").replace(",", "")
    return sign * float(f"{whole or 0}.{tail}")


def ledger_tail(cap: sqlite3.Connection | None, key: tuple, n_values: int):
    """The template's last two rows where the capture kept them as prose:
    "Gerekli İstikrarlı Fon 364,384" / "Net İstikrarlı Fonlama Oranı (%)
    142.75" are single lines with the figure inside the text (TEB, ICBCT,
    ZIRAAT, AKTIF…). Returns a callback for `assemble_by_label`."""
    if cap is None:
        return None

    def tail(page: int, block_id: int):
        rows = []
        for n, tr, en in _TAIL_LINES:
            hit = None
            for _pg, text in cap.execute(
                    "SELECT page, text FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? "
                    "AND kind=? AND page BETWEEN ? AND ? AND role!='data' ORDER BY page, line_order",
                    (*key, page, page + 1)):
                f = NT.fold(text).strip()
                if not (tr.search(f) or en.search(f)):
                    continue
                m = _TRAILING.search(f)
                v = parse_printed(m.group(1)) if m else None
                if v is not None:
                    hit = (text.strip(), v)         # the FIRST line that carries a figure
                    break
            if hit is None:
                return None
            rows.append((n, hit[0], [None] * (n_values - 1) + [hit[1]]))
        return rows

    return tail


def _period_hint(heading: str | None, grid: list[dict]) -> str | None:
    text = NT.fold(heading or "") + " " + " ".join(NT.fold(r["label"] or "") for r in grid[:8])
    if re.search(r"ONCEKI DONEM|PRIOR PERIOD|PREVIOUS PERIOD", text):
        return "prior"
    if re.search(r"CARI DONEM|CURRENT PERIOD", text):
        return "current"
    return None


def assemble(tab: sqlite3.Connection, key: tuple,
             cap: sqlite3.Connection | None = None) -> dict | None:
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=_MAX_ROW, bottom_row=33, n_values=5,
        percent_rows={34}, role_of=_role_of,
        value_names=("no_maturity", "maturity_lt_6m", "maturity_6m_1y",
                     "maturity_gte_1y", "weighted_total"))
    if got is not None:
        return got
    return NT.assemble_by_label(
        tab, key, labels=_BY_LABEL, n_values=5, percent_rows={34}, open_rows={1, 2},
        close_row=34, min_rows=14, role_of=_role_of,
        value_names=("no_maturity", "maturity_lt_6m", "maturity_6m_1y", "maturity_gte_1y", "weighted_total"),
        gate=_nsfr_gate, period_hint=_period_hint, tail_of=ledger_tail(cap, key, 5))


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_nsfr_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    -- 'current' or 'prior': the filing prints the current quarter AND the
    -- prior YEAR-END in full; the prior cross-anchors December's narrow row.
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- unweighted maturity buckets in the template's printed order, plus the
    -- rightmost weighted total. Canonical thousand TL, scaled at mint; row 34
    -- carries the NSFR percent in weighted_total, never scaled. NULL = "-".
    no_maturity     REAL,
    maturity_lt_6m  REAL,
    maturity_6m_1y  REAL,
    maturity_gte_1y REAL,
    weighted_total  REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_nsfr_full_row
  ON bank_audit_nsfr_full(template_row);
"""


_prior_year_end = NT.prior_year_end


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--capture-db", default=str(REPO / "data" / "bank_audit_capture.db"),
                    help="the capture ledger, for the total-RSF and ratio lines the capture kept as prose")
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    cap = (sqlite3.connect(f"file:{args.capture_db}?mode=ro", uri=True)
           if Path(args.capture_db).exists() else None)
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

    def narrow_nsfr(key):
        return [v for (v,) in aud.execute(
            "SELECT nsfr FROM bank_audit_liquidity WHERE bank_ticker=? AND "
            "period=? AND kind=?", key) if v is not None]

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_liquidity "
        "WHERE nsfr IS NOT NULL")}

    detected = written = 0
    inst_count = Counter()
    rows_per: list[int] = []
    cur_a, pri_a = [0, 0], [0, 0]
    ident = [0, 0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key, cap)
        if got is None:
            continue
        detected += 1
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            rows_per.append(len(inst))
            by_row = {x["template_row"]: x for x in inst}
            asf = next((x["weighted_total"] for x in inst
                        if x["role"] == "asf_total"), None)
            rsf = by_row.get(33, {}).get("weighted_total")
            ratio = by_row.get(34, {}).get("weighted_total")
            if None not in (asf, rsf, ratio) and rsf:
                d = abs(asf / rsf * 100 - ratio)
                ident[2] += 1
                ident[0] += int(d <= 0.5)
                ident[1] += int(d <= 10)
        cur = {x["template_row"]: x
               for x in got["instances"].get("current", [])}
        wide = cur.get(34, {}).get("weighted_total")
        have = narrow_nsfr(key)
        if wide is not None and have:
            cur_a[1] += 1
            ok = any(abs(wide - v) <= 0.06 for v in have)
            cur_a[0] += int(ok)
            if not ok and len(mism) < 10:
                mism.append((key, wide, sorted(set(have))))
        pri = {x["template_row"]: x
               for x in got["instances"].get("prior", [])}
        pwide = pri.get(34, {}).get("weighted_total")
        phave = narrow_nsfr((key[0], _prior_year_end(key[1]), key[2]))
        if pwide is not None and phave:
            pri_a[1] += 1
            pri_a[0] += int(any(abs(pwide - v) <= 0.06 for v in phave))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(got['instances'])} "
                  f"rows={[len(v) for v in got['instances'].values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_nsfr_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_nsfr_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["no_maturity"], x["maturity_lt_6m"],
                      x["maturity_6m_1y"], x["maturity_gte_1y"],
                      x["weighted_total"], x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    import statistics
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"narrow nsfr present locally {len(both)}")
    if rows_per:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}; "
              f"rows per instance: median {statistics.median(rows_per):.0f}")
    for name, b in (("current nsfr vs narrow", cur_a),
                    ("prior   nsfr vs prior-YEAR-END narrow", pri_a)):
        print(f"  {name:38} {b[0]:4}/{b[1]:4}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    if ident[2]:
        print(f"  identity 34 ~ asf/33: within 0.5: {ident[0]}/{ident[2]} "
              f"({ident[0] / ident[2]:.1%})   within 10: {ident[1]}/{ident[2]} "
              f"({ident[1] / ident[2]:.1%})")
    for key, wide, vals in mism:
        print(f"    {' '.join(key):32} wide={wide} narrow={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_nsfr_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
