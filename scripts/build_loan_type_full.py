#!/usr/bin/env python
"""The loans-by-type graduation: the first NOTES-section family minted from
the document layer — BRSA's "cash loans by type and credit quality" note
(Section 5, assets), 535 captured tables across 15 banks.

The template is fixed by the regulator even though it is not numbered: eleven
rows — non-specialised loans and its seven sub-types (working-capital,
export, import, financial-sector, consumer, credit cards, other), specialised
loans, other receivables, total — by four credit-quality columns: standard
loans, and watch-list loans split into not-restructured / contract-modified /
refinanced. Two instances per filing (current, then prior year-end).

No narrow lane holds any of it. What makes it trustworthy without one are
the template's own identities, enforced as the MINT GATE: an instance is
stored only if, in the standard column, non-specialised = sum of its seven
sub-types AND total = non-specialised + specialised + other receivables. The
balance-sheet cross-check (the four-column total appearing among the
partition's stored balance-sheet amounts) is reported as information.

`--write` stores into bank_audit_loan_type_full in data/bank_audit_tables.db
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

# Row registry: role -> pattern on the folded label. Order matters where one
# label contains another ("DIGER ALACAKLAR" before "DIGER").
ROLES: list[tuple[str, re.Pattern]] = [
    ("non_specialised", re.compile(r"^IHTISAS DISI|^NON.?SPECIALI[SZ]ED")),
    ("working_capital", re.compile(r"^ISLETME|^WORKING CAPITAL|^OPERATING|"
                                   r"^CORPORATION LOANS|^ENTERPRISE LOANS|"
                                   r"^LOANS (GIVEN|GRANTED|EXTENDED) TO ENTERPRISES")),
    ("export", re.compile(r"^IHRACAT|^EXPORT")),
    ("import", re.compile(r"^ITHALAT|^IMPORT")),
    ("financial_sector", re.compile(r"^MALI KESIM|^FINANCIAL SECTOR|"
                                    r"^LOANS (GIVEN|GRANTED|EXTENDED) TO (THE )?FINANCIAL")),
    ("consumer", re.compile(r"^TUKETICI|^CONSUMER")),
    ("credit_cards", re.compile(r"^KREDI KART|^CREDIT CARD")),
    ("other_receivables", re.compile(r"^DIGER ALACAK|^OTHER RECEIVABLE")),
    ("other", re.compile(r"^DIGER( \(\*+\))?$|^DIGER KREDI|^OTHER( \(\*+\))?$|^OTHER LOANS")),
    ("specialised", re.compile(r"^IHTISAS KREDI|^SPECIALI[SZ]ED (LOANS|LENDING)")),
    ("total", re.compile(r"^TOPLAM$|^TOTAL$")),
]
SUBTYPES = ("working_capital", "export", "import", "financial_sector",
            "consumer", "credit_cards", "other")
VALUES = ("standard", "watch_not_restructured", "watch_modified", "watch_refinanced")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_loan_type_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- the four credit-quality columns, canonical thousand TL (scaled at
    -- mint). NULL = the filing printed "-".
    standard                REAL,
    watch_not_restructured  REAL,
    watch_modified          REAL,
    watch_refinanced        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_loan_type_full_role
  ON bank_audit_loan_type_full(row_role);
"""


def _is_family(grid: list[dict]) -> bool:
    roles = [role_of(r["label"] or "") for r in grid]
    # AKBNK prints the sub-types without the "Ihtisas Disi Krediler" head
    return roles and roles[0] in ("non_specialised", "working_capital") and "total" in roles \
        and sum(1 for r in roles if r in SUBTYPES) >= 4 and 7 <= len(grid) <= 16


def _identities_hold(inst: list[dict]) -> bool:
    by = {}
    for x in inst:
        by.setdefault(x["role"], x)
    ns, tot = by.get("non_specialised"), by.get("total")
    if not tot or tot["standard"] is None:
        return False
    subs = sum(by[s]["standard"] or 0.0 for s in SUBTYPES if s in by)
    if ns and ns["standard"] is not None:
        ok1 = abs(subs - ns["standard"]) <= max(2.0, 1e-5 * abs(ns["standard"]))
        ns_value = ns["standard"]
    else:
        ok1 = sum(1 for s in SUBTYPES if s in by) >= 4     # no head printed: the sub-types are it
        ns_value = subs
    spec = (by.get("specialised") or {}).get("standard") or 0.0
    oth = (by.get("other_receivables") or {}).get("standard") or 0.0
    ok2 = abs(ns_value + spec + oth - tot["standard"]) \
        <= max(2.0, 1e-5 * abs(tot["standard"]))
    return ok1 and ok2


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, n_cols, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, nc, g, unit in blocks:
        grid = absorb_inline(json.loads(g), role_of)
        if _is_family(grid):
            found.append((pg, bid, grid, unit))
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, grid, _u in found:
        rows = []
        pending = ""          # a wrapped label's head, printed on its own line
        # the value columns are the last four LIVE columns: YKBNK's capture
        # carries an all-None phantom column in the middle of the grid
        reg = [r for r in grid if role_of(r["label"] or "")]          # registry rows only:
        ncol = max((len(r["cells"]) for r in reg), default=0)         # a merged table below
        live = [c for c in range(ncol) if any(len(r["cells"]) > c and r["cells"][c] is not None for r in reg)]
        take = live[-4:]
        for r in grid:
            label = (r["label"] or "").strip()
            if not label:
                continue
            cells = r["cells"]
            # "Mali Kesime" / "Verilen Krediler": the capture left the wrap as
            # two rows, the head with NO cells at all (a disclosed-nothing row
            # prints "-" cells and is a real row). Carry the head forward so
            # the role is read off the whole label, whichever half matched.
            if cells and all(c is None for c in cells):
                pending = (pending + " " + label).strip()
                continue
            if pending:
                label = pending + " " + label
            pending = ""
            vals = [num(cells[c]) if c < len(cells) else None for c in take]
            vals = [None] * (4 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": label, "role": role_of(label), "page": pg,
                   "block_id": bid}
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

    def bs_amounts(key) -> set[float]:
        try:
            return {round(abs(v), 2) for (v,) in aud.execute(
                "SELECT amount_total FROM bank_audit_balance_sheet WHERE "
                "bank_ticker=? AND period=? AND kind=?", key) if v is not None}
        except sqlite3.OperationalError:
            return set()

    detected = written = gated = 0
    inst_count: Counter = Counter()
    ncols_seen: Counter = Counter()
    bs_hit = [0, 0]
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = {}
        for lab, inst in got["instances"].items():
            if _identities_hold(inst):
                kept[lab] = inst
            else:
                gated += 1
        if not kept:
            continue
        got["instances"] = kept
        inst_count[len(kept)] += 1
        cur = kept.get("current")
        if cur:
            tot = next((x for x in cur if x["role"] == "total"), None)
            if tot:
                grand = sum(tot[v] or 0.0 for v in VALUES)
                amounts = bs_amounts(key)
                if amounts and grand:
                    bs_hit[1] += 1
                    bs_hit[0] += int(any(abs(grand - a) <= max(2.0, 1e-4 * a)
                                         for a in amounts))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(kept)} "
                  f"rows={[len(v) for v in kept.values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_loan_type_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in kept.items():
                out.executemany(
                    "INSERT INTO bank_audit_loan_type_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["label"], x["role"],
                      *(x[v] for v in VALUES), x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by the identities: {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
    # Informational only. The balance sheet's loans line aggregates on a
    # different perimeter (amortised-cost loans incl. leasing/factoring and
    # net of nothing here), so a low figure is expected, not a defect; the
    # lane's trust rests on the two template identities above.
    print(f"  (info) four-column total equal to a stored balance-sheet amount: "
          f"{bs_hit[0]}/{bs_hit[1]} — not an anchor, perimeters differ")
    if ncols_seen:
        print("  column counts seen:", dict(ncols_seen))
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_loan_type_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
