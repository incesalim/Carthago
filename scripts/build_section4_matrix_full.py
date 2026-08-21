#!/usr/bin/env python
"""The Section-4 matrices graduation: the three risk-management tables that
share one row template — balance-sheet items for assets and liabilities,
their totals, the gap, and the off-balance-sheet lines — under three
different column sets, minted from the document layer on the shared
band-matrix machinery:

  liquidity_gap  remaining maturity: demand, ≤1m, 1-3m, 3-12m, 1-5y, 5y+,
                 unallocated, total
  repricing      interest-rate sensitivity: ≤1m, 1-3m, 3-12m, 1-5y, 5y+,
                 non-interest-bearing, total
  fx_position    currency: EUR, USD, (GBP, JPY, CHF,) other FC, total

`family` is read off the column vocabulary. Rows carry a label-registry
`row_role` (cash_and_cbrt, banks, fvtpl, money_market, fvoci, loans,
amortised_cost, other_assets, total_assets, bank_deposits, other_deposits,
funds_borrowed, money_market_payables, securities_issued, misc_payables,
other_liabilities, total_liabilities, gap, net_off_balance,
derivative_receivables, derivative_payables, non_cash_loans, ...), the
label kept verbatim. Stored LONG, one row per (item row, band).

MINT GATE: total = Σ bands on ≥90% of the value-bearing rows AND on the
total-assets row. Anchors, dry-run (default): total assets per band vs the
narrow repricing lane's rate-sensitive assets per bucket; total assets per
currency vs the narrow FX-position lane; the liquidity gap's total assets
vs the narrow balance sheet's total assets.

`--write` stores into bank_audit_section4_matrix_full in
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
from src.audit_reports.numbered_template import absorb_inline, fold, num, prior_year_end  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

_HEADER_LABEL = re.compile(r"CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD|PREVIOUS PERIOD|"
                           r"^VARLIKLAR$|^ASSETS$|^YUKUMLULUKLER$|^LIABILITIES$")
_M1 = r"1 AYA KADAR|UP ?TO 1 MONTH|UP TO ONE MONTH|1 MONTH(?! ?[-–])|\b1 AY\b(?! ?[-–])|(?<![\d-])1 AY"
BANDSETS: dict[str, BM.BandSet] = {
    "liquidity_gap": BM.BandSet(
        bands=[
            ("demand", re.compile(r"VADESIZ|DEMAND")),
            ("m1", re.compile(_M1)),
            ("m1_3", re.compile(r"1 ?[-–] ?3 ?(AY|MONTH)|1-3")),
            ("m3_12", re.compile(r"3 ?[-–] ?12 ?(AY|MONTH)|3-12")),
            ("y1_5", re.compile(r"1 ?[-–] ?5 ?(YIL|YEAR)|1-5")),
            ("y5_plus", re.compile(r"5 YIL VE UZERI|5 YIL VE UST|5 YILDAN UZUN|OVER 5|5 YEARS? AND (OVER|ABOVE)|MORE THAN 5|ABOVE 5")),
            ("unallocated", re.compile(r"DAGITILAMAYAN|UNALLOCATED|UNDISTRIBUTED|NOT DISTRIBUTED|NON.?ALLOCA")),
        ],
        header_label=_HEADER_LABEL),
    "repricing": BM.BandSet(
        bands=[
            ("m1", re.compile(_M1)),
            ("m1_3", re.compile(r"1 ?[-–] ?3 ?(AY|MONTH)|1-3")),
            ("m3_12", re.compile(r"3 ?[-–] ?12 ?(AY|MONTH)|3-12")),
            ("y1_5", re.compile(r"1 ?[-–] ?5 ?(YIL|YEAR)|1-5")),
            ("y5_plus", re.compile(r"5 YIL VE UZERI|5 YIL VE UST|5 YILDAN UZUN|OVER 5|5 YEARS? AND (OVER|ABOVE)|MORE THAN 5|ABOVE 5")),
            ("non_interest", re.compile(r"FAIZSIZ|NON.?INTEREST|INTEREST.?FREE|BEARING")),
        ],
        header_label=_HEADER_LABEL),
    "fx_position": BM.BandSet(
        bands=[
            ("eur", re.compile(r"\bEURO?\b|\bAVRO\b")),
            ("usd", re.compile(r"\bUSD\b|ABD DOLARI|US DOLLAR|\bDOLAR\b")),
            ("gbp", re.compile(r"\bGBP\b|STERLIN|POUND")),
            ("chf", re.compile(r"\bCHF\b|ISVICRE|SWISS")),
            ("jpy", re.compile(r"\bJPY\b|\bYEN\b")),
            ("other_fc", re.compile(r"DIGER|OTHER")),
        ],
        header_label=_HEADER_LABEL),
}
_FAMILY_HINT = {
    "fx_position": re.compile(r"\bEURO?\b|\bAVRO\b|\bUSD\b|ABD DOLARI|US DOLLAR"),
    "repricing": re.compile(r"FAIZSIZ|NON.?INTEREST|INTEREST.?FREE|BEARING"),
    "liquidity_gap": re.compile(r"DAGITILAMAYAN|UNALLOCATED|UNDISTRIBUTED|NOT DISTRIBUTED|VADESIZ|DEMAND|5 YIL|5 YEAR|OVER 5"),
}

ROLES: list[tuple[str, re.Pattern]] = [
    ("total_assets", re.compile(r"^TOPLAM VARLIK|^TOTAL ASSETS")),
    ("total_liabilities", re.compile(r"^TOPLAM YUKUMLULUK|^TOTAL LIABILIT")),
    ("gap", re.compile(r"^LIKIDITE \(?(ACIGI|FAZLASI)|^LIQUIDITY \(?(GAP|SURPLUS)|^NET LIKIDITE|^BILANCODAKI (UZUN|KISA)|"
                       r"^NET BILANCO POZISYON|^NET ON.?BALANCE|^ON.?BALANCE SHEET (LONG|SHORT)|^BILANCO ICI (UZUN|KISA)|"
                       r"^TOTAL POSITION|^TOPLAM POZISYON|^NET POZISYON|^NET POSITION|^NET BALANCE SHEET POSITION|"
                       r"^BALANCE SHEET (LONG|SHORT) POSITION|^NET GAP|^GAP$|^LIQUIDITY GAP|^NET LIQUIDITY")),
    ("fx_deposits", re.compile(r"^DOVIZ TEVDIAT|^FOREIGN CURRENCY DEPOSIT|^FX DEPOSIT")),
    ("funds", re.compile(r"^FONLAR$|^FUNDS$")),
    ("net_off_balance", re.compile(r"^NET BILANCO DISI|^NET NAZIM|^NET OFF.?BALANCE|^NAZIM HESAP(LARDAKI)? (UZUN|KISA)|"
                                   r"^OFF.?BALANCE SHEET (LONG|SHORT|POSITION)")),
    ("derivative_receivables", re.compile(r"^TUREV FINANSAL ARACLARDAN ALACAK|^DERIVATIVE (FINANCIAL )?(ASSETS|RECEIVABLE|INSTRUMENTS? ASSETS)|"
                                          r"^FINANCIAL DERIVATIVE ASSETS|^RECEIVABLES FROM DERIVATIVE")),
    ("derivative_payables", re.compile(r"^TUREV FINANSAL ARACLARDAN BORC|^DERIVATIVE (FINANCIAL )?(LIABILIT|PAYABLE|INSTRUMENTS? LIABILIT)|"
                                       r"^FINANCIAL DERIVATIVE LIABILIT|^PAYABLES FROM DERIVATIVE")),
    ("non_cash_loans", re.compile(r"^GAYRINAKDI|^NON.?CASH LOAN")),
    ("cash_and_cbrt", re.compile(r"^NAKIT DEGERLER|^CASH (AND|&)|^CASH, |^NAKIT VE")),
    ("banks", re.compile(r"^BANKALAR$|^BANKALAR(?! MEVDUAT)|^BANKS$|^BANKS(?! DEPOSIT)|^DUE FROM BANKS")),
    ("fvtpl", re.compile(r"^GERCEGE UYGUN DEGER FARKI KAR|^FINANCIAL ASSETS AT FAIR VALUE THROUGH PROFIT|^FVTPL|"
                         r"^ALIM SATIM AMACLI|^TRADING|^FINANCIAL ASSETS (MEASURED )?AT FAIR VALUE THROUGH P")),
    ("money_market_payables", re.compile(r"^PARA PIYASALARINA|^MONEY MARKET (BORROWING|FUNDS|PAYABLE|BALANCES|DEBTS)|^FUNDS FROM MONEY MARKET|"
                                         r"^BORROWINGS FROM MONEY MARKET|^DUE TO MONEY MARKET|^INTERBANK MONEY MARKET TAKINGS")),
    ("money_market", re.compile(r"^PARA PIYASALARINDAN|^MONEY MARKET|^RECEIVABLES FROM MONEY MARKET|^INTERBANK MONEY MARKET")),
    ("fvoci", re.compile(r"^GERCEGE UYGUN DEGER FARKI DIGER|^FINANCIAL ASSETS AT FAIR VALUE THROUGH OTHER|^FVOCI|"
                         r"^SATILMAYA HAZIR|^AVAILABLE.?FOR.?SALE|^FINANCIAL ASSETS (MEASURED )?AT FAIR VALUE THROUGH O")),
    ("loans", re.compile(r"^VERILEN KREDILER|^KREDILER|^LOANS")),
    ("amortised_cost", re.compile(r"^ITFA EDILMIS|^FINANCIAL ASSETS (MEASURED )?AT AMORTI|^AMORTI[SZ]ED COST|"
                                  r"^VADEYE KADAR|^HELD.?TO.?MATURITY|^INVESTMENTS HELD")),
    ("other_assets", re.compile(r"^DIGER VARLIK|^OTHER ASSETS")),
    ("subsidiaries", re.compile(r"^ISTIRAK|^SUBSIDIAR|^ASSOCIATES|^INVESTMENTS? IN (ASSOCIATES|SUBSIDIAR)|^BAGLI ORTAKLIK")),
    ("hedging_derivatives", re.compile(r"^RISKTEN KORUNMA|^HEDGING|^DERIVATIVE FINANCIAL ASSETS (HELD )?FOR HEDG")),
    ("tangible_assets", re.compile(r"^MADDI DURAN|^TANGIBLE|^PROPERTY AND EQUIPMENT|^FIXED ASSETS")),
    ("intangible_assets", re.compile(r"^MADDI OLMAYAN|^INTANGIBLE")),
    # wrap tails whose head the capture lost: "Gerçeğe Uygun Değer Farkı
    # ... Yansıtılan" / "Financial Assets at Fair Value Through ... Income" —
    # resolved fvtpl / fvoci by template order in _instances_of
    ("_fair_value_tail", re.compile(r"^(GELIRE )?(YANSITILAN )?FINANSAL VARLIKLAR$|^INCOME$|^PROFIT OR LOSS$|"
                                    r"^OTHER COMPREHENSIVE INCOME$|^COMPREHENSIVE INCOME$")),
    ("funds_borrowed", re.compile(r"^INSTITUTIONS$|^KURULUSLARDAN SAGLANAN FONLAR|^SAGLANAN FONLAR")),
    ("bank_deposits", re.compile(r"^BANKALAR MEVDUAT|^BANK DEPOSIT|^DEPOSITS FROM BANKS|^INTERBANK DEPOSIT")),
    ("other_deposits", re.compile(r"^DIGER MEVDUAT|^OTHER DEPOSIT|^MEVDUAT|^DEPOSITS")),
    ("funds_borrowed", re.compile(r"^DIGER MALI KURULUS|^ALINAN KREDI|^FUNDS (PROVIDED|BORROWED)|^BORROWINGS|"
                                  r"^FUNDS FROM OTHER FINANCIAL|^LOANS RECEIVED")),
    ("securities_issued", re.compile(r"^IHRAC EDILEN|^MARKETABLE SECURITIES ISSUED|^SECURITIES ISSUED|^DEBT SECURITIES ISSUED|"
                                     r"^BONDS ISSUED|^ISSUED (MARKETABLE )?SECURITIES")),
    ("misc_payables", re.compile(r"^MUHTELIF BORC|^MISCELLANEOUS PAYABLE|^SUNDRY CREDITOR")),
    ("other_liabilities", re.compile(r"^DIGER YUKUMLULUK|^OTHER LIABILIT")),
    ("prior_total_assets", re.compile(r"^ONCEKI DONEM TOPLAM VARLIK|^PRIOR PERIOD TOTAL ASSETS|^PREVIOUS PERIOD TOTAL ASSETS")),
    ("prior_total_liabilities", re.compile(r"^ONCEKI DONEM TOPLAM YUKUMLULUK|^PRIOR PERIOD TOTAL LIABILIT|^PREVIOUS PERIOD TOTAL LIABILIT")),
]
_PRIOR = re.compile(r"ONCEKI|PRIOR|PREVIOUS")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_section4_matrix_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    family       TEXT NOT NULL,        -- liquidity_gap / repricing / fx_position
    instance_no  INTEGER NOT NULL,
    period_label TEXT NOT NULL,        -- current / prior / extra
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    band_order   INTEGER NOT NULL,
    -- the family's bands (see module doc) / total / total_prior; NULL where
    -- the header could not be read.
    band         TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order, band_order)
);
CREATE INDEX IF NOT EXISTS idx_section4_matrix_full_cell
  ON bank_audit_section4_matrix_full(family, row_role, band);
"""


def family_of(grid: list[dict], col_labels: list, heading: str | None) -> str | None:
    """Which of the three matrices a block is, from its column vocabulary."""
    roles = [role_of(r["label"] or "") for r in grid]
    if "total_assets" not in roles and "total_liabilities" not in roles:
        return None
    if not any(x in roles for x in ("loans", "money_market_payables", "money_market", "banks", "cash_and_cbrt")):
        return None
    headers = [r for r in grid if BM.is_header_row(r, _HEADER_LABEL)]
    text = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or "") + " "
                + " ".join(str(c) for r in headers for c in r["cells"] if isinstance(c, str)))
    for fam in ("fx_position", "repricing", "liquidity_gap"):
        if _FAMILY_HINT[fam].search(text):
            return fam
    return None


def _identity_holds(rows: list[dict], step: float) -> bool:
    checked = ok = 0
    ta_ok = None
    for x in rows:
        tot = next((v for b, v in x["cells"] if b == "total"), None)
        parts = [v for b, v in x["cells"] if b not in ("total", "total_prior") and v is not None]
        if tot is None or not parts:
            continue
        hit = abs(sum(parts) - tot) <= max(2.0 * step, 1e-5 * abs(tot))
        checked += 1
        ok += int(hit)
        if x["role"] == "total_assets" and ta_ok is None:
            ta_ok = hit
    return checked >= 4 and ok / checked >= 0.9 and bool(ta_ok)


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid, col_labels = absorb_inline(json.loads(g), role_of), json.loads(cl or "[]")
        if len(grid) < 5:
            continue
        fam = family_of(grid, col_labels, heading)
        if fam:
            found.append((fam, pg, bid, heading, grid, col_labels, unit))
    if not found:
        return None
    # a continuation block — the liabilities half of a matrix broken across
    # a page — has no total-assets row and no header; it joins the family
    # of the nearest block before it when its columns line up
    by_pos = {(pg, bid): fam for fam, pg, bid, *_ in found}
    keyed = sorted(by_pos)
    for pg, bid, heading, cl, g, unit in blocks:
        if (pg, bid) in by_pos:
            continue
        prev = [k for k in keyed if k < (pg, bid) and pg - k[0] <= 1]
        if not prev:
            continue
        grid, col_labels = absorb_inline(json.loads(g), role_of), json.loads(cl or "[]")
        roles = [role_of(r["label"] or "") for r in grid]
        if "total_assets" in roles or not any(
                x in roles for x in ("total_liabilities", "gap", "other_deposits", "bank_deposits",
                                     "money_market_payables", "net_off_balance")):
            continue
        ref = next(b for b in found if (b[1], b[2]) == prev[-1])
        if max((len(r["cells"]) for r in grid), default=0) == max(len(r["cells"]) for r in ref[4]):
            found.append((ref[0], pg, bid, heading, grid, col_labels, unit))
    found.sort(key=lambda b: (b[1], b[2]))
    unit = found[0][6]
    factor = U.UNIT_SCALE.get(unit)
    instances, no_header = [], Counter()
    prev_cols: dict[str, list] = {}
    streams: dict[str, list] = {}
    for fam, pg, bid, heading, grid, col_labels, _u in found:
        bs = BANDSETS[fam]
        cols = BM.column_model(grid, col_labels, bs, min_named=3)
        if cols is None and fam in prev_cols:
            data = [r for r in grid if not BM.is_header_row(r, bs.header_label)]
            ncol = max((len(r["cells"]) for r in data), default=0)
            if ncol and all(i < ncol for i, _b in prev_cols[fam]):
                cols = prev_cols[fam]
        if cols is None:
            no_header[fam] += 1
            continue
        prev_cols[fam] = cols
        streams.setdefault(fam, []).extend((r, cols, pg, bid, heading) for r in grid)
    for fam, stream in streams.items():
        instances.extend(_instances_of(stream, fam, factor, BANDSETS[fam]))
    return {"unit": unit, "step": float(factor or 1.0), "no_header": no_header,
            "instances": instances}


def _instances_of(stream, fam, factor, bs):
    """Split one family's row stream (all its blocks, in page order — a
    matrix broken across a page is one stream) on header rows / a repeated
    total-assets row; the current period prints first, the prior under an
    'Önceki Dönem' header (or as 'Önceki Dönem Toplam Varlıklar' rows)."""
    out, cur = [], []
    hint = None
    heading = None
    seen_ta = False
    pending = ""                     # a wrapped label's head, printed alone
    for r, cols, pg, bid, head in stream:
        if not cur:
            heading = head
        label = (r["label"] or "").strip()
        if label and r["cells"] and all(c is None for c in r["cells"]) \
                and not BM.is_header_row(r, bs.header_label):
            pending = (pending + " " + label).strip()
            continue
        if BM.is_header_row(r, bs.header_label):
            text = fold(label + " " + " ".join(str(c) for c in r["cells"] if isinstance(c, str)))
            if cur and any(x["role"] == "total_assets" for x in cur) and _PRIOR.search(text):
                out.append({"family": fam, "rows": cur, "hint": hint, "heading": heading})
                cur, seen_ta = [], False
            if _PRIOR.search(text):
                hint = "prior"
            elif re.search(r"CARI DONEM|CURRENT PERIOD", text):
                hint = "current"
            continue
        if not label:
            continue
        if pending:
            label = pending + " " + label
            pending = ""
        role = role_of(label)
        if role == "_fair_value_tail":
            # template order: FVTPL prints before money-market placements,
            # FVOCI after them
            seen = {x["role"] for x in cur}
            role = "fvoci" if ("fvtpl" in seen or "money_market" in seen) else "fvtpl"
        if role == "total_assets":
            if seen_ta and cur:
                out.append({"family": fam, "rows": cur, "hint": hint, "heading": heading})
                cur, hint = [], "prior"
            seen_ta = True
        cells = r["cells"]
        vals = []
        for i, band in cols:
            v = num(cells[i]) if i < len(cells) else None
            if factor is not None:
                v = U.scale_amount(v, factor)
            vals.append((band, v))
        cur.append({"label": label, "role": role, "cells": vals, "page": pg, "block_id": bid})
    if cur:
        out.append({"family": fam, "rows": cur, "hint": hint, "heading": heading})
    return out


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

    _BUCKET = {"m1": ("1 AY", "1 MONTH", "UP TO 1"), "m1_3": ("1-3",), "m3_12": ("3-12",),
               "y1_5": ("1-5",), "y5_plus": ("5 Y", "OVER 5"), "non_interest": ("FAIZSIZ", "NON", "INTEREST")}

    def repricing_ref(key, label) -> dict[str, float]:
        k = key if label == "current" else (key[0], prior_year_end(key[1]), key[2])
        got = {}
        try:
            for bucket, ta in aud.execute(
                    "SELECT bucket, rate_sensitive_assets FROM bank_audit_repricing WHERE "
                    "bank_ticker=? AND period=? AND kind=? AND period_type='current'", k):
                fb = fold(bucket or "")
                for band, needles in _BUCKET.items():
                    if any(n in fb for n in needles) and ta is not None:
                        got.setdefault(band, ta)
                        break
        except sqlite3.OperationalError:
            pass
        return got

    def fx_ref(key, label) -> dict[str, float]:
        k = key if label == "current" else (key[0], prior_year_end(key[1]), key[2])
        got = {}
        try:
            for cur, ta in aud.execute(
                    "SELECT currency, on_bs_assets FROM bank_audit_fx_position WHERE "
                    "bank_ticker=? AND period=? AND kind=? AND period_type='current'", k):
                c = fold(cur or "")
                band = ("eur" if "EUR" in c or "AVRO" in c else "usd" if "USD" in c or "DOLAR" in c
                        else "other_fc" if "DIGER" in c or "OTHER" in c else "total" if "TOPLAM" in c or "TOTAL" in c
                        else None)
                if band and ta is not None:
                    got.setdefault(band, ta)
        except sqlite3.OperationalError:
            pass
        return got

    def bs_total_assets(key, label) -> float | None:
        k = key if label == "current" else (key[0], prior_year_end(key[1]), key[2])
        try:
            for name, tot in aud.execute(
                    "SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE "
                    "bank_ticker=? AND period=? AND kind=?", k):
                if tot is not None and re.match(r"^(TOPLAM VARLIKLAR|TOTAL ASSETS)\b", fold(name or "")):
                    return tot
        except sqlite3.OperationalError:
            pass
        return None

    def close(a, b, rel=2e-3):
        return abs(a - b) <= max(2.0, rel * abs(b))

    detected = written = gated = 0
    no_header: Counter = Counter()
    fams: Counter = Counter()
    labels: Counter = Counter()
    anchors = {"repricing": [0, 0], "fx_position": [0, 0], "liquidity_gap": [0, 0]}
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        no_header.update(got["no_header"])
        kept = []
        order: Counter = Counter()
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"]):
                gated += 1
                continue
            fam = inst["family"]
            inst["label"] = inst["hint"] or ("current" if order[fam] == 0 else "prior" if order[fam] == 1 else "extra")
            order[fam] += 1
            fams[fam] += 1
            labels[inst["label"]] += 1
            kept.append(inst)
            ta = next((dict(x["cells"]) for x in inst["rows"] if x["role"] == "total_assets"), None)
            if ta and inst["label"] in ("current", "prior"):
                if fam == "repricing":
                    ref = repricing_ref(key, inst["label"])
                    pairs = [(ta.get(b), v) for b, v in ref.items() if ta.get(b) is not None]
                    if pairs:
                        anchors[fam][1] += 1
                        anchors[fam][0] += int(sum(close(a, v) for a, v in pairs) >= max(1, len(pairs) - 1))
                elif fam == "fx_position":
                    ref = fx_ref(key, inst["label"])
                    pairs = [(ta.get(b), v) for b, v in ref.items() if ta.get(b) is not None]
                    if pairs:
                        anchors[fam][1] += 1
                        anchors[fam][0] += int(sum(close(a, v) for a, v in pairs) >= max(1, len(pairs) - 1))
                else:
                    ref = bs_total_assets(key, inst["label"])
                    if ref and ta.get("total") is not None:
                        anchors[fam][1] += 1
                        anchors[fam][0] += int(close(ta["total"], ref))
            for x in inst["rows"]:
                if any(v is not None for _b, v in x["cells"]):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_section4_matrix_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            n_by_fam: Counter = Counter()
            for inst in kept:
                n = n_by_fam[inst["family"]]
                n_by_fam[inst["family"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_section4_matrix_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, inst["label"], inst["heading"], i, x["label"],
                      x["role"], k, b, v, x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for k, (b, v) in enumerate(x["cells"])])
                written += sum(len(x["cells"]) for x in inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks without a readable "
          f"band header: {dict(no_header)} | instances gated out by total = Σ bands: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams)} | period labels: {dict(labels)}")
    for fam, b in anchors.items():
        what = {"repricing": "total assets per bucket vs narrow repricing",
                "fx_position": "total assets per currency vs narrow fx_position",
                "liquidity_gap": "total assets vs narrow balance sheet"}[fam]
        print(f"  {what:52} {b[0]:5}/{b[1]:5}" + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} "
              f"({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(10):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_section4_matrix_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
