#!/usr/bin/env python
"""The deposit-insurance graduation: the NOTES-section "saving deposits
covered by / exceeding the deposit insurance limit" table (Section 5,
liabilities), minted from the document layer.

Template: saving deposits (TL), FX deposits with saving-deposit status,
other accounts with saving-deposit status, foreign-branch deposits under a
foreign insurer, off-shore-branch deposits under a foreign insurer, and a
total some banks print — some add the same three rows for commercial
deposits. Columns: covered by insurance (current, prior), exceeding the
limit (current, prior); the column order is read off the labels and the
standard (covered first) assumed otherwise.

Gate: where a total row is printed, total = Σ rows in every column, else
the instance is refused; where none is printed the instance is kept and
`total_check` says so ('not_printed' vs 'holds') — the regulator's own
template has no total row, so refusing those would lose a third of the
banks for no defect of theirs. No narrow lane holds any of this.

`--write` stores into bank_audit_deposit_insurance_full in
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

ROLES: list[tuple[str, re.Pattern]] = [
    ("total", re.compile(r"^TOPLAM|^TOTAL")),
    ("foreign_branches", re.compile(r"^YURT ?DISI SUBE|^FOREIGN BRANCH|^BRANCHES.? DEPOSITS UNDER FOREIGN|"
                                    r"^DEPOSITS (IN|AT) FOREIGN BRANCH")),
    ("offshore_branches", re.compile(r"^KIYI ?BNK|^KIYI BANKACILIGI|^OFF.?SHORE")),
    ("commercial_fc", re.compile(r"^TICARI MEVDUAT NITELIGINI HAIZ DTH|^FOREIGN CURRENCY COMMERCIAL|"
                                 r"^COMMERCIAL DEPOSITS? .*(FC|FX|FOREIGN)")),
    ("commercial_other", re.compile(r"^TICARI MEVDUAT NITELIGINI HAIZ DIG|^OTHER .*COMMERCIAL")),
    ("commercial_tl", re.compile(r"^TICARI MEVDUAT|^COMMERCIAL DEPOSIT")),
    ("saving_fc", re.compile(r"^TASARRUF MEVDUATI NITELIGINI HAIZ DTH|^FOREIGN CURRENCY SAVING|^DTH\b|"
                             r"^FOREIGN CURRENCY ACCOUNT|^DOVIZ HESAP|^YABANCI PARA HESAP|"
                             r"^SAVING(S)? DEPOSITS? \(?(FC|FX|FOREIGN)|^FX SAVING|^FC SAVING|"
                             r"^KATILIM FONU NITELIGINI HAIZ DTH|^FOREIGN CURRENCY PARTICIPATION")),
    ("saving_other", re.compile(r"^TASARRUF MEVDUATI NITELIGINI HAIZ DIG|^OTHER (SAVING|DEPOSITS IN THE FORM)|^DIG\.? ?H|"
                                r"^OTHER ACCOUNTS? (IN THE FORM|WITH|HAVING|CONSIDERED)|"
                                r"^KATILIM FONU NITELIGINI HAIZ DIG|^OTHER .*PARTICIPATION")),
    ("saving_tl", re.compile(r"^TASARRUF MEVDUAT|^SAVING(S)? DEPOSIT|^KATILIM FON|^PARTICIPATION FUND|"
                             r"^REAL PERSONS|^TURKISH LIRA ACCOUNT|^TURK LIRASI HESAP|^TL HESAP")),
]
VALUES = ("covered_current", "covered_prior", "exceeding_current", "exceeding_prior")
_FIRST = re.compile(r"^TASARRUF MEVDUAT|^SAVING(S)? DEPOSIT|^KATILIM FON|^PARTICIPATION FUND|^REAL PERSONS|"
                    r"^TURKISH LIRA ACCOUNT|^TURK LIRASI HESAP|^TL HESAP")
_CTX = re.compile(r"SIGORTA|INSURANCE|GUARANTEE|COVERED")
_COVERED = re.compile(r"KAPSAM|COVERED|UNDER|GUARANTEE|WITHIN")
_EXCEED = re.compile(r"ASAN|EXCEED|OVER|ABOVE")


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


def columns_swapped(col_labels: list, heading: str | None) -> bool:
    """True when the labels put the exceeding pair before the covered pair."""
    for src in (col_labels, [heading or ""]):
        text = " ".join(str(c or "") for c in src)
        f = fold(text)
        a, b = _COVERED.search(f), _EXCEED.search(f)
        if a and b:
            return b.start() < a.start()
    return False


_YEAR = re.compile(r"^(19|20)\d\d$")
_PERIOD_MARK = re.compile(r"CARI|CURRENT|ONCEKI|PRIOR|PREVIOUS")


def _is_year_row(cells: list) -> bool:
    ys = [c for c in cells if c is not None]
    return len(ys) >= 2 and all(
        (isinstance(c, float) and c.is_integer() and 1990 <= c <= 2100)
        or (isinstance(c, str) and _YEAR.match(c.strip())) for c in ys)


def period_major(grid: list[dict], col_labels: list) -> bool:
    """True when the four columns run (cur, cur, prior, prior) — covered and
    exceeding within each period — instead of the standard (cur, prior, cur,
    prior). Read off a year header row in the grid, else the period markers
    in the column labels."""
    for r in grid:
        if _is_year_row(r["cells"]):
            ys = [float(c) if isinstance(c, float) else float(c.strip())
                  for c in r["cells"] if c is not None]
            if len(ys) == 4:
                return ys[0] == ys[1] and ys[2] == ys[3] and ys[0] != ys[2]
    marks = []
    for c in col_labels:
        f = fold(str(c or ""))
        m = _PERIOD_MARK.search(f)
        if m:
            marks.append("cur" if m.group(0) in ("CARI", "CURRENT") else "prior")
    return marks == ["cur", "cur", "prior", "prior"]


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_deposit_insurance_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    covered_current   REAL,
    covered_prior     REAL,
    exceeding_current REAL,
    exceeding_prior   REAL,
    -- 'holds' (a printed total equals the sum of rows) or 'not_printed'
    total_check  TEXT NOT NULL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_deposit_insurance_full_role
  ON bank_audit_deposit_insurance_full(row_role);
"""


def _is_family(grid: list[dict], col_labels: list, heading: str | None) -> bool:
    if not grid or not 3 <= len(grid) <= 14:
        return False
    if len(grid[0]["cells"]) != 4:
        return False
    body = [r for r in grid if not _is_year_row(r["cells"])]     # AKBNK opens on a year row
    if not body or not _FIRST.search(fold(body[0]["label"] or "").strip()):
        return False
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    return bool(_CTX.search(ctx))


def _rows_of(grid, pg, bid, factor, swapped, by_period=False) -> list[dict]:
    rows = []
    pending = ""
    for r in grid:
        label = (r["label"] or "").strip()
        if not label:
            continue
        cells = r["cells"]
        if _is_year_row(cells):                 # "2023 2023 2022 2022" header
            continue
        if cells and all(c is None for c in cells):
            # a wrapped label: the TAIL of the row above when that row has no
            # role yet and the joined label has one, otherwise the HEAD of
            # the row below
            joined = (rows[-1]["label"] + " " + label) if rows else ""
            if rows and rows[-1]["role"] is None and role_of(joined) is not None:
                rows[-1]["label"] += " " + label
                rows[-1]["role"] = role_of(rows[-1]["label"])
                continue
            pending = (pending + " " + label).strip()
            continue
        if pending:
            label = pending + " " + label
        pending = ""
        vals = [num(c) for c in cells[-4:]]
        vals = [None] * (4 - len(vals)) + vals
        if by_period:                           # (cur, cur, prior, prior) printed
            vals = [vals[0], vals[2], vals[1], vals[3]]
        if swapped:
            vals = vals[2:] + vals[:2]
        if factor is not None:
            vals = [U.scale_amount(v, factor) for v in vals]
        row = {"label": label, "role": role_of(label), "page": pg, "block_id": bid}
        row.update(zip(VALUES, vals))
        rows.append(row)
    return rows


def total_check(inst: list[dict]) -> str | None:
    """'holds' / 'not_printed', or None when a printed total fails."""
    tot = next((x for x in inst if x["role"] == "total"), None)
    if tot is None:
        return "not_printed"
    parts = [x for x in inst if x["role"] not in ("total", None)]
    if not parts:
        return None
    for col in VALUES:
        t = tot[col]
        if t is None:
            continue
        s = sum(x[col] or 0.0 for x in parts)
        if abs(s - t) > max(2.0, 1e-5 * abs(t)):
            return None
    return "holds"


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid, col_labels = absorb_inline(json.loads(g), role_of), json.loads(cl or "[]")
        if _is_family(grid, col_labels, heading):
            found.append((pg, bid, grid, unit, columns_swapped(col_labels, heading),
                          period_major(grid, col_labels)))
    if not found:
        return None
    unit = found[0][3]
    factor = U.UNIT_SCALE.get(unit)
    return {"unit": unit, "instances": [
        _rows_of(grid, pg, bid, factor, swapped, by_period)
        for pg, bid, grid, _u, swapped, by_period in found]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
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

    detected = written = gated = 0
    checks: Counter = Counter()
    per_filing: Counter = Counter()
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            tc = total_check(inst)
            if tc is None:
                gated += 1
                continue
            checks[tc] += 1
            kept.append((tc, inst))
            for x in inst:
                if any(x[v] is not None for v in VALUES):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[fold(x["label"])[:50]] += 1
        if not kept:
            continue
        per_filing[len(kept)] += 1
        if out is not None:
            out.execute("DELETE FROM bank_audit_deposit_insurance_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for n, (tc, inst) in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_deposit_insurance_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, i, x["label"], x["role"], *(x[v] for v in VALUES), tc,
                      x["page"], x["block_id"], got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances refused (printed total ≠ Σ rows): {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
        print(f"total_check: {dict(checks)}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} "
              f"({role_cov[0] / role_cov[1]:.1%})")
    for lab, c in unrole.most_common(8):
        print(f"    unrecognised x{c}: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_deposit_insurance_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
