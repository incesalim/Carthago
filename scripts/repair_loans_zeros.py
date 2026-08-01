#!/usr/bin/env python3
"""Restore the zeros `_save_loans` discarded, from the raw responses we kept.

THE DEFECT (fixed in the scraper on 2026-08-01; this repairs the history)

`_save_loans` selected a value with `get_val("A") or get_val("B") or ...`. `or`
is falsy-based, so a genuine reported `0` was treated as missing and the chain
fell through to a candidate column absent from that table — storing NULL.

BDDK sends nil as the integer `0`: never null, never empty, never a dash. So
every real zero in the five `or`-chained columns was lost. Measured before the
fix: `total_tl` and `total_fx` held **zero zeros across the whole table**, while
table 4's `Yp` column alone reports 19,139 of them — and the stored NULL count
matched that number exactly. The four maturity-split columns never used an `or`
chain and kept their zeros, which is what identified the cause.

It is not cosmetic. The biggest affected block is consumer-loan FX, where zero
is Decree 32 — residents without FX income may not borrow in foreign currency.
Stored as NULL, a legal prohibition reads as "we don't know", and any "FX share
of consumer lending" view renders blank where the honest answer is a hard zero.

WHY THIS CAN BE REPAIRED AT ALL

`raw_api_responses` keeps BDDK's JSON verbatim (~13k responses), so the true
values are still on disk. Nothing has to be re-fetched.

WRITE BUDGET

Rows *written* to D1 cost ~1000× a read, so this updates **only rows whose value
actually changes** — it never re-stamps a row that already holds the right
number. Expect tens of thousands of updated cells, not the whole table.

RUN IT IN CI, NOT LOCALLY. The local snapshot is whatever was last pulled; the
authoritative one lives in R2. Order matters: pull snapshot → run this → push
the `loans` table to D1 → upload the snapshot back. Skipping the upload leaves
the next pull re-introducing the NULLs.

    python scripts/repair_loans_zeros.py                 # dry run (default)
    python scripts/repair_loans_zeros.py --apply         # write to the snapshot
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data" / "bddk_data.db"

# Only table 3–7 rows land in `loans` (see parse_and_save_table).
LOANS_TABLES = (3, 4, 5, 6, 7)

# The five columns that used an `or` chain, with their candidate source columns
# IN PRECEDENCE ORDER — identical to the fixed scraper.
CHAINS: dict[str, tuple[str, ...]] = {
    "total_tl": ("ToplamTp", "Tp", "NakdiKrediTp"),
    "total_fx": ("ToplamYp", "Yp", "NakdiKrediYp"),
    "total_amount": ("Toplam", "NakdiKrediToplam", "ToplamNakdi"),
    "npl_amount": ("Takipteki", "TakipKrediToplam"),
    "non_cash_amount": ("GayriNakdi", "GayriNakdiKrediToplam"),
}


def first_val(cells: list, columns: dict, names: tuple[str, ...]):
    """First candidate column PRESENT — not the first truthy value."""
    for name in names:
        if name in columns and len(cells) > columns[name]:
            v = cells[columns[name]]
            if v is not None and v != "":
                return v
    return None


def derive(response_json: str) -> dict[int, dict[str, object]]:
    """{item_order: {column: true_value}} from one stored raw response."""
    payload = json.loads(response_json)
    j = payload.get("Json", {})
    rows = j.get("data", {}).get("rows", [])
    if not rows:
        return {}

    columns = {
        m.get("name", ""): i
        for i, m in enumerate(j.get("colModels", []))
    }

    out: dict[int, dict[str, object]] = {}
    for n, row in enumerate(rows):
        cells = row.get("cell", [])
        if len(cells) < 4:
            continue
        order = cells[columns["BasitSira"]] if "BasitSira" in columns else n + 1
        out[order] = {col: first_val(cells, columns, names) for col, names in CHAINS.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true",
                    help="write the corrections (default is a dry run)")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"repair_loans_zeros: no database at {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    raws = cur.execute(
        "SELECT table_number, year, month, currency, bank_type_code, response_json "
        "  FROM raw_api_responses WHERE table_number IN (%s)"
        % ",".join("?" * len(LOANS_TABLES)),
        LOANS_TABLES,
    ).fetchall()
    print(f"raw responses for the loans tables: {len(raws)}")

    fixed = Counter()
    disagreements = Counter()
    updates: list[tuple] = []

    for raw in raws:
        try:
            truth = derive(raw["response_json"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"  [skip] {raw['table_number']}/{raw['year']}-{raw['month']}"
                  f"/{raw['currency']}/{raw['bank_type_code']}: {exc}")
            continue
        if not truth:
            continue

        stored = cur.execute(
            # `rowid` is aliased to the table's INTEGER PRIMARY KEY, so the result
            # column comes back named `id` — alias it so the name is ours.
            "SELECT rowid AS rid, item_order, total_tl, total_fx, total_amount, "
            "       npl_amount, non_cash_amount FROM loans "
            " WHERE table_number=? AND year=? AND month=? AND currency=? AND bank_type_code=?",
            (raw["table_number"], raw["year"], raw["month"], raw["currency"],
             raw["bank_type_code"]),
        ).fetchall()

        for row in stored:
            want = truth.get(row["item_order"])
            if want is None:
                continue
            sets, vals = [], []
            for col in CHAINS:
                new, old = want[col], row[col]
                if new is None or old == new:
                    continue
                # The defect only ever turned a real value into NULL. Anything
                # else is a different problem — count it, don't silently rewrite.
                if old is not None:
                    disagreements[col] += 1
                    continue
                sets.append(f"{col}=?")
                vals.append(new)
                fixed[col] += 1
            if sets:
                # Bump `downloaded_at` on the corrected rows ONLY. push_to_d1
                # selects by that column, so this makes the incremental push
                # carry exactly these rows — no full rebuild, and no re-stamping
                # of rows whose values did not change (rows WRITTEN are the D1
                # cost centre, ~1000× a read).
                sets.append("downloaded_at=CURRENT_TIMESTAMP")
                updates.append((f"UPDATE loans SET {', '.join(sets)} WHERE rowid=?",
                                (*vals, row["rid"])))

    print("\ncells to restore (NULL -> reported value):")
    for col in CHAINS:
        print(f"  {col:<18} {fixed[col]:>8,}")
    print(f"  {'TOTAL':<18} {sum(fixed.values()):>8,} cells across {len(updates):,} rows")

    if disagreements:
        print("\n⚠️  non-NULL stored values that disagree with the raw response "
              "(NOT touched — a different defect, investigate separately):")
        for col, n in disagreements.items():
            print(f"  {col:<18} {n:>8,}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    for sql, params in updates:
        cur.execute(sql, params)
    conn.commit()
    print(f"\napplied: {len(updates):,} rows updated in {args.db}")
    print("NEXT: push_to_d1.py --only-tables loans, then re-upload the snapshot to R2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
