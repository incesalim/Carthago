"""Measure what the free-provision classifier change does to the whole corpus.

READ-ONLY. Downloads each audit PDF from R2 to a temp file, re-runs
`classify_free_provision`, and diffs the result against the value already stored
in the snapshot. Writes nothing — not D1, not R2, not the local snapshot.

It exists because the fix touches page SELECTION, which is corpus-wide: the
Turkish `k`→`ğ` softening alone widens the subject pattern everywhere. Two
partitions are known to be wrong (TEB 2026Q1) and two more carry the same
fingerprint (ZIRAATK 2024Q1); anything ELSE that moves is a regression and has
to be looked at by hand.

Runs in Actions, not locally: the PDFs live in R2 and the corpus is ~580
partitions.

    python scripts/measure_free_provision_change.py [--limit N] [--banks A,B]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.free_provision import (  # noqa: E402
    classify_free_provision, _override_for,
)

DB = REPO / "data" / "bank_audit.db"


def _pages(pdf: Path) -> list[str]:
    from src.audit_reports.extractor import _fitz_page_count, _fitz_page_text
    n = _fitz_page_count(str(pdf)) or 0
    return [_fitz_page_text(str(pdf), i) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--limit", type=int, default=0, help="0 = the whole corpus")
    ap.add_argument("--banks", default="", help="comma-separated, blank = all")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    stored = {
        (b, p, k): (fp, pr, sp)
        for b, p, k, fp, pr, sp in conn.execute(
            "SELECT bank_ticker, period, kind, free_provision, "
            "free_provision_prior, source_page FROM bank_audit_free_provision")
    }
    print(f"[measure] {len(stored)} stored free-provision rows", flush=True)

    only = {b.strip().upper() for b in args.banks.split(",") if b.strip()}
    pdfs = r2_storage.list_audit_pdfs()
    if only:
        pdfs = [p for p in pdfs if p[0].upper() in only]
    if args.limit:
        pdfs = pdfs[: args.limit]
    print(f"[measure] {len(pdfs)} PDFs to scan", flush=True)

    changed, unreadable, same = [], [], 0
    for i, (ticker, period, kind, key) in enumerate(sorted(pdfs), 1):
        part = (ticker.upper(), period.upper(), kind)
        # A curated override short-circuits extraction in production, so its
        # partitions cannot move and must not be counted as if they could.
        if _override_for(*part) is not None:
            continue
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "r.pdf"
            try:
                r2_storage.download_to(key, dest)
                res = classify_free_provision(_pages(dest))
            except Exception as e:                              # noqa: BLE001
                unreadable.append((*part, f"{type(e).__name__}: {e}"))
                continue
        old = stored.get(part)
        new = (res.free_provision, res.free_provision_prior, res.source_page)
        if old is None:
            if res.disclosed:
                changed.append((*part, None, new))
            continue
        if (old[0], old[1]) != (new[0], new[1]):
            changed.append((*part, old, new))
        else:
            same += 1
        if i % 50 == 0:
            print(f"[measure] {i}/{len(pdfs)} … {len(changed)} changed",
                  flush=True)

    print("\n" + "=" * 72)
    print(f"unchanged        : {same}")
    print(f"CHANGED          : {len(changed)}")
    print(f"unreadable       : {len(unreadable)}")
    print("=" * 72)
    for b, p, k, old, new in sorted(changed):
        print(f"  {b:8s} {p} {k:14s}  {old} -> {new}")
    for row in sorted(unreadable):
        print(f"  [unreadable] {row}")

    expected = {("TEB", "2026Q1", "consolidated"), ("TEB", "2026Q1", "unconsolidated"),
                ("ZIRAATK", "2024Q1", "consolidated"),
                ("ZIRAATK", "2024Q1", "unconsolidated")}
    actual = {(b, p, k) for b, p, k, _, _ in changed}
    print("\nexpected to change:", sorted(expected))
    print("unexpected movers :", sorted(actual - expected) or "NONE")
    print("expected but still:", sorted(expected - actual) or "NONE")

    Path("free_provision_change.json").write_text(
        json.dumps({"changed": [[b, p, k, old, new] for b, p, k, old, new in changed],
                    "unreadable": unreadable, "unchanged": same}, default=str),
        encoding="utf-8")
    # Read-only measurement: never fail the run on data, only on a crash.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
