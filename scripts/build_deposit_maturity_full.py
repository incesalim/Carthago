#!/usr/bin/env python
"""The deposits-by-maturity graduation: the NOTES-section matrix of deposits
by type × maturity band (Section 5, liabilities) — the largest notes family
in the document layer, ~1,600 captured blocks across 32 banks — and its
twin of the same shape, interest paid on deposits by maturity (Section 5,
P&L). Both are minted; `measure` tells them apart.

Rows: saving deposits, FX deposit accounts (residents / non-residents),
public, commercial, other, precious metals, bank deposits (CBRT, domestic,
foreign, participation banks, other), 7-day notice, subtotals and the
grand total — label-registry roles, the label kept verbatim, rows the
registry does not know kept with a NULL role. Columns: demand, 7-day notice,
up to 1 month, 1-3, 3-6, 6-12 months, 1 year and over, accumulating, total
— read from the header fragments at each column index and completed from
the canonical order where the capture split the header beyond reading;
stored LONG, one row per (deposit row, band).

MINT GATE: the matrix's own arithmetic — total = Σ bands on ≥90% of the
value-bearing rows AND on the grand-total row. `measure`: the grand total
against the narrow balance sheet's deposits line ('balance') or the narrow
P&L's interest-on-deposits line ('interest_expense'), else 'unknown' with
the heading kept — the same figure on the regulator's own cross-reference.

`--write` stores into bank_audit_deposit_maturity_full in
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

BANDSET = BM.BandSet(
    bands=[
        ("demand", re.compile(r"VADESIZ|DEMAND|CURRENT ACC|OZEL CARI")),
        ("notice_7d", re.compile(r"7 ?GUN|7.?DAY|IHBARLI|NOTICE")),
        ("m1", re.compile(r"1 AYA KADAR|UP TO 1 MONTH|UPTO 1 MONTH|UP TO ONE MONTH|1 MONTH(?! ?[-–])|\b1 AY\b(?! ?[-–])")),
        ("m1_3", re.compile(r"1 ?[-–] ?3 ?(AY|MONTH)|1 TO 3|1-3")),
        ("m3_6", re.compile(r"3 ?[-–] ?6 ?(AY|MONTH)|3 TO 6|3-6")),
        ("m6_12", re.compile(r"6 ?(AY|MONTH)S? ?[-–] ?(1 )?(YIL|YEAR)|6 ?[-–] ?12|6 MONTHS? TO 1|6 AY.?1 YIL|1 YILA KADAR|UP TO 1 YEAR")),
        ("y1_plus", re.compile(r"1 YIL VE UST|1 YILDAN UZUN|OVER 1 YEAR|1 YEAR AND OVER|1 YEAR AND ABOVE|MORE THAN 1 YEAR|ABOVE 1 YEAR|1 YEAR OR MORE|LONGER THAN 1")),
        ("accumulating", re.compile(r"BIRIKIMLI|ACCUMULAT|CUMULATIVE|KATILMA HES")),
    ],
    optional=("notice_7d",),
    header_label=re.compile(r"CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD|PREVIOUS PERIOD|^VADESIZ|^DEMAND"),
)

ROLES: list[tuple[str, re.Pattern]] = [
    ("grand_total", re.compile(r"^GENEL TOPLAM|^GRAND TOTAL|^TOTAL DEPOSITS|^TOPLAM MEVDUAT")),
    ("total", re.compile(r"^TOPLAM|^TOTAL")),
    ("notice_7d", re.compile(r"^7 ?GUN|^7.?DAY")),
    ("saving", re.compile(r"^TASARRUF MEVDUAT|^SAVING")),
    ("fx_resident", re.compile(r"^YURT ?ICINDE YER|^RESIDENTS? (IN|OF) TURK|^DOMESTIC RESIDENT|^YURT ?ICI YERLESIK")),
    ("fx_nonresident", re.compile(r"^YURT ?DISINDA YER|^RESIDENTS? ABROAD|^NON.?RESIDENT|^YURT ?DISI YERLESIK")),
    ("fx_deposit", re.compile(r"^DOVIZ TEVDIAT|^DTH|^FOREIGN CURRENCY DEPOSIT|^FX DEPOSIT|^FC DEPOSIT")),
    ("public", re.compile(r"^RESM[IÎ]|^PUBLIC SECTOR|^OFFICIAL|^PUBLIC DEPOSIT")),
    ("commercial", re.compile(r"^TICARI|^TIC\. KUR|^COMMERCIAL")),
    ("precious_metal", re.compile(r"^KIYMETLI MADEN|^PRECIOUS METAL|^GOLD")),
    ("cbrt", re.compile(r"^TCMB|^CBRT|^CENTRAL BANK|^T\.?C\.? ?MERKEZ")),
    ("domestic_banks", re.compile(r"^YURT ?ICI BANKA|^DOMESTIC BANK")),
    ("foreign_banks", re.compile(r"^YURT ?DISI BANKA|^FOREIGN BANK")),
    ("participation_banks", re.compile(r"^KATILIM BANKA|^PARTICIPATION BANK")),
    ("bank_deposits", re.compile(r"^BANKALAR ?ARASI|^BANKALAR MEVDUAT|^BANKALAR VE KATILIM|^BANK DEPOSIT|^INTERBANK|"
                                 r"^BANKS AND PARTICIPATION|^DEPOSITS FROM BANKS|^BANKS$")),
    ("other", re.compile(r"^DIGER|^DIG\. KUR|^OTHER")),
]
_BANK_GROUP = {"cbrt", "domestic_banks", "foreign_banks", "participation_banks"}
_NOT_FAMILY = re.compile(r"PARA PIYASA|MONEY MARKET|MUHTELIF BORC|MISCELLANEOUS PAYABLE|GAYRINAKDI|"
                         r"NON.?CASH LOAN|\bKREDILER\b|\bLOANS\b|POZISYON|POSITION|MENKUL DEGER|"
                         r"SECURITIES|NAKIT DEGERLER|CASH AND|ALINAN KREDI|FUNDS BORROWED|BORROWINGS")
_PRIOR = re.compile(r"ONCEKI|PRIOR|PREVIOUS")
# the balance-sheet line, allowing the footnote markers the narrow lane keeps
# in the name ("MEVDUAT II-a", "DEPOSITS -a", "DEPOSITS (1)")
_BS_DEPOSITS = re.compile(r"^(MEVDUAT|DEPOSITS?|TOPLANAN FONLAR|FUNDS COLLECTED)"
                          r"(\s+[-–]?\s*[IVXA-Z0-9.()\-]{1,5})*$")
_PL_INTEREST = re.compile(r"MEVDUATA VERILEN FAIZ|INTEREST (EXPENSE )?ON DEPOSIT|INTEREST PAID (ON|TO) DEPOSIT|"
                          r"KATILMA HESAPLARINA VERILEN|PROFIT SHARE (EXPENSE )?ON PARTICIPATION|"
                          r"EXPENSE ON PARTICIPATION ACCOUNT")


def role_of(label: str, in_bank_group: bool) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            if role == "other" and in_bank_group:
                return "other_banks"
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_deposit_maturity_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    -- balance / interest_expense / unknown, decided by the grand total
    -- against the narrow balance sheet and P&L; heading kept alongside.
    measure      TEXT NOT NULL,
    period_label TEXT NOT NULL,      -- current / prior / extra
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    band_order   INTEGER NOT NULL,
    -- demand / notice_7d / m1 / m1_3 / m3_6 / m6_12 / y1_plus / accumulating
    -- / total / total_prior (a trailing prior-period total column, where a
    -- bank prints one); NULL where the header could not be read.
    band         TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order, band_order)
);
CREATE INDEX IF NOT EXISTS idx_deposit_maturity_full_cell
  ON bank_audit_deposit_maturity_full(measure, row_role, band);
"""


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if len(grid) < 6:
        return False
    text = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or "") + " "
                + " ".join(str(c) for r in grid[:4] for c in r["cells"] if isinstance(c, str)))
    if not re.search(r"VADESIZ|DEMAND|7 ?GUN|7.?DAY|BIRIKIMLI|ACCUMULAT|AYA KADAR|MONTHS?", text):
        return False
    labels = " | ".join(fold(r["label"] or "") for r in grid)
    if _NOT_FAMILY.search(labels):          # the Section-4 maturity-gap table
        return False
    roles = [role_of(r["label"] or "", False) for r in grid]
    # no total required here: a matrix broken across a page keeps its total
    # in the next block, which joins as a continuation
    return "saving" in roles and any(x in roles for x in ("public", "commercial", "fx_deposit"))


def _identity_holds(rows: list[dict], step: float) -> bool:
    checked = ok = 0
    grand_ok = None
    for x in rows:
        tot = next((v for b, v in x["cells"] if b == "total"), None)
        parts = [v for b, v in x["cells"] if b not in ("total", "total_prior") and v is not None]
        if tot is None or not parts:
            continue
        hit = abs(sum(parts) - tot) <= max(2.0 * step, 1e-5 * abs(tot))
        checked += 1
        ok += int(hit)
        if x["role"] in ("grand_total", "total"):
            grand_ok = hit                      # the last total row wins
    return checked >= 4 and ok / checked >= 0.9 and bool(grand_ok)


def _grand_total(rows: list[dict]) -> float | None:
    tots = [next((v for b, v in x["cells"] if b == "total"), None)
            for x in rows if x["role"] in ("grand_total", "total")]
    tots = [t for t in tots if t is not None]
    return max(tots) if tots else None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid, col_labels = absorb_inline(json.loads(g), lambda lab: role_of(lab, False)), json.loads(cl or "[]")
        if _is_family(grid, col_labels, heading):
            found.append((pg, bid, heading, grid, col_labels, unit))
    if not found:
        return None
    # a continuation block (the matrix broke across a page) has no header
    # of its own and no lead row: it is family by adjacency
    pages = {pg for pg, *_ in found}
    for pg, bid, heading, cl, g, unit in blocks:
        if (pg in pages or pg - 1 in pages) and not any(b[0] == pg and b[1] == bid for b in found):
            grid, col_labels = absorb_inline(json.loads(g), lambda lab: role_of(lab, False)), json.loads(cl or "[]")
            roles = [role_of(r["label"] or "", False) for r in grid]
            if any(x in roles for x in ("total", "grand_total", "bank_deposits", "fx_deposit")) \
                    and not _NOT_FAMILY.search(" | ".join(fold(r["label"] or "") for r in grid)) \
                    and 6 <= max((len(r["cells"]) for r in grid), default=0) <= 12:
                found.append((pg, bid, heading, grid, col_labels, unit))
    found.sort(key=lambda b: (b[0], b[1]))
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    # one stream of rows across blocks; a block without a readable header
    # inherits the model before it when its live columns line up
    stream: list[tuple] = []       # (row, cols, page, block_id, heading)
    no_header = 0
    prev_cols = None
    for pg, bid, heading, grid, col_labels, _u in found:
        cols = BM.column_model(grid, col_labels, BANDSET)
        if cols is None and prev_cols is not None:
            data = [r for r in grid if not BM.is_header_row(r, BANDSET.header_label)]
            ncol = max((len(r["cells"]) for r in data), default=0)
            if ncol and all(i < ncol for i, _b in prev_cols):
                cols = prev_cols
        if cols is None:
            no_header += 1
            continue
        prev_cols = cols
        for r in grid:
            stream.append((r, cols, pg, bid, heading))
    instances = _instances_of_stream(stream, factor)
    return {"unit": unit, "step": float(factor or 1.0), "no_header": no_header,
            "instances": instances}


def _instances_of_stream(stream, factor):
    """Split the row stream into instances on header rows / a repeating
    saving row, tagging each with current / prior from the header text."""
    out: list[dict] = []
    cur: list[dict] = []
    label_hint = None
    heading = None
    seen: set[str] = set()
    in_bank_group = False
    for r, cols, pg, bid, head in stream:
        label = (r["label"] or "").strip()
        if BM.is_header_row(r, BANDSET.header_label):
            text = fold(label + " " + " ".join(str(c) for c in r["cells"] if isinstance(c, str)))
            if cur and any(x["role"] in ("total", "grand_total") for x in cur):
                out.append({"rows": cur, "hint": label_hint, "heading": heading})
                cur, seen, in_bank_group = [], set(), False
            if _PRIOR.search(text):
                label_hint = "prior"
            elif re.search(r"CARI DONEM|CURRENT PERIOD", text):
                label_hint = "current"
            continue
        if not label:
            continue
        role = role_of(label, in_bank_group)
        if role == "saving" and role in seen and cur:
            out.append({"rows": cur, "hint": label_hint, "heading": heading})
            cur, seen, in_bank_group, label_hint = [], set(), False, None
        if not cur:
            heading = head
        if role:
            seen.add(role)
        if role == "bank_deposits":
            in_bank_group = True
        elif role in ("total", "grand_total", "saving", "fx_deposit", "public", "commercial"):
            in_bank_group = False
        cells = r["cells"]
        vals = []
        for i, band in cols:
            v = num(cells[i]) if i < len(cells) else None
            if factor is not None:
                v = U.scale_amount(v, factor)
            vals.append((band, v))
        cur.append({"label": label, "role": role, "cells": vals, "page": pg, "block_id": bid})
    if cur:
        out.append({"rows": cur, "hint": label_hint, "heading": heading})
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

    def refs(key) -> dict[str, list[float]]:
        got = {"balance": [], "interest_expense": []}
        try:
            for name, tot in aud.execute(
                    "SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE "
                    "bank_ticker=? AND period=? AND kind=?", key):
                if tot is not None and _BS_DEPOSITS.search(fold(name or "").strip()):
                    got["balance"].append(tot)
            for name, amt in aud.execute(
                    "SELECT item_name, amount FROM bank_audit_profit_loss WHERE "
                    "bank_ticker=? AND period=? AND kind=?", key):
                if amt is not None and _PL_INTEREST.search(fold(name or "")):
                    got["interest_expense"].append(amt)
        except sqlite3.OperationalError:
            pass
        return got

    def classify(grand: float | None, key) -> tuple[str, str] | None:
        """(measure, period_label) from the numbers: the grand total against
        this filing's BS deposits / P&L deposit interest ('current'), the
        prior year-end's BS ('prior' for a balance matrix) or the prior
        year's same quarter's P&L ('prior' for an interest matrix, whose
        prior column is cumulative to the same date a year earlier)."""
        if grand is None:
            return None
        bank, period, kind = key
        year, q = int(period[:4]), period[4:]
        probes = [
            (key, "current", ("balance", "interest_expense")),
            ((bank, prior_year_end(period), kind), "prior", ("balance",)),
            ((bank, f"{year - 1}{q}", kind), "prior", ("interest_expense",)),
        ]
        for k, label, names in probes:
            got = refs(k)
            for name in names:
                if any(abs(grand - v) <= max(2.0, 2e-3 * abs(v)) for v in got[name]):
                    return name, label
        return None

    detected = written = gated = no_header = 0
    measures: Counter = Counter()
    per_filing: Counter = Counter()
    role_cov = [0, 0]
    band_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        no_header += got["no_header"]
        kept = []
        order = 0
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"]):
                gated += 1
                continue
            hit = classify(_grand_total(inst["rows"]), key)
            if hit is not None:
                inst["measure"], inst["label"] = hit
            else:
                # unanchored: the header's own word, else the print order
                # (current before prior within a matrix)
                inst["measure"] = "unknown"
                inst["label"] = inst["hint"] or ("current" if order % 2 == 0 else "prior")
            order += 1
            measures[inst["measure"]] += 1
            kept.append(inst)
            for x in inst["rows"]:
                if any(v is not None for _b, v in x["cells"]):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:45]] += 1
                for b, v in x["cells"]:
                    if v is not None:
                        band_cov[1] += 1
                        band_cov[0] += int(b is not None)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        if out is not None:
            out.execute("DELETE FROM bank_audit_deposit_maturity_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for n, inst in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_deposit_maturity_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, inst["measure"], inst["label"], inst["heading"], i, x["label"],
                      x["role"], k, b, v, x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"]) for k, (b, v) in enumerate(x["cells"])])
                written += sum(len(x["cells"]) for x in inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks without a readable "
          f"band header: {no_header} | instances gated out by total = Σ bands: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
        print(f"measure (grand total vs narrow BS deposits / P&L deposit interest): "
              f"{dict(measures.most_common())}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} "
              f"({role_cov[0] / role_cov[1]:.1%})")
        print(f"  value cells with a band: {band_cov[0]}/{band_cov[1]} "
              f"({band_cov[0] / band_cov[1]:.1%})")
    for lab, c in unrole.most_common(10):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_deposit_maturity_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
