"""Measure what the free-provision classifier change does to the whole corpus.

READ-ONLY. Downloads each audit PDF from R2 to a temp file, re-runs
`classify_free_provision`, and diffs the result against the value already stored
in the snapshot. Writes nothing — not D1, not R2, not the local snapshot.

It exists because the fix touches page SELECTION, which is corpus-wide: the
Turkish `k`→`ğ` softening alone widens the subject pattern everywhere, and the
first attempt regressed ZIRAAT into reading a pre-reversal gross. Every mover
has to be judged on the SENTENCE the classifier matched, which is why the
artifact carries both the new snippet and the stored one.

Runs in Actions, not locally: the PDFs live in R2 and the corpus is 1,061
partitions (580 of which currently carry a free-provision row).

    python scripts/measure_free_provision_change.py [--limit N] [--banks A,B]
"""
from __future__ import annotations

import argparse
import json
import re
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
from src.audit_reports.units import UnitContext  # noqa: E402

# Exactly the column list upsert_free_provision passes, so the measurement
# scales what production scales — if MONEY_COLUMNS moves, this follows.
_FP_COLS = ["bank_ticker", "period", "kind", "free_provision",
            "free_provision_prior", "source_page", "source_text"]


def _canonical(res, part, pdf: Path):
    """The classifier's raw amounts, normalised the way production stores them.

    The classifier reads what the PAGE prints. Since 2026Q2 that page is in
    Milyon TL, and `upsert_free_provision` multiplies by the filing's factor on
    the way into the row. Comparing the raw read against a canonical `bin` row
    makes every non-overridden Q2 disclosure look like a mover — ENPARA stores
    2,500,000 from a printed "2.500", so a 1000x false positive would have been
    reported as a regression of the fix.
    """
    unit = UnitContext.for_partition(part[1], str(pdf))
    row = unit.scale_rows(
        "bank_audit_free_provision", _FP_COLS,
        [(part[0], part[1], part[2], res.free_provision,
          res.free_provision_prior, res.source_page, res.snippet or "")])[0]
    return row[3], row[4], unit.source_unit

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
    ap.add_argument("--context", default="",
                    help="BANK:PERIOD:KIND[,…] — dump the full wording around "
                         "every free-provision mention and stop. Read-only; for "
                         "judging a mover by its sentence rather than its number.")
    args = ap.parse_args()

    if args.context:
        wanted = {tuple(x.split(":")) for x in args.context.split(",") if x}
        for ticker, period, kind, key in sorted(r2_storage.list_audit_pdfs()):
            if (ticker.upper(), period.upper(), kind) not in wanted:
                continue
            with tempfile.TemporaryDirectory() as td:
                dest = Path(td) / "r.pdf"
                r2_storage.download_to(key, dest)
                print(f"\n===== {ticker} {period} {kind}", flush=True)
                for pno, page in enumerate(_pages(dest), 1):
                    flat = re.sub(r"\s+", " ", page)
                    for m in re.finditer(r"serbest\s+kar[şs][ıi]l[ıiğ]", flat, re.I):
                        s = max(0, m.start() - 320)
                        print(f"  p{pno}: …{flat[s:m.start() + 420]}…\n")
        return 0

    conn = sqlite3.connect(args.db)
    stored = {
        (b, p, k): (fp, pr, sp, (txt or "")[:200])
        for b, p, k, fp, pr, sp, txt in conn.execute(
            "SELECT bank_ticker, period, kind, free_provision, "
            "free_provision_prior, source_page, source_text "
            "FROM bank_audit_free_provision")
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
                fp, prior, unit_read = _canonical(res, part, dest)
            except Exception as e:                              # noqa: BLE001
                unreadable.append((*part, f"{type(e).__name__}: {e}"))
                continue
        old = stored.get(part)
        new = (fp, prior, res.source_page)
        snip = re.sub(r"\s+", " ", res.snippet or "").strip()[:200]
        if old is None:
            if res.disclosed:
                changed.append((*part, None, new, unit_read, snip, ""))
            continue
        if (old[0], old[1]) != (new[0], new[1]):
            # The stored snippet matters most where the NEW read has none:
            # ZIRAATK's correction removes a value, so only the old sentence
            # can show what was being relied on.
            changed.append((*part, old[:3], new, unit_read, snip, old[3]))
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
    for b, p, k, old, new, unit_read, snip, old_snip in sorted(changed):
        print(f"  {b:8s} {p} {k:14s} [{unit_read}]  {old} -> {new}")
        print(f"      old: {old_snip or '(none stored)'}")
        print(f"      new: {snip or '(no sentence matched)'}")
    for row in sorted(unreadable):
        print(f"  [unreadable] {row}")

    expected = {("TEB", "2026Q1", "consolidated"), ("TEB", "2026Q1", "unconsolidated"),
                ("ZIRAATK", "2024Q1", "consolidated"),
                ("ZIRAATK", "2024Q1", "unconsolidated")}
    actual = {(b, p, k) for b, p, k, *_ in changed}
    print("\nexpected to change:", sorted(expected))
    print("unexpected movers :", sorted(actual - expected) or "NONE")
    print("expected but still:", sorted(expected - actual) or "NONE")

    Path("free_provision_change.json").write_text(
        json.dumps({"changed": [{"bank": b, "period": p, "kind": k,
                                 "old": old, "new": new, "unit_read": u,
                                 "snippet": s, "old_snippet": os_}
                                for b, p, k, old, new, u, s, os_ in changed],
                    "unreadable": unreadable, "unchanged": same}, default=str),
        encoding="utf-8")
    # Read-only measurement: never fail the run on data, only on a crash.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
