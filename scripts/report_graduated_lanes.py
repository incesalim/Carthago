#!/usr/bin/env python
"""The graduated lanes in one table: for every bank_audit_*_full table in
data/bank_audit_tables.db — filings covered (of the document layer's
partitions), banks, periods, rows, and the share of the 1,095 filings with
at least one minted instance, plus a per-bank coverage matrix.

Read-only. Prints the summary; writes the full report (with the per-bank
matrix) to docs/knowledge/<date>-graduated-lanes-readiness.md (gitignored,
internal). The anchor and refusal rates live in each builder's dry-run
output and PROJECT_STATE; this report is the coverage side.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TABLES_DB = REPO / "data" / "bank_audit_tables.db"
KNOWLEDGE = REPO / "docs" / "knowledge"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)

    partitions = {tuple(r) for r in tab.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_document_tables")}
    banks = sorted({b for b, _p, _k in partitions})
    n_part = len(partitions)
    lanes = [t for (t,) in tab.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bank_audit_%_full' ORDER BY name")]

    rows_out = []
    matrix: dict[str, dict[str, float]] = {}
    for t in lanes:
        cols = [r[1] for r in tab.execute(f"PRAGMA table_info({t})")]
        if not {"bank_ticker", "period", "kind"} <= set(cols):
            continue
        n_rows = tab.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        covered = {tuple(r) for r in tab.execute(f"SELECT DISTINCT bank_ticker, period, kind FROM {t}")}
        n_banks = len({b for b, _p, _k in covered})
        n_periods = len({p for _b, p, _k in covered})
        rows_out.append((t.replace("bank_audit_", "").replace("_full", ""), len(covered), n_part,
                         len(covered) / n_part if n_part else 0.0, n_banks, n_periods, n_rows))
        per_bank = {}
        for b in banks:
            have = sum(1 for (bb, _p, _k) in covered if bb == b)
            total = sum(1 for (bb, _p, _k) in partitions if bb == b)
            per_bank[b] = have / total if total else 0.0
        matrix[t] = per_bank

    rows_out.sort(key=lambda r: -r[1])
    lines = [f"# Graduated lanes — readiness {date.today().isoformat()}", "",
             f"Document layer: {n_part} partitions, {len(banks)} banks. Coverage = filings with ≥1 minted instance.", "",
             "| lane | filings | coverage | banks | periods | rows |", "|---|---:|---:|---:|---:|---:|"]
    print(f"{'lane':28} {'filings':>8} {'cover':>7} {'banks':>5} {'periods':>7} {'rows':>10}")
    total_rows = 0
    for name, cov, n, share, nb, np_, nr in rows_out:
        total_rows += nr
        print(f"{name:28} {cov:8} {share:7.1%} {nb:5} {np_:7} {nr:10,}")
        lines.append(f"| {name} | {cov} / {n} | {share:.1%} | {nb} | {np_} | {nr:,} |")
    print(f"{'total':28} {'':8} {'':7} {'':5} {'':7} {total_rows:10,}")
    lines += ["", f"Total rows across lanes: {total_rows:,}.", "", "## Coverage by bank (share of the bank's filings)", "",
              "| lane | " + " | ".join(banks) + " |", "|---|" + "---:|" * len(banks)]
    for t, per_bank in matrix.items():
        lines.append(f"| {t.replace('bank_audit_', '').replace('_full', '')} | "
                     + " | ".join(f"{per_bank[b]:.0%}" if per_bank[b] else "·" for b in banks) + " |")
    if not args.no_write:
        KNOWLEDGE.mkdir(exist_ok=True)
        path = KNOWLEDGE / f"{date.today().isoformat()}-graduated-lanes-readiness.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
