#!/usr/bin/env python
"""The narrow lanes audited by the wide ones: every narrow row the graduated
lanes contradict, named.

The narrow lanes (bank_audit_capital, _liquidity, _npl_movement,
_loans_by_sector, _repricing, _fx_position in data/bank_audit.db) were
extracted one figure at a time with no identity of their own. The wide
lanes in data/bank_audit_tables.db are minted only when the regulator's
template arithmetic holds, and they carry the same figures. Where the two
disagree, the wide figure has an identity behind it and the narrow one
does not — so the disagreement is the narrow lane's repair list.

Reads both databases, prints a per-lane summary and writes the full list
to docs/knowledge/<date>-narrow-vs-wide-repair-list.md (gitignored, internal).
Read-only on both databases.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.numbered_template import fold  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"
KNOWLEDGE = REPO / "docs" / "knowledge"


def close(a, b, rel=1e-3, absolute=2.0) -> bool:
    return abs(a - b) <= max(absolute, rel * abs(b))


def audit(tab: sqlite3.Connection, aud: sqlite3.Connection) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = defaultdict(list)

    # --- capital: narrow total_capital / tier1 / cet1 vs the wide capital lane
    wide = {}
    for bank, per, kind, role, val in tab.execute(
            "SELECT bank_ticker, period, kind, row_role, amount FROM bank_audit_capital_full "
            "WHERE row_role IN ('cet1_total','tier1_total','total_own_funds') AND amount IS NOT NULL"):
        wide.setdefault((bank, per, kind, role), val)
    for bank, per, kind, cet1, t1, tot in aud.execute(
            "SELECT bank_ticker, period, kind, cet1_capital, tier1_capital, total_capital "
            "FROM bank_audit_capital WHERE period_type='current'"):
        for role, narrow in (("cet1_total", cet1), ("tier1_total", t1), ("total_own_funds", tot)):
            w = wide.get((bank, per, kind, role))
            if narrow is not None and w is not None and not close(narrow, w):
                out["bank_audit_capital"].append((bank, per, kind, role, narrow, w))

    # --- liquidity: narrow lcr_total / nsfr vs the wide LCR row 23 / NSFR row 34
    lcr = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, weighted_total FROM bank_audit_lcr_full "
        "WHERE period_label='current' AND template_row=23 AND weighted_total IS NOT NULL")}
    nsfr = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, weighted_total FROM bank_audit_nsfr_full "
        "WHERE period_label='current' AND template_row=34 AND weighted_total IS NOT NULL")}
    for bank, per, kind, n_lcr, n_nsfr in aud.execute(
            "SELECT bank_ticker, period, kind, lcr_total, nsfr FROM bank_audit_liquidity "
            "WHERE period_type='current'"):
        w = lcr.get((bank, per, kind))
        if n_lcr is not None and w is not None and not close(n_lcr, w, rel=5e-3, absolute=0.05):
            out["bank_audit_liquidity.lcr_total"].append((bank, per, kind, "lcr_total", n_lcr, w))
        w = nsfr.get((bank, per, kind))
        if n_nsfr is not None and w is not None and not close(n_nsfr, w, rel=5e-3, absolute=0.05):
            out["bank_audit_liquidity.nsfr"].append((bank, per, kind, "nsfr", n_nsfr, w))

    # --- npl_movement: narrow closing sum (III+IV+V) vs CR1 defaulted loans
    cr1 = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, defaulted_gross FROM bank_audit_credit_quality_full "
        "WHERE period_label='current' AND template_row=1 AND defaulted_gross IS NOT NULL")}
    sums: dict[tuple, float] = defaultdict(float)
    for b, p, k, v in aud.execute(
            "SELECT bank_ticker, period, kind, closing_balance FROM bank_audit_npl_movement "
            "WHERE period_type='current' AND closing_balance IS NOT NULL"):
        sums[(b, p, k)] += v
    for key, narrow in sums.items():
        w = cr1.get(key)
        if w is not None and not close(narrow, w):
            out["bank_audit_npl_movement.closing_sum"].append((*key, "closing III+IV+V", narrow, w))

    # --- loans_by_sector: every stage/ECL cell vs the gated wide sector lane
    wide_cells = {}
    for b, p, k, sector, col, v in tab.execute(
            "SELECT bank_ticker, period, kind, sector, column, amount FROM bank_audit_sector_full "
            "WHERE family='stage_ecl' AND period_label='current' AND instance_no=0 "
            "AND column IN ('stage2','stage3','ecl') AND sector IS NOT NULL AND amount IS NOT NULL"):
        wide_cells[(b, p, k, sector, col)] = v
    for b, p, k, sector, s2, s3, e in aud.execute(
            "SELECT bank_ticker, period, kind, sector, stage2_amount, stage3_amount, ecl_amount "
            "FROM bank_audit_loans_by_sector WHERE period_type='current'"):
        for col, narrow in (("stage2", s2), ("stage3", s3), ("ecl", e)):
            w = wide_cells.get((b, p, k, sector, col))
            if narrow is not None and w is not None and not close(narrow, w):
                out["bank_audit_loans_by_sector"].append((b, p, k, f"{sector}.{col}", narrow, w))

    # --- repricing: narrow rate-sensitive assets per bucket vs the wide total-assets row
    bucket_of = {"m1": ("1 AY", "1 MONTH", "UP TO 1"), "m1_3": ("1-3",), "m3_12": ("3-12",),
                 "y1_5": ("1-5",), "y5_plus": ("5 Y", "OVER 5"), "non_interest": ("FAIZSIZ", "NON", "INTEREST")}
    wide_rp = {}
    for b, p, k, band, v in tab.execute(
            "SELECT bank_ticker, period, kind, band, amount FROM bank_audit_section4_matrix_full "
            "WHERE family='repricing' AND period_label='current' AND instance_no=0 "
            "AND row_role='total_assets' AND amount IS NOT NULL"):
        wide_rp[(b, p, k, band)] = v
    for b, p, k, bucket, ta in aud.execute(
            "SELECT bank_ticker, period, kind, bucket, rate_sensitive_assets FROM bank_audit_repricing "
            "WHERE period_type='current' AND rate_sensitive_assets IS NOT NULL"):
        fb = fold(bucket or "")
        band = next((bd for bd, needles in bucket_of.items() if any(n in fb for n in needles)), None)
        w = wide_rp.get((b, p, k, band)) if band else None
        if w is not None and not close(ta, w):
            out["bank_audit_repricing.rate_sensitive_assets"].append((b, p, k, bucket, ta, w))

    # --- fx_position: narrow on-balance assets per currency vs the wide total-assets row
    wide_fx = {}
    for b, p, k, band, v in tab.execute(
            "SELECT bank_ticker, period, kind, band, amount FROM bank_audit_section4_matrix_full "
            "WHERE family='fx_position' AND period_label='current' AND instance_no=0 "
            "AND row_role='total_assets' AND amount IS NOT NULL"):
        wide_fx[(b, p, k, band)] = v
    for b, p, k, cur, ta in aud.execute(
            "SELECT bank_ticker, period, kind, currency, on_bs_assets FROM bank_audit_fx_position "
            "WHERE period_type='current' AND on_bs_assets IS NOT NULL"):
        c = fold(cur or "")
        band = ("eur" if "EUR" in c or "AVRO" in c else "usd" if "USD" in c or "DOLAR" in c
                else "other_fc" if "DIGER" in c or "OTHER" in c else "total" if "TOPLAM" in c or "TOTAL" in c
                else None)
        w = wide_fx.get((b, p, k, band)) if band else None
        if w is not None and not close(ta, w):
            out["bank_audit_fx_position.on_bs_assets"].append((b, p, k, cur, ta, w))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--no-write", action="store_true", help="print only; no knowledge file")
    args = ap.parse_args()
    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
    found = audit(tab, aud)

    lines = [f"# Narrow lanes audited by the wide lanes — {date.today().isoformat()}", "",
             "Status: repair list (open). Generated by `scripts/audit_narrow_vs_wide.py`;",
             "read-only on both databases. Each row: a narrow figure a gated wide lane",
             "contradicts. The wide figure has the template's identity behind it; the",
             "narrow one has none. Tolerance 0.1% (ratios 0.5%).", ""]
    total = 0
    for lane in sorted(found):
        rows = found[lane]
        total += len(rows)
        print(f"{lane:48} {len(rows):5} rows indicted")
        lines += [f"## {lane} — {len(rows)} rows", "", "| bank | period | kind | what | narrow | wide |",
                  "|---|---|---|---|---:|---:|"]
        for b, p, k, what, n, w in sorted(rows):
            lines.append(f"| {b} | {p} | {k} | {what} | {n:,.2f} | {w:,.2f} |")
        lines.append("")
    print(f"{'total':48} {total:5}")
    if not args.no_write:
        KNOWLEDGE.mkdir(exist_ok=True)
        path = KNOWLEDGE / f"{date.today().isoformat()}-narrow-vs-wide-repair-list.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
