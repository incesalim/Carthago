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
import math
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import registry as reg          # noqa: E402
from src.audit_reports.triage import value_columns     # noqa: E402

DEFAULT_OUT = REPO / "docs" / "knowledge" / "triage"

#: How far from a power of ten a move may land and still count as one, in
#: DECADES: 0.25 is a factor of ~1.8 either side.
#:
#: ⚠️ This was ±0.5% around an exact ×1000, which meant the check fired only if
#: the bank's balance sheet had not moved AT ALL between the two quarters.
#: Measured on the real seam it exists for — ANADOLU 2026Q2 unconsolidated,
#: stored 1000x small — the ratio is 0.00109, not 0.001, because the bank also
#: grew 9%. It was 0.00105 at 5% growth and 0.00121 at 21%. Every one of those
#: missed. The repo had already written the evidence down and not applied it
#: here: TEB's 2026Q2 ratio is recorded in PROJECT_STATE as "950.6 (not exactly
#: 1000 because the bank also grew ~5%)", and the SQL sweep that found it used a
#: deliberately wide band, `> 50 or < 0.02`.
#:
#: So the test is on the ORDER OF MAGNITUDE, not on an exact multiple. A quarter
#: of real change never crosses a decade; a unit error always does. At 0.25 a
#: genuine 5x move stays clear (0.30 decades) while an 8x move is reported —
#: which is worth a look regardless, and this lane only ever raises an alert.
_SCALE_DECADE_TOL = 0.25

#: Ratios that an actual denomination change can produce. `units.UNIT_SCALE` is
#: {bin: 1, milyon: 1_000, milyar: 1_000_000}, so every confusion between two of
#: them is ×1000 or ×1,000,000, either direction. ×10 and ×100 are real findings
#: worth printing, but they are not a reporting unit and must not raise the
#: alarm that is.
_UNIT_RATIOS = frozenset({1e3, 1e6, 1e-3, 1e-6})

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
    """The power of ten between two values, if the move spans whole decades.

    Sign changes are not scale changes — a provision flipping +x to -x is a
    different question — so both values must share a sign.
    """
    if not before or not now or (now > 0) != (before > 0):
        return None
    decades = math.log10(abs(now / before))
    nearest = round(decades)
    if nearest == 0 or abs(decades - nearest) > _SCALE_DECADE_TOL:
        return None
    return 10.0 ** nearest


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
            # Material in EITHER quarter. Testing only `now` hid the exact case
            # this exists for: a shrunk-by-1000 row is tiny by construction, so
            # ANADOLU's 212.6bn of assets became 212,600 and fell under the
            # 1,000,000 floor — the error made itself invisible to the check.
            if prev_v is None or max(abs(v), abs(prev_v)) < min_amount:
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

    # One row moving by a decade is a correction; a statement moving TOGETHER by
    # a factor that is actually a unit ratio is the filing changing denomination.
    #
    # Two things this got wrong, both visible in its own output as rows moved
    # "7/5" — more rows than the statement has:
    #
    #  * it counted CELLS against ROWS. `shifts` holds one entry per (row,
    #    column), so a 4-row table with three value columns could report 12
    #    against 4 and clear any share test. Distinct rows is the honest count.
    #  * it accepted any power of ten. A Turkish filing denominates in bin,
    #    milyon or milyar, so a unit confusion is ×1000 or ×1,000,000 and never
    #    ×10 — yet ×10 in the 4-row FX-position table was 13 of the 30 findings
    #    on a corpus with no unit error left in it. A single currency moving a
    #    decade is an FX question, not a denomination change.
    by_rows: dict[float, set[str]] = collections.defaultdict(set)
    for s in shifts:
        by_rows[s["factor"]].add(s["row"])
    unit_switch = None
    for f, rows in sorted(by_rows.items(), key=lambda kv: -len(kv[1])):
        if f not in _UNIT_RATIOS:
            continue
        if len(rows) >= 3 and len(rows) >= 0.6 * len(now):
            unit_switch = {"factor": f, "rows": len(rows), "of": len(now)}
        break
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


def alert_unit_switches(findings: list[dict]) -> None:
    """Ping Telegram/Discord when a partition looks denominated differently from
    the quarter before it.

    ONLY unit switches. The seam report also lists ×10 moves, rows that vanished
    and rows that appeared, and there are thousands of those across the corpus —
    real questions, but a daily message carrying them is a daily message nobody
    reads. A unit switch is the one finding here that is silent everywhere else
    in the system and wrong every time it appears: the corpus baseline is zero
    across 15,638 seams and 4.5 years.
    """
    switches = [f for f in findings if f["unit_switch"]]
    if not switches:
        print("[watch] no reporting-unit change against the prior quarter",
              flush=True)
        return
    lines = []
    for f in switches[:6]:
        u = f["unit_switch"]
        lines.append(f"• {f['bank_ticker']} {f['prior_period']}→{f['period']} "
                     f"{f['kind'][:5]} {f['table'].replace('bank_audit_', '')}: "
                     f"×{u['factor']:g} on {u['rows']}/{u['of']} rows")
    more = f"\n…and {len(switches) - 6} more" if len(switches) > 6 else ""
    msg = (f"🚨 Audit reporting-unit change: {len(switches)} partition(s) are "
           f"denominated differently from the quarter before.\n"
           + "\n".join(lines) + more +
           "\nEvery in-filing identity still passes when this happens — check "
           "the filing's declared unit before trusting the figures.")
    try:
        subprocess.run([sys.executable, str(REPO / "scripts" / "notify.py"), msg],
                       check=False)
    except Exception as e:                                       # noqa: BLE001
        print(f"[watch] notify failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--alert", action="store_true",
                    help="send a Telegram/Discord message when a partition's "
                         "denomination moved against the prior quarter, and "
                         "always exit 0 (alert-only; never blocks a pipeline).")
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
        # Alert-only callers are wired into a pipeline that has already written
        # its rows; a missing snapshot is their problem to report, not a reason
        # for this step to take the job down with it.
        return 0 if args.alert else 1
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
    if args.alert:
        alert_unit_switches(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
