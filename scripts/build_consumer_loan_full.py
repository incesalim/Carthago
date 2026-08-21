#!/usr/bin/env python
"""The consumer-loans graduation: the second NOTES-section family minted from
the document layer — BRSA's "consumer loans, retail credit cards and
personnel loans by maturity" note (Section 5), ~45 rows x 3 columns
(short-term, medium/long-term, total), current + prior instances.

Rows carry two roles because item labels repeat under each group: `group`
(consumer loans TL / FC-indexed / FC, retail credit cards TL / FC, personnel
loans, personnel credit cards, overdraft accounts) and `item` (housing,
vehicle, general-purpose, other, instalment, non-instalment). The label is
kept verbatim besides.

The mint gate needs no registry at all: every row prints total = short +
long, so an instance is stored only if that identity holds on at least 90%
of its value-bearing rows AND on its grand total. No narrow lane holds any of
this.

`--write` stores into bank_audit_consumer_loan_full in
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
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

_FIRST = re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(TP|TL|TRY|TRL)")
# DENIZ / ING / AKTIF: the note title carries the consumer-TL figures, the
# row's own label lost to the capture
_TITLE = re.compile(r"^(\d+(\.\d+)*\.?\s*)?(TUKETICI KREDILERI, BIREYSEL|CONSUMER LOANS, (INDIVIDUAL|RETAIL))")
_TOTAL = re.compile(r"^TOPLAM ?(\(\*+\))?$|^TOTAL ?(\(\*+\))?$|^TOPLAM TUKETICI KREDI|^TOTAL CONSUMER LOANS?$")
_HEADER_ROW = re.compile(r"^(CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD|\d{1,2}[ .]|KISA VADELI|SHORT.?TERM|BILGILER$)")
GROUPS: list[tuple[str, re.Pattern]] = [
    ("consumer_fc_indexed", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(DOVIZE ENDEKSLI|FC.?INDEXED|FX.?INDEXED|INDEXED TO)")),
    ("consumer_fc", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(YP|FC|FX)\b")),
    ("consumer_tl", re.compile(r"^(TUKETICI KREDILERI|CONSUMER LOANS)\s*[-–]?\s*(TP|TL|TRY|TRL)\b")),
    ("retail_cards_fc", re.compile(r"^(BIREYSEL KREDI KARTLARI|RETAIL CREDIT CARDS|INDIVIDUAL CREDIT CARDS|CONSUMER CREDIT CARDS)\s*[-–]?\s*(YP|FC|FX)")),
    ("retail_cards_tl", re.compile(r"^(BIREYSEL KREDI KARTLARI|RETAIL CREDIT CARDS|INDIVIDUAL CREDIT CARDS|CONSUMER CREDIT CARDS)\s*[-–]?\s*(TP|TL|TRY|TRL)")),
    ("personnel_cards_fc", re.compile(r"^(PERSONEL KREDI KARTLARI|PERSONNEL CREDIT CARDS)\s*[-–]?\s*(YP|FC|FX)")),
    ("personnel_cards_tl", re.compile(r"^(PERSONEL KREDI KARTLARI|PERSONNEL CREDIT CARDS)\s*[-–]?\s*(TP|TL|TRY|TRL)")),
    ("personnel_loans_fc_indexed", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(DOVIZE ENDEKSLI|FC.?INDEXED|FX.?INDEXED|INDEXED TO)")),
    ("personnel_loans_fc", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(YP|FC|FX)\b")),
    ("personnel_loans_tl", re.compile(r"^(PERSONEL KREDILERI|PERSONNEL LOANS)\s*[-–]?\s*(TP|TL|TRY|TRL)\b")),
    # overdrafts: "Kredili Mevduat Hesabı", the participation banks' "Kredili
    # Müstakriz Hesabı", "Credit Deposit Account", and a bare "Deposit
    # Accounts – TL (Real Persons)"; the personnel ones are their own group
    ("overdraft_personnel_fc", re.compile(r"^(KREDILI (MEVDUAT|MUSTAKRIZ) HESA|OVERDRAFT ACCOUNTS?|CREDIT DEPOSIT ACCOUNTS?|DEPOSIT ACCOUNTS?)"
                                          r"[^()]*[-–]\s*(YP|FC|FX)[^()]*\((PERSONEL|PERSONNEL)")),
    ("overdraft_personnel_tl", re.compile(r"^(KREDILI (MEVDUAT|MUSTAKRIZ) HESA|OVERDRAFT ACCOUNTS?|CREDIT DEPOSIT ACCOUNTS?|DEPOSIT ACCOUNTS?)"
                                          r"[^()]*[-–]\s*(TP|TL|TRY|TRL)[^()]*\((PERSONEL|PERSONNEL)")),
    ("overdraft_fc", re.compile(r"^(KREDILI (MEVDUAT|MUSTAKRIZ) HESA|OVERDRAFT ACCOUNTS?|CREDIT DEPOSIT ACCOUNTS?|DEPOSIT ACCOUNTS?)"
                                r"[^()]*[-–]\s*(YP|FC|FX)")),
    ("overdraft_tl", re.compile(r"^(KREDILI (MEVDUAT|MUSTAKRIZ) HESA|OVERDRAFT ACCOUNTS?|CREDIT DEPOSIT ACCOUNTS?|DEPOSIT ACCOUNTS?)"
                                r"[^()]*[-–]\s*(TP|TL|TRY|TRL)")),
]
ITEMS: list[tuple[str, re.Pattern]] = [
    ("housing", re.compile(r"^KONUT|^HOUSING|^MORTGAGE|^REAL ESTATE")),
    ("vehicle", re.compile(r"^TASIT|^VEHICLE|^AUTO|^OTOMOBIL|^CAR LOAN")),
    ("general_purpose", re.compile(r"^IHTIYAC|^GENERAL PURPOSE|^CONSUMER LOANS$|^PERSONAL")),
    ("non_instalment", re.compile(r"^TAKSITSIZ|^WITHOUT.?INSTAL|^NON.?.?INSTAL")),
    ("instalment", re.compile(r"^TAKSITLI|^WITH.?INSTAL|^INSTAL")),
    ("other", re.compile(r"^DIGER|^OTHER")),
]
VALUES = ("short_term", "long_term", "accruals", "total")
# ISCTR prints a fourth column, the accruals, between the maturities and the total
_ACCRUALS_COL = re.compile(r"ACCRUAL|REESKONT|TAHAKKUK")


def _group_of(label: str) -> str | None:
    f = fold(label)
    for g, rx in GROUPS:
        if rx.search(f):
            return g
    return None


def _item_of(label: str) -> str | None:
    f = fold(label)
    for i, rx in ITEMS:
        if rx.search(f):
            return i
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_consumer_loan_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    group_role   TEXT,
    item_role    TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    short_term   REAL,
    long_term    REAL,
    accruals     REAL,               -- ISCTR's fourth column; NULL where the template has three
    total        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_consumer_loan_full_group
  ON bank_audit_consumer_loan_full(group_role, item_role);
"""


def _normalise(grid: list[dict]) -> list[dict]:
    """The grid from its consumer-TL row on: header rows above it dropped
    (AKBNK: "Cari Dönem – 31.12.2025"), the note title relabelled as that
    row where it carries the figures (DENIZ / ING / AKTIF), the header
    rows between it and the first item dropped."""
    out = []
    started = False
    for r in grid:
        lab = fold(r["label"] or "").strip()
        live = any(c is not None and not (isinstance(c, str) and not num(c)) for c in r["cells"])
        if not started:
            if _FIRST.search(lab):
                started = True
            elif _TITLE.search(lab) and live:
                started = True
                r = {**r, "label": "Tüketici Kredileri-TP"}
            else:
                continue
        elif not live and _HEADER_ROW.search(lab):
            continue
        out.append(r)
    return out


def _is_family(grid: list[dict]) -> bool:
    if not grid or len(grid) < 8:
        return False
    first = fold(grid[0]["label"] or "")
    return bool(_FIRST.search(first)) and any(
        _TOTAL.search(fold(r["label"] or "").strip()) for r in grid)


def _identity_holds(inst: list[dict]) -> bool:
    """total = short + long (+ accruals where a bank prints them) on >= 90%
    of value-bearing rows, and on the grand total row itself."""
    checked = ok = 0
    grand_ok = False
    for x in inst:
        s, lg, t = x["short_term"], x["long_term"], x["total"]
        if t is None or (s is None and lg is None):
            continue
        checked += 1
        hit = abs((s or 0.0) + (lg or 0.0) + (x.get("accruals") or 0.0) - t) <= max(2.0, 1e-5 * abs(t))
        ok += int(hit)
        if x["item_role"] is None and x["group_role"] is None \
                and _TOTAL.search(fold(x["label"]).strip()):
            grand_ok = hit
    has_grand = any(x["item_role"] is None and x["group_role"] is None and _TOTAL.search(fold(x["label"]).strip())
                    for x in inst)
    if not has_grand:
        # no grand total printed (ISCTR 2025Q4): the per-row identity alone,
        # on a table long enough to be the whole note
        return checked >= 12 and ok / checked >= 0.9
    return checked >= 4 and ok / checked >= 0.9 and grand_ok


def _has_total(grid: list[dict]) -> bool:
    return any(_TOTAL.search(fold(r["label"] or "").strip()) for r in grid)


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, grid_json, col_labels_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()

    def role(lab):
        return _group_of(lab) or _item_of(lab) or ("total" if _TOTAL.search(fold(lab).strip()) else None)

    found = []
    pending = None          # ISCTR: the table split over several blocks, the total in the last
    for pg, bid, g, cl, unit in blocks:
        raw = json.loads(g)
        grid = _normalise(absorb_inline(raw, role))
        accruals = bool(_ACCRUALS_COL.search(fold(" ".join(str(c or "") for c in json.loads(cl or "[]")))))
        if pending is not None:
            ppg, pbid, pgrid, paccr, punit, n, (lpg, lbid) = pending
            adjacent = (pg == lpg and bid == lbid + 1) or (pg == lpg + 1 and bid == 1)
            restart = bool(raw) and bool(_FIRST.search(fold(raw[0]["label"] or "")))
            # the chain ends where a block opens on a label the template does
            # not know (ISCTR 2025Q4: the commercial instalment loans follow,
            # and no grand total was printed)
            lead = next((r for r in raw if any(num(c) is not None for c in r["cells"])), None)
            foreign = lead is not None and role(lead["label"] or "") is None
            if adjacent and n < 6 and not restart and not foreign:
                tail = [{**r, "_page": pg, "_block_id": bid} for r in raw
                        if any(num(c) is not None for c in r["cells"])]     # header rows of the continuation dropped
                joined = pgrid + tail
                if _has_total(joined):
                    found.append((ppg, pbid, joined, paccr or accruals, punit))
                    pending = None
                else:
                    pending = (ppg, pbid, joined, paccr or accruals, punit, n + 1, (pg, bid))
                continue
            if len(pgrid) >= 12:
                found.append((ppg, pbid, pgrid, paccr, punit))     # a chain without a grand total
            pending = None
        if _is_family(grid):
            found.append((pg, bid, grid, accruals, unit))
        elif grid and len(grid) >= 4 and _FIRST.search(fold(grid[0]["label"] or "")) and not _has_total(grid):
            pending = (pg, bid, grid, accruals, unit, 1, (pg, bid))
    if pending is not None and len(pending[2]) >= 12:
        found.append(pending[:5])
    if not found:
        return None
    unit = found[0][4]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, grid, accruals, _u in found:
        rows, group = [], None
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            g = _group_of(label)
            if g:
                group = g
            item = None if g else _item_of(label)
            width = 4 if accruals else 3
            vals = [num(c) for c in r["cells"][-width:]]
            vals = [None] * (width - len(vals)) + vals
            if not accruals:
                vals = vals[:2] + [None] + vals[2:]
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": label, "group_role": group if (g or item) else None,
                   "item_role": item, "page": r.get("_page", pg), "block_id": r.get("_block_id", bid)}
            row.update(zip(VALUES, vals))
            rows.append(row)
        instances.append(rows)
    labels = ("current", "prior", "extra2", "extra3")
    return {"unit": unit,
            "instances": {labels[i]: inst for i, inst in enumerate(instances[:4])}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    out = None
    if args.write:
        out = sqlite3.connect(args.tables_db)
        cols = [r[1] for r in out.execute("PRAGMA table_info(bank_audit_consumer_loan_full)")]
        if cols and "accruals" not in cols:
            out.execute("DROP TABLE bank_audit_consumer_loan_full")     # local derived table, rebuilt whole
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

    detected = written = gated = 0
    inst_count: Counter = Counter()
    role_cov = [0, 0]
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = {}
        for lab, inst in got["instances"].items():
            if _identity_holds(inst):
                kept[lab] = inst
            else:
                gated += 1
        if not kept:
            continue
        inst_count[len(kept)] += 1
        for inst in kept.values():
            for x in inst:
                if x["total"] is not None:
                    role_cov[1] += 1
                    role_cov[0] += int(x["group_role"] is not None)
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(kept)} "
                  f"rows={[len(v) for v in kept.values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_consumer_loan_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in kept.items():
                out.executemany(
                    "INSERT INTO bank_audit_consumer_loan_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["label"], x["group_role"], x["item_role"],
                      x["short_term"], x["long_term"], x["accruals"], x["total"], x["page"],
                      x["block_id"], got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by total = short + long: {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
    if role_cov[1]:
        print(f"  value-bearing rows with a group role: {role_cov[0]}/{role_cov[1]} "
              f"({role_cov[0] / role_cov[1]:.1%})")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_consumer_loan_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
