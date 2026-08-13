#!/usr/bin/env python
"""Reconcile stored analytical figures against the cells the filing printed.

Every per-partition validator in this repo is an *internal* identity — assets =
liabilities, subtotal = Σchildren, closing = opening + flows. A uniform unit
change scales both sides equally, so all of them foot and every cell reads `ok`.
That is exactly how TEB 2026Q2 landed 1000× too small with a clean validation
run, and `docs/PROJECT_STATE.md` states the general rule it taught: **no
internal identity can detect a unit change; only a cross-period or external
anchor can.**

The document capture is that external anchor. A figure the extractor stored
should be the figure the filing printed, times the scale its declared unit
implies (`units.UNIT_SCALE`: bin ×1, milyon ×1000). Both halves of that come out
of the capture — the cells, and the unit declaration itself, read by the repo's
own `units.regex_unit` over the captured page text, so no PDF is needed.

    stored / expected_factor ∉ printed cells  →  invented, derived, or wrong
    stored matches at a DIFFERENT factor      →  a reporting-unit error

The second test is the valuable one, and the direction matters. A milyon filing
ingested correctly stores printed×1000, so "stored ÷ 1000 is printed" is the
HEALTHY state, not the bug. The bug is the reverse — TEB 2026Q2 declared Milyon
and was ingested at factor 1, so its figures matched the page exactly while
being 1000× too small against every other quarter. What this check looks for is
therefore a partition whose figures fit a factor OTHER than the one its own
declaration calls for.

Read-only. Touches no D1 row and rewrites nothing; it reads the capture ledger
and the audit snapshot and reports.

  python scripts/check_capture_reconcile.py --capture-db data/holdout_capture.db
  python scripts/check_capture_reconcile.py --bank GARAN --period 2026Q1 --verbose
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402

DEFAULT_CAPTURE = REPO / "data" / "bank_audit_capture.db"
DEFAULT_AUDIT = REPO / "data" / "bank_audit.db"

# Derived from other stored rows rather than read off the page, so their figures
# have no reason to appear as a printed cell. `units.money_columns` refuses
# these outright; listing them keeps the reason next to the exclusion.
DERIVED_TABLES = {"bank_audit_stages"}

# Measured over the 12-filing holdout, current engine: eleven readable filings
# reconcile at 96.6%-98.5%, and the twelfth (FIBA, whose statement pages are
# drawn as vector outlines) at 15.2%. 85% sits in the empty band between them
# with ~12 points of headroom, and a partial capture is reported separately
# rather than counted as a data defect.
MIN_RATE = 0.85
# A scale finding needs a floor and a decisive margin, so a handful of
# coincidental round numbers cannot raise one on their own.
SCALE_MIN_HITS = 20
SCALE_MARGIN = 3.0

# Every scale a declared unit can imply. A partition is expected to sit at the
# one its own declaration calls for; fitting a different one is the finding.
FACTORS = sorted(set(U.UNIT_SCALE.values()))


def _tables(conn: sqlite3.Connection) -> list[str]:
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    return [t for t in sorted(U.MONEY_COLUMNS)
            if t not in DERIVED_TABLES and t in have]


def printed_values(cap: sqlite3.Connection, key: tuple) -> set[float]:
    """Every numeric cell the filing printed, as magnitudes.

    Sign is dropped deliberately: BRSA prints deduction rows as "(-)" labels or
    parenthesised figures while the extractor stores them signed, so comparing
    signs would fail rows that are perfectly correct.
    """
    return {round(abs(v), 2) for (v,) in cap.execute(
        "SELECT value FROM bank_audit_document_cells WHERE bank_ticker=? AND "
        "period=? AND kind=? AND is_numeric=1 AND value IS NOT NULL", key)
        if v is not None}


def capture_gap(cap: sqlite3.Connection, key: tuple) -> int:
    """Pages whose tables were drawn, not typed — none of their rows exist."""
    try:
        return cap.execute(
            "SELECT COUNT(*) FROM bank_audit_document_pages WHERE bank_ticker=? "
            "AND period=? AND kind=? AND text_layer='vector'", key).fetchone()[0]
    except sqlite3.OperationalError:
        return 0                      # ledger predates the text_layer column


def declared_unit(cap: sqlite3.Connection, key: tuple) -> str | None:
    """The unit the filing declares, read off the capture rather than the PDF.

    `regex_unit` resolves by authority (transition statement, then unanimity,
    then majority) because a filing that switched to Milyon leaves stale
    boilerplate behind. It wants the front pages untruncated — the declaration
    sits as late as p17 on an annual report — so 25 are passed.
    """
    by_page: dict[int, list[str]] = {}
    for pg, txt in cap.execute(
            "SELECT page,text FROM bank_audit_document_lines WHERE bank_ticker=? "
            "AND period=? AND kind=? AND page<=25 ORDER BY page,line_order", key):
        by_page.setdefault(pg, []).append(txt or "")
    return U.regex_unit([" ".join(v) for _pg, v in sorted(by_page.items())])


def reconcile_one(cap, aud, key: tuple, tables: list[str]) -> dict:
    printed = printed_values(cap, key)
    unit = declared_unit(cap, key)
    expected = U.UNIT_SCALE.get(unit) if unit else None

    stored: dict[str, list[float]] = {}
    for t in tables:
        cols = sorted(U.money_columns(t))
        try:
            rows = aud.execute(
                f"SELECT {','.join(cols)} FROM {t} "  # noqa: S608 - names from a fixed registry
                "WHERE bank_ticker=? AND period=? AND kind=?", key).fetchall()
        except sqlite3.OperationalError:
            continue
        # A disclosed zero prints as "-", so it is not a figure to look for, and
        # `null` is not `0` — neither is evidence of anything here.
        vals = [abs(v) for row in rows for v in row if v is not None and abs(v) >= 1]
        if vals:
            stored[t] = vals

    at_factor = {f: sum(1 for vals in stored.values() for v in vals
                        if round(v / f, 2) in printed) for f in FACTORS}
    total = sum(len(v) for v in stored.values())
    # With no readable declaration there is no expectation to test against, so
    # the best-fitting factor is used for the coverage rate and the scale
    # verdict is withheld rather than guessed.
    best = max(at_factor, key=lambda f: at_factor[f]) if total else 1
    use = expected if expected is not None else best

    lanes = {t: {"found": (h := sum(1 for v in vals if round(v / use, 2) in printed)),
                 "total": len(vals), "rate": h / len(vals)}
             for t, vals in stored.items()}
    found = sum(v["found"] for v in lanes.values())
    return {"bank_ticker": key[0], "period": key[1], "kind": key[2],
            "unit": unit, "expected_factor": expected, "used_factor": use,
            "best_factor": best, "at_factor": at_factor,
            "stored": total, "found": found,
            "rate": (found / total) if total else None,
            "vector_pages": capture_gap(cap, key), "lanes": lanes}


def findings_for(r: dict) -> list[dict]:
    out: list[dict] = []
    if not r["stored"]:
        return out
    exp, best, at = r["expected_factor"], r["best_factor"], r["at_factor"]
    # Checked before the absence rule: a mis-scaled partition is also a low-rate
    # partition, and "the figures sit at the wrong scale" is the finding worth
    # reporting, not "the figures are missing".
    if exp is not None and best != exp and at[best] >= SCALE_MIN_HITS \
            and at[best] >= SCALE_MARGIN * max(at[exp], 1):
        out.append({
            "code": "unit_scale", "severity": "error",
            "detail": f"the filing declares {r['unit']!r} (×{exp}), but its "
                      f"stored figures fit ×{best}: {at[best]:,} match there "
                      f"against {at[exp]:,} at the declared scale. The partition "
                      f"looks stored {exp // best if exp > best else best // exp}× "
                      f"{'small' if best < exp else 'large'}. No internal identity "
                      f"can see this — see TEB 2026Q2 in PROJECT_STATE."})
        return out
    if exp is None:
        out.append({
            "code": "unit_unknown", "severity": "info",
            "detail": "no reporting unit could be read from the captured text, "
                      f"so the scale was not verified; figures were matched at "
                      f"the best-fitting ×{best}."})
    if r["vector_pages"]:
        # The capture is the incomplete side here, not the extraction. Saying
        # "figures absent" would blame the extractor for a hole in the evidence.
        out.append({
            "code": "capture_incomplete", "severity": "info",
            "detail": f"{r['vector_pages']} pages are drawn as vector outlines, "
                      f"so their rows were never captured; reconciliation is "
                      f"not meaningful for this filing "
                      f"(rate {r['rate']:.1%}). Recovering them needs OCR."})
        return out
    if r["rate"] is not None and r["rate"] < MIN_RATE:
        worst = sorted(r["lanes"].items(), key=lambda kv: kv[1]["rate"])[:3]
        lanes = ", ".join(f"{k.replace('bank_audit_', '')} {v['rate']:.0%}"
                          for k, v in worst)
        out.append({
            "code": "figures_absent", "severity": "error",
            "detail": f"only {r['rate']:.1%} of stored figures appear as cells "
                      f"the filing printed ({r['found']:,}/{r['stored']:,}); "
                      f"lowest lanes: {lanes}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture-db", default=str(DEFAULT_CAPTURE))
    ap.add_argument("--audit-db", default=str(DEFAULT_AUDIT))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--verbose", action="store_true", help="one line per partition")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--report-only", action="store_true",
                    help="always exit 0, even with findings")
    args = ap.parse_args()

    if not Path(args.capture_db).exists():
        print(f"no capture ledger at {args.capture_db} — run "
              f"scripts/backfill_document_capture.py first", file=sys.stderr)
        return 2
    cap = sqlite3.connect(f"file:{args.capture_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
    tables = _tables(aud)

    where, params = [], []
    for col, val in (("bank_ticker", args.bank), ("period", args.period),
                     ("kind", args.kind)):
        if val:
            where.append(f"{col}=?")
            params.append(val.upper() if col != "kind" else val)
    sql = ("SELECT DISTINCT bank_ticker,period,kind FROM bank_audit_document_pages"
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY 1,2,3")
    keys = cap.execute(sql, params).fetchall()
    if not keys:
        print("no captured partitions matched", file=sys.stderr)
        return 2

    reports, findings = [], []
    for key in keys:
        r = reconcile_one(cap, aud, key, tables)
        f = findings_for(r)
        r["findings"] = f
        reports.append(r)
        findings.extend({"bank_ticker": key[0], "period": key[1],
                         "kind": key[2], **x} for x in f)

    if args.json:
        print(json.dumps({"partitions": reports, "findings": findings}, indent=2))
    else:
        if args.verbose:
            print(f"{'filing':30} {'stored':>7} {'found':>7} {'rate':>7}  flags")
            for r in reports:
                flags = " ".join(x["code"] for x in r["findings"]) or "-"
                rate = f"{r['rate']:.1%}" if r["rate"] is not None else "-"
                name = f"{r['bank_ticker']} {r['period']} {r['kind']}"
                print(f"{name:30} {r['stored']:>7,} {r['found']:>7,} {rate:>7}  {flags}")
            print()
        checked = sum(1 for r in reports if r["stored"])
        errors = [f for f in findings if f["severity"] == "error"]
        for f in findings:
            mark = "ERROR" if f["severity"] == "error" else "info "
            print(f"{mark} {f['bank_ticker']} {f['period']} {f['kind']} "
                  f"[{f['code']}] {f['detail']}")
        print(f"\n{checked} partitions reconciled against the capture, "
              f"{len(errors)} with errors.")
    return 1 if (findings and not args.report_only
                 and any(f["severity"] == "error" for f in findings)) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
