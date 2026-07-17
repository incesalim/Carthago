"""One-time cleanup of page-artefact rows in bank_audit_oci.

The OCI sibling of the defect dedup_hierarchy_rows.py already cleaned out of the
frozen BS/PL tables — the same fingerprint ("a statement TITLE mis-parsed as a
data row with a garbage amount (<=202)"), never extended here.

Two artefact shapes, both from the OCI page's own furniture:
  * the DATE HEADER — "31 MART 2024 TARİHİNDE SONA EREN ARA HESAP DÖNEMİNE AİT…"
    parsed as hierarchy '31', item_name 'MART', amount 202.0. The 202 is the bare
    4-digit year truncated to its first thousands group ("2024" -> 202), which is
    why 2023 and 2024 both yield exactly 202.0 — the fingerprint to grep for.
  * the STATEMENT TITLE — "KAR VEYA ZARAR VE DİĞER KAPSAMLI GELİR TABLOSU" /
    "UNCONSOLIDATED STATEMENT OF PROFIT OR LOSS AND OTHER COMPREHENSIVE INCOME"
    parsed under the section's OWN roman ('IV.', 'V.'), also with amount 202.0.

Why they survived: a stray takes no part in III = I + II, so no identity ever
touched it and every affected cell read green. 577 rows across 574 of 1050
partitions — 55% of the corpus — invisible to every check.

Data-only, values are only ever DELETED, never edited. The predicate is the OCI
template itself (romans I/II/III + the 2.x sub-tree), which is exact rather than
heuristic:
  * 16,709 rows conform; 577 do not; nothing is ambiguous.
  * every non-conforming row is a date/title fragment — verified by reading all 6
    distinct off-template keys ('31' x238, '30' x202, '1' x96, 'IV.' x37, 'V.' x3,
    '30.06.' x1) and every one of the 3 whose amount is not 202.
  * no real row anywhere carries amount == 202.0, and no roman above III exists in
    a real OCI row (every 'IV.'/'V.' row has min == max == 202.0).
So the filter cannot take data.

Recurrence is prevented at the source by oci._drop_offtemplate (the extractor
guard) and surfaced by validator.check_oci's `oci_offtemplate_row` — this script
only clears what was already stored, since the lane is not being re-extracted.

  python scripts/clean_oci_header_rows.py [--db data/bank_audit.db] [--apply]

Dry by default — pass --apply to write. This one only touches the LOCAL DB and
bumps extracted_at on the partitions it changes; push the result with
    python scripts/sync_audit_expected.py --db data/bank_audit.db --push
and clear/re-push the affected partitions the way apply_overrides.py does.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports.validator import _OCI_TEMPLATE_RX  # noqa: E402


def find_strays(conn: sqlite3.Connection) -> list[tuple]:
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, item_order, hierarchy, item_name, amount "
        "FROM bank_audit_oci").fetchall()
    return [r for r in rows
            if not _OCI_TEMPLATE_RX.fullmatch((r[4] or "").strip())]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--apply", action="store_true", help="write (default: dry)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    strays = find_strays(conn)
    parts = sorted({(r[0], r[1], r[2]) for r in strays})
    total = conn.execute("SELECT COUNT(*) FROM bank_audit_oci").fetchone()[0]
    print(f"[oci-clean] {len(strays)} off-template rows across {len(parts)} partitions "
          f"({total:,} rows total)")

    # Belt-and-braces guard. The off-template predicate is already exact, but a
    # stray carrying a plausible AMOUNT would mean it has drifted, so stop and let
    # a human look rather than delete on faith.
    #
    # Two artefact amounts are expected and explained:
    #   <=202   the Turkish header's year truncated at the thousands separator
    #           ("31 MART 2024 …" -> 202). 576 of the 577.
    #   a bare  the same header in an ENGLISH filing, where no separator splits
    #   year    the year, so it survives whole: TSKB 2023Q2 cons carries 2023.0 at
    #           hierarchy '1' with item_name 'January 2023 - 1 January 2022-'.
    #           Same artefact, different number.
    # Anything else is unexplained.
    def _explained(a: float) -> bool:
        a = abs(a or 0)
        return a <= 202 or 2000 <= a <= 2100

    big = [r for r in strays if not _explained(r[6])]
    if big:
        print(f"[oci-clean] ABORT — {len(big)} off-template rows carry an unexplained "
              "amount; these may be real. Investigate before deleting:")
        for r in big[:10]:
            print("   ", r)
        return 1

    for r in strays[:8]:
        print(f"    {r[0]:8} {r[1]} {r[2][:5]:5} order={r[3]:<3} "
              f"{r[4]!r:8} {(r[5] or '')[:34]!r:36} {r[6]}")
    if len(strays) > 8:
        print(f"    … and {len(strays) - 8} more")

    if not args.apply:
        print("[oci-clean] dry run — pass --apply to delete")
        return 0

    n = 0
    for b, p, k, io, *_ in strays:
        conn.execute("DELETE FROM bank_audit_oci WHERE bank_ticker=? AND period=? "
                     "AND kind=? AND item_order=?", (b, p, k, io))
        n += 1
    # bank_audit_oci has NO extracted_at of its own — push_to_d1 windows it on the
    # PARENT log, bank_audit_extractions.extracted_at (same as the rest of the
    # BS/PL family). Bump that, or the --hours push skips these partitions.
    for b, p, k in parts:
        conn.execute("UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                     "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k))
    conn.commit()
    left = len(find_strays(conn))
    print(f"[oci-clean] deleted {n} rows; {left} off-template rows remain")
    conn.close()
    return 0 if left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
