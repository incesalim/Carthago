#!/usr/bin/env python3
"""Compare each partition against the one before it. Read-only, no PDFs.

Every structural validator in this repo argues *inside* one filing — TL+FC=Total,
parent=Σchildren, Tier1=CET1+AT1 — and each of those is a ratio of figures that
share a scale. When the whole sector switched from Bin TL to Milyon TL in
2026Q2, all eleven filings stayed internally perfect while every stored figure
was wrong by 1000×. No in-filing check could have caught it, and none did.

The generic form of that catch is a comparison against something OUTSIDE the
filing, and the cheapest such thing is the same bank one quarter earlier:

  * **scale shift**   — a row whose value moved by a clean power of ten. Several
                        agreeing in one partition is a reporting-unit change.
  * **newly absent**  — a material row the bank reported last quarter and not
                        this one. Usually an extractor that stopped finding it.
  * **newly present** — a row that appears from nowhere; often the mirror image,
                        a row that was being missed and now is not.

None of these is an error by itself — banks do restate, and lines legitimately
come and go. They are the questions worth asking, ranked by materiality. Nothing
here writes a row, touches D1, or opens a PDF: it is pure SQL over the local
snapshot, so it runs over the whole corpus in seconds.

  python scripts/watch_cross_period.py
  python scripts/watch_cross_period.py --table bank_audit_balance_sheet --bank AKBNK
  python scripts/watch_cross_period.py --since 2025Q1 --min-amount 5000000
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import registry as reg          # noqa: E402
from src.audit_reports.triage import value_columns     # noqa: E402

DEFAULT_OUT = REPO / "docs" / "knowledge" / "triage"

#: A clean power of ten, and the tolerance for calling a move "clean". Unit
#: changes are exact; genuine growth of ~1000× is not, and lands off these.
_SCALE_FACTORS = (1000.0, 100.0, 0.01, 0.001)
_SCALE_TOL = 0.005

#: Rows are compared only in their CURRENT-period form. A 'prior' row restates
#: an earlier year-end and legitimately differs from the previous filing's
#: current row, so pairing those would flag the whole corpus.
_CURRENT_ONLY = "current"


def prev_period(period: str) -> str | None:
    """The quarter before this one. '2026Q1' → '2025Q4'."""
    try:
        year, q = int(period[:4]), int(period[5:])
    except (ValueError, IndexError):
        return None
    return f"{year - 1}Q4" if q == 1 else f"{year}Q{q - 1}"


def row_key_columns(present: set[str]) -> list[str]:
    """Columns that identify the SAME row across two quarters.

    `item_name` is the label as printed, and it drifts — a bank rewords a line,
    the extractor keeps a footnote marker one quarter and not the next — so
    keying on it reports the same row as both "newly absent" and "newly present"
    and buries the real signal under matched pairs of noise. Structural keys
    (the BRSA hierarchy marker, the currency, the sector) are stable by design.
    """
    structural = [c for c in ("statement", "hierarchy", "currency", "sector",
                              "stage", "section") if c in present]
    if any(c in present for c in ("hierarchy", "currency", "sector", "stage")):
        return structural
    # No structural key at all (e.g. the profile lane): fall back to the label,
    # accepting the drift rather than collapsing every row onto one key.
    return structural + [c for c in ("item_name",) if c in present]


def row_key(row: sqlite3.Row, keys: list[str]) -> str:
    return " | ".join(str(row[k] or "") for k in keys)


def load(conn: sqlite3.Connection, table: str, bank: str, period: str,
         kind: str, keys: list[str], cols: list[str]) -> dict[str, dict[str, float]]:
    """{row_key: {column: value}} for one partition's current-period rows."""
    has_pt = "period_type" in {c[1] for c in conn.execute(
        f"PRAGMA table_info({table})").fetchall()}
    sql = f"SELECT * FROM {table} WHERE bank_ticker=? AND period=? AND kind=?"
    args = [bank, period, kind]
    if has_pt:
        sql += " AND period_type=?"
        args.append(_CURRENT_ONLY)
    out: dict[str, dict[str, float]] = {}
    for r in conn.execute(sql, args):
        vals = {c: float(r[c]) for c in cols
                if c in r.keys() and isinstance(r[c], (int, float)) and r[c]}
        if vals:
            out[row_key(r, keys)] = vals
    return out


def scale_factor(now: float, before: float) -> float | None:
    """The clean power of ten between two values, if there is one."""
    if not before or not now:
        return None
    ratio = now / before
    for f in _SCALE_FACTORS:
        if abs(ratio - f) <= abs(f) * _SCALE_TOL:
            return f
    return None


def compare(conn: sqlite3.Connection, table: str, bank: str, kind: str,
            period: str, keys: list[str], cols: list[str],
            min_amount: float) -> dict | None:
    before_p = prev_period(period)
    if not before_p:
        return None
    now = load(conn, table, bank, period, kind, keys, cols)
    before = load(conn, table, bank, before_p, kind, keys, cols)
    if not now or not before:
        return None

    shifts: list[dict] = []
    for k, vals in now.items():
        if k not in before:
            continue
        for col, v in vals.items():
            prev_v = before[k].get(col)
            if prev_v is None or abs(v) < min_amount:
                continue
            f = scale_factor(v, prev_v)
            if f is not None:
                shifts.append({"row": k, "column": col, "now": v,
                               "before": prev_v, "factor": f})

    gone = [{"row": k, "max": max(abs(x) for x in before[k].values())}
            for k in before.keys() - now.keys()
            if max(abs(x) for x in before[k].values()) >= min_amount]
    new = [{"row": k, "max": max(abs(x) for x in now[k].values())}
           for k in now.keys() - before.keys()
           if max(abs(x) for x in now[k].values()) >= min_amount]
    if not (shifts or gone or new):
        return None

    by_factor = collections.Counter(s["factor"] for s in shifts)
    unit_switch = None
    if by_factor:
        f, n = by_factor.most_common(1)[0]
        # One row moving by 1000× is a correction; most of a statement moving by
        # the SAME factor is the filing changing its reporting unit.
        if n >= 3 and n >= 0.4 * len(now):
            unit_switch = {"factor": f, "rows": n, "of": len(now)}
    return {
        "bank_ticker": bank, "period": period, "prior_period": before_p,
        "kind": kind, "table": table,
        "unit_switch": unit_switch,
        "scale_shifts": sorted(shifts, key=lambda s: -abs(s["now"]))[:12],
        "newly_absent": sorted(gone, key=lambda g: -g["max"])[:12],
        "newly_present": sorted(new, key=lambda g: -g["max"])[:12],
    }


def write_report(findings: list[dict], out_dir: Path, scanned: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    units = [f for f in findings if f["unit_switch"]]
    md = [f"# Cross-period watch — {today}",
          "",
          "> **Status: generated, read-only.** `scripts/watch_cross_period.py` over the",
          "> local audit snapshot. Each entry is a QUESTION about a seam between two",
          "> quarters, not a defect: banks restate and lines legitimately come and go.",
          "> Nothing was written to D1 and no PDF was opened.",
          "",
          f"{scanned} partition seams compared, {len(findings)} raised something.",
          ""]

    md += ["## Reporting-unit changes", ""]
    if units:
        md += ["A whole statement moving by one clean power of ten is the failure that",
               "passes every in-filing identity — the 2026Q2 Bin→Milyon switch was",
               "invisible to all of them.", "",
               "| Bank | Period | Kind | Table | Factor | Rows moved |",
               "|---|---|---|---|--:|--:|"]
        for f in units:
            u = f["unit_switch"]
            md.append(f"| {f['bank_ticker']} | {f['prior_period']}→{f['period']} | "
                      f"{f['kind'][:5]} | `{f['table']}` | ×{u['factor']:g} | "
                      f"{u['rows']}/{u['of']} |")
    else:
        md.append("_None._")

    md += ["", "## Seams worth a look", ""]
    for f in sorted(findings, key=lambda x: (x["bank_ticker"], x["period"])):
        if not (f["scale_shifts"] or f["newly_absent"] or f["newly_present"]):
            continue
        md.append(f"### {f['bank_ticker']} {f['prior_period']} → {f['period']} "
                  f"{f['kind']} · `{f['table']}`")
        md.append("")
        for s in f["scale_shifts"][:5]:
            md.append(f"- **scale ×{s['factor']:g}** `{s['row']}` · {s['column']}: "
                      f"{s['before']:,.0f} → {s['now']:,.0f}")
        for g in f["newly_absent"][:5]:
            md.append(f"- **newly absent** `{g['row']}` (was up to {g['max']:,.0f})")
        for g in f["newly_present"][:5]:
            md.append(f"- **newly present** `{g['row']}` (up to {g['max']:,.0f})")
        md.append("")

    path = out_dir / f"{today}-cross-period-watch.md"
    path.write_text("\n".join(md), encoding="utf-8")
    (out_dir / f"{today}-cross-period-watch.json").write_text(
        json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--table", help="one table; default = every validated lane")
    ap.add_argument("--bank")
    ap.add_argument("--since", default="", help="only periods >= this, e.g. 2025Q1")
    ap.add_argument("--min-amount", type=float, default=1_000_000,
                    help="ignore rows below this (thousand TL)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"no audit DB at {db_path}")
        return 1
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    tables = [args.table] if args.table else sorted(
        {st.table for st in reg.REGISTRY if st.has_validator})
    findings: list[dict] = []
    scanned = 0

    for table in tables:
        try:
            cols = value_columns(conn, table)
        except sqlite3.OperationalError:
            print(f"  ? {table}: not in this snapshot")
            continue
        present = {c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        keys = row_key_columns(present)
        sql = (f"SELECT DISTINCT bank_ticker, period, kind FROM {table} "
               f"WHERE period >= ? ORDER BY bank_ticker, period")
        params: list = [args.since or "0000Q0"]
        if args.bank:
            sql = sql.replace("WHERE period >= ?", "WHERE period >= ? AND bank_ticker = ?")
            params.append(args.bank)
        for bank, period, kind in conn.execute(sql, params):
            scanned += 1
            f = compare(conn, table, bank, kind, period, keys, cols, args.min_amount)
            if f:
                findings.append(f)
                u = f["unit_switch"]
                flag = f" UNIT ×{u['factor']:g}" if u else ""
                print(f"  {bank} {f['prior_period']}→{period} {kind[:5]} {table}"
                      f": {len(f['scale_shifts'])} scale, {len(f['newly_absent'])} gone, "
                      f"{len(f['newly_present'])} new{flag}")

    conn.close()
    path = write_report(findings, Path(args.out), scanned)
    units = sum(1 for f in findings if f["unit_switch"])
    print(f"\n{scanned} seams compared, {len(findings)} raised something, "
          f"{units} look like a reporting-unit change")
    try:
        print(f"report → {path.relative_to(REPO)}")
    except ValueError:
        print(f"report → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
