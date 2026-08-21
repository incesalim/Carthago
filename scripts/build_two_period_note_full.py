#!/usr/bin/env python
"""The two-period notes graduation: the small NOTES-section tables printed
as items × (current period, prior period) with a total — minted from the
document layer under a family registry, each family anchored to a line of
the narrow off-balance-sheet statement:

  letters_of_guarantee   definite, temporary, advance, customs, other
                         letters of guarantee     → off-BS letters of guarantee
  non_cash_loans         letters of guarantee, letters of credit, bank
                         acceptances / avals, other guarantees and
                         sureties                 → off-BS non-cash loans

Rows carry a registry role, the label kept. MINT GATE: total = Σ rows on
the current column (and on the prior where printed). Anchor, dry-run
(default): the current total vs the family's narrow off-balance line, same
filing.

`--write` stores into bank_audit_two_period_note_full in
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
FAMILIES: dict[str, tuple[re.Pattern, list[tuple[str, re.Pattern]]]] = {
    "letters_of_guarantee": (R(r"^TEMINAT MEKTUPLARI|^LETTERS? OF GUARANTEE"), [
        ("definite", R(r"^KESIN|^DEFINITE|^LETTERS? OF CERTAIN|^CERTAIN|^FINAL")),
        ("temporary", R(r"^GECICI|^TEMPORARY|^LETTERS? OF TENTATIVE|^TENTATIVE|^BID|^PROVISIONAL")),
        ("advance", R(r"^AVANS|^ADVANCE|^LETTERS? OF ADVANCE")),
        ("customs", R(r"^GUMRUK|^CUSTOMS|^LETTERS? OF GUARANTEE GIVEN TO CUSTOMS|^GIVEN TO CUSTOMS")),
        ("other", R(r"^DIGER|^OTHER|^SURETY")),
    ]),
    "non_cash_loans": (R(r"^GAYRINAKDI KREDI|^NON.?CASH LOAN"), [
        ("letters_of_guarantee", R(r"^TEMINAT MEKTUP|^LETTERS? OF GUARANTEE|^GUARANTEES?$|^GARANTI")),
        ("letters_of_credit", R(r"^AKREDITIF|^LETTERS? OF CREDIT")),
        ("bank_acceptances", R(r"^BANKA KREDI|^BANKA AVAL|^BANKA KABUL|^BANK LOAN|^BANK ACCEPTANCE|^BILLS? OF EXCHANGE|^ACCEPTANCE")),
        ("endorsements", R(r"^CIRO|^ENDORSEMENT")),
        ("other", R(r"^DIGER|^OTHER")),
    ]),
}
_TOTAL = R(r"^TOPLAM|^TOTAL")
_FIRST = {"letters_of_guarantee": ("definite", "temporary"), "non_cash_loans": ("letters_of_guarantee", "letters_of_credit", "bank_acceptances")}
_CTX = R(r"CARI|ONCEKI|CURRENT|PRIOR|PREVIOUS")


def roles_of(fam: str, labels: list[str]) -> list[str | None]:
    out = []
    for lab in labels:
        f = fold(lab).strip()
        if _TOTAL.search(f):
            out.append("total")
            continue
        out.append(next((role for role, rx in FAMILIES[fam][1] if rx.search(f)), None))
    return out


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_two_period_note_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    family       TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    current      REAL,
    prior        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_two_period_note_full_role
  ON bank_audit_two_period_note_full(family, row_role);
"""


def family_of(grid: list[dict], col_labels: list, heading: str | None) -> str | None:
    if not 3 <= len(grid) <= 10 or len(grid[0]["cells"]) != 2:
        return None
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    if not _CTX.search(ctx):
        return None
    labels = [(r["label"] or "").strip() for r in grid]
    if not any(_TOTAL.search(fold(lab)) for lab in labels):
        return None
    best, best_n = None, 0
    for fam in FAMILIES:
        rs = roles_of(fam, labels)
        if rs[0] not in _FIRST[fam]:
            continue
        n = sum(1 for r in rs if r and r != "total")
        if n >= 2 and n > best_n:
            best, best_n = fam, n
    return best


def _identity_holds(rows: list[dict], step: float) -> bool:
    tot = next((x for x in rows if x["role"] == "total"), None)
    if tot is None:
        return False
    ok = 0
    for col in ("current", "prior"):
        t = tot[col]
        if t is None:
            continue
        s = sum(x[col] or 0.0 for x in rows if x["role"] != "total")
        if abs(s - t) > max(2.0 * step, 1e-5 * abs(t)):
            return False
        ok += 1
    return ok >= 1


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid = json.loads(g)
        fam = family_of(grid, json.loads(cl or "[]"), heading)
        if fam:
            found.append((fam, pg, bid, heading, grid, unit))
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for fam, pg, bid, heading, grid, _u in found:
        labels = [(r["label"] or "").strip() for r in grid]
        rows = []
        for r, lab, role in zip(grid, labels, roles_of(fam, labels)):
            if not lab:
                continue
            vals = [num(c) for c in r["cells"][-2:]]
            vals = [None] * (2 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            rows.append({"label": lab, "role": role, "current": vals[0], "prior": vals[1],
                         "page": pg, "block_id": bid})
        instances.append({"family": fam, "rows": rows, "heading": heading})
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


_OFF_BS = {"letters_of_guarantee": R(r"^TEMINAT MEKTUPLARI$|^LETTERS? OF GUARANTEES?$"),
           # the narrow off-balance lane keeps the guarantees section head,
           # "Garanti ve Kefaletler" — the non-cash loans total
           "non_cash_loans": R(r"^GAYRINAKDI KREDILER$|^NON.?CASH LOANS?$|^GARANTI VE KEFALETLER$|"
                               r"^GUARANTEES AND (WARRANTIES|SURETIES|SURETYSHIPS)$|^GUARANTEES$")}


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

    def narrow(key, fam) -> list[float]:
        rx = _OFF_BS[fam]
        try:
            return [v for name, v in aud.execute(
                "SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE "
                "bank_ticker=? AND period=? AND kind=? AND statement='off_balance'", key)
                if v is not None and rx.search(re.sub(r"\s+[-–]?\s*[IVXA-Z0-9.()]{1,5}$", "", fold(name or "").strip()))]
        except sqlite3.OperationalError:
            return []

    detected = written = gated = 0
    fams: Counter = Counter()
    anchors = {f: [0, 0] for f in FAMILIES}
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"]):
                gated += 1
                continue
            fam = inst["family"]
            fams[fam] += 1
            kept.append(inst)
            tot = next(x for x in inst["rows"] if x["role"] == "total")
            if tot["current"] is not None:
                ref = narrow(key, fam)
                if ref:
                    anchors[fam][1] += 1
                    anchors[fam][0] += int(any(abs(tot["current"] - v) <= max(2.0, 1e-3 * abs(v)) for v in ref))
            for x in inst["rows"]:
                if x["current"] is not None or x["prior"] is not None:
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[(fam, fold(x["label"])[:40])] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_two_period_note_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            for inst in kept:
                n = n_by[inst["family"]]
                n_by[inst["family"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_two_period_note_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, i, x["label"], x["role"], x["current"], x["prior"],
                      x["page"], x["block_id"], got["unit"]) for i, x in enumerate(inst["rows"])])
                written += len(inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the total: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams.most_common())}")
    for fam, b in anchors.items():
        if b[1]:
            print(f"  {fam:24} current total vs narrow off-balance line  {b[0]:5}/{b[1]:5}  {b[0] / b[1]:6.1%}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for (fam, lab), c in unrole.most_common(8):
        print(f"    unrecognised x{c} [{fam}]: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_two_period_note_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
