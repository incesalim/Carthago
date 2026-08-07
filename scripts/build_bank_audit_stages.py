"""Build the bank_audit_stages table from bank_audit_credit_quality.

Consolidates the Stage 1/2/3 amount + ECL provision disclosures that banks
publish in 2-4 different sections (depending on report format) into one
clean per-(bank, period, kind, period_type) row with coverage ratios.

Source priority per stage figure:
  amounts:
    1st  section='loans_amounts'        — single inline row, AKBNK-style
    2nd  section='loans_by_stage' (S1+S2) + section='npl_brsa_gross' (S3)
  ECL provisions:
    1st  section='loans_ecl'            — full S1/S2/S3
    2nd  section='loans_ecl_brsa' (S1+S2) + section='npl_brsa_provision' (S3)

Idempotent: re-running wipes and rebuilds bank_audit_stages, so it can be
called after every re-extract.

Usage:
    python scripts/build_bank_audit_stages.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"


_SQL_AGG = """
WITH
  amounts AS (
    SELECT bank_ticker, period, kind, period_type,
           stage1_amount AS s1_amount,
           stage2_amount AS s2_amount,
           stage3_amount AS s3_amount,
           total_amount  AS tot_amount
    FROM bank_audit_credit_quality
    WHERE section='loans_amounts'
  ),
  s12 AS (
    SELECT bank_ticker, period, kind, period_type,
           stage1_amount, stage2_amount
    FROM bank_audit_credit_quality
    WHERE section='loans_by_stage'
  ),
  s3 AS (
    -- npl_brsa_gross.total_amount is the sum of groups III+IV+V — the
    -- full Stage 3 loan amount per the BRSA classification.
    SELECT bank_ticker, period, kind, period_type,
           total_amount AS s3_amount
    FROM bank_audit_credit_quality
    WHERE section='npl_brsa_gross'
  ),
  ecl AS (
    SELECT bank_ticker, period, kind, period_type,
           stage1_amount AS s1_ecl,
           stage2_amount AS s2_ecl,
           stage3_amount AS s3_ecl
    FROM bank_audit_credit_quality
    WHERE section='loans_ecl'
  ),
  ecl_brsa AS (
    SELECT bank_ticker, period, kind, period_type,
           stage1_amount AS s1_ecl, stage2_amount AS s2_ecl
    FROM bank_audit_credit_quality
    WHERE section='loans_ecl_brsa'
  ),
  s3_prov AS (
    SELECT bank_ticker, period, kind, period_type,
           total_amount AS s3_ecl
    FROM bank_audit_credit_quality
    WHERE section='npl_brsa_provision'
  ),
  -- Cartesian of every (bank, period, kind, period_type) appearing in any
  -- of the source sections. UNION (not UNION ALL) so we get distinct
  -- tuples without duplicates.
  base AS (
    SELECT bank_ticker, period, kind, period_type FROM amounts
    UNION SELECT bank_ticker, period, kind, period_type FROM s12
    UNION SELECT bank_ticker, period, kind, period_type FROM s3
    UNION SELECT bank_ticker, period, kind, period_type FROM ecl
    UNION SELECT bank_ticker, period, kind, period_type FROM ecl_brsa
    UNION SELECT bank_ticker, period, kind, period_type FROM s3_prov
  )
SELECT
  b.bank_ticker, b.period, b.kind, b.period_type,
  -- amounts: prefer inline, fall back to 7.2 + BRSA
  COALESCE(a.s1_amount,  s12.stage1_amount)               AS s1_amt,
  COALESCE(a.s2_amount,  s12.stage2_amount)               AS s2_amt,
  COALESCE(a.s3_amount,  s3.s3_amount)                    AS s3_amt,
  -- ECL: prefer loans_ecl (full), fall back to loans_ecl_brsa + BRSA prov
  COALESCE(e.s1_ecl,     eb.s1_ecl)                       AS s1_ecl,
  COALESCE(e.s2_ecl,     eb.s2_ecl)                       AS s2_ecl,
  COALESCE(e.s3_ecl,     sp.s3_ecl)                       AS s3_ecl
FROM base b
LEFT JOIN amounts  a   USING (bank_ticker, period, kind, period_type)
LEFT JOIN s12          USING (bank_ticker, period, kind, period_type)
LEFT JOIN s3           USING (bank_ticker, period, kind, period_type)
LEFT JOIN ecl     e    USING (bank_ticker, period, kind, period_type)
LEFT JOIN ecl_brsa eb  USING (bank_ticker, period, kind, period_type)
LEFT JOIN s3_prov sp   USING (bank_ticker, period, kind, period_type)
"""


def _derived_stage_row(source: tuple) -> tuple:
    """Turn one _SQL_AGG source row into the persisted derived-stage row."""
    bt, p, k, pt, s1, s2, s3, e1, e2, e3 = source
    # `total` is the LOAN BOOK, and S1+S2 are what make it one. With both
    # absent, summing the surviving S3 would fabricate a 100% NPL row. Unknown
    # is therefore NULL, not zero. One missing S1/S2 is retained because 40
    # current rows legitimately have that partial shape.
    if s1 is None and s2 is None:
        tot_a = None
    else:
        amounts = [x for x in (s1, s2, s3) if x is not None]
        tot_a = sum(amounts) if amounts else None
    ecls = [x for x in (e1, e2, e3) if x is not None]
    tot_e = sum(ecls) if ecls else None
    cov1 = (e1 / s1) if (e1 is not None and s1 not in (None, 0)) else None
    cov2 = (e2 / s2) if (e2 is not None and s2 not in (None, 0)) else None
    cov3 = (e3 / s3) if (e3 is not None and s3 not in (None, 0)) else None
    return (bt, p, k, pt, s1, s2, s3, tot_a,
            e1, e2, e3, tot_e, cov1, cov2, cov3)


def build_stages(conn: sqlite3.Connection) -> int:
    """Rebuild bank_audit_stages from bank_audit_credit_quality, in process.

    Extracted from main() so tests can drive the REAL builder without
    shelling out: the suite carries a zero-subprocess guarantee (verified
    with a plugin wrapping subprocess.Popen and socket.connect), and a test
    that launches python breaks it and makes the suite depend on the
    interpreter path. Returns the row count written.
    """
    # Ensure the table exists (init_schema also creates it; this is a
    # no-op if so).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bank_audit_stages (
            bank_ticker      TEXT NOT NULL,
            period           TEXT NOT NULL,
            kind             TEXT NOT NULL,
            period_type      TEXT NOT NULL,
            stage1_amount    REAL,
            stage2_amount    REAL,
            stage3_amount    REAL,
            total_amount     REAL,
            stage1_ecl       REAL,
            stage2_ecl       REAL,
            stage3_ecl       REAL,
            total_ecl        REAL,
            stage1_coverage  REAL,
            stage2_coverage  REAL,
            stage3_coverage  REAL,
            extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bank_ticker, period, kind, period_type)
        )
    """)
    # NO delete-all here: the write below is incremental and owns row lifecycle
    # (it removes the keys the rebuild no longer produces). Wiping first would
    # re-stamp every surviving row's `extracted_at` — the whole cost this
    # rebuild is trying to avoid — and, worse, combined with an insert of only
    # the CHANGED rows it would empty the table.
    rows = [_derived_stage_row(r) for r in conn.execute(_SQL_AGG)]

    # Write only the rows that actually moved. `extracted_at` defaults to
    # CURRENT_TIMESTAMP and push_to_d1 windows on it, so re-inserting the whole
    # derived table re-stamps every row and ships it to D1 on every refresh —
    # 11,346 estimated billed rows in the 2026Q2 run for a table almost none of
    # which changed. Same rule as upsert_validation / upsert_pl_roles.
    _KEY = 4        # (bank_ticker, period, kind, period_type)
    stored = {r[:_KEY]: tuple(r[_KEY:]) for r in conn.execute(
        "SELECT bank_ticker, period, kind, period_type, "
        " stage1_amount, stage2_amount, stage3_amount, total_amount, "
        " stage1_ecl, stage2_ecl, stage3_ecl, total_ecl, "
        " stage1_coverage, stage2_coverage, stage3_coverage FROM bank_audit_stages")}
    changed = [r for r in rows if stored.get(r[:_KEY]) != tuple(r[_KEY:])]
    gone = set(stored) - {r[:_KEY] for r in rows}
    for key in gone:
        conn.execute(
            "DELETE FROM bank_audit_stages WHERE bank_ticker=? AND period=? "
            "AND kind=? AND period_type=?", key)
    conn.executemany(
        "INSERT OR REPLACE INTO bank_audit_stages "
        "(bank_ticker, period, kind, period_type, "
        " stage1_amount, stage2_amount, stage3_amount, total_amount, "
        " stage1_ecl, stage2_ecl, stage3_ecl, total_ecl, "
        " stage1_coverage, stage2_coverage, stage3_coverage) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        changed,
    )
    conn.commit()
    print(f"bank_audit_stages: {len(changed)} of {len(rows)} rows changed"
          f"{f', {len(gone)} removed' if gone else ''}")

    # Stats
    total = len(rows)
    complete = sum(1 for r in rows if all(r[i] is not None for i in (4, 5, 6, 8, 9, 10)))
    any_amt = sum(1 for r in rows if any(r[i] is not None for i in (4, 5, 6)))
    any_ecl = sum(1 for r in rows if any(r[i] is not None for i in (8, 9, 10)))
    print(f"bank_audit_stages: {total} rows")
    print(f"  with all 6 fields (S1/S2/S3 amounts + ECL):   {complete}")
    print(f"  with at least one amount field:               {any_amt}")
    print(f"  with at least one ECL field:                  {any_ecl}")
    return total


def rebuild_stages_partition(conn: sqlite3.Connection, bank: str, period: str,
                             kind: str) -> int:
    """Rebuild one derived stages partition inside the caller's transaction.

    Targeted credit-quality repairs use a SAVEPOINT and must validate the
    candidate *after* its dependent stages row has been rebuilt.  The full
    builder commits, which would release that savepoint; this scoped form writes
    only changed period rows and deliberately leaves commit/rollback ownership
    to the caller. Returns the number of factual stage rows changed or removed.
    """
    query = _SQL_AGG + (
        "\nWHERE b.bank_ticker=? AND b.period=? AND b.kind=?"
    )
    rows = [_derived_stage_row(r)
            for r in conn.execute(query, (bank, period, kind))]
    key_len = 4
    stored = {r[:key_len]: tuple(r[key_len:]) for r in conn.execute(
        "SELECT bank_ticker, period, kind, period_type, "
        " stage1_amount, stage2_amount, stage3_amount, total_amount, "
        " stage1_ecl, stage2_ecl, stage3_ecl, total_ecl, "
        " stage1_coverage, stage2_coverage, stage3_coverage "
        "FROM bank_audit_stages WHERE bank_ticker=? AND period=? AND kind=?",
        (bank, period, kind))}
    changed = [r for r in rows
               if stored.get(r[:key_len]) != tuple(r[key_len:])]
    current_keys = {r[:key_len] for r in rows}
    gone = set(stored) - current_keys
    for key in gone:
        conn.execute(
            "DELETE FROM bank_audit_stages WHERE bank_ticker=? AND period=? "
            "AND kind=? AND period_type=?", key)
    conn.executemany(
        "INSERT OR REPLACE INTO bank_audit_stages "
        "(bank_ticker, period, kind, period_type, "
        " stage1_amount, stage2_amount, stage3_amount, total_amount, "
        " stage1_ecl, stage2_ecl, stage3_ecl, total_ecl, "
        " stage1_coverage, stage2_coverage, stage3_coverage) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        changed,
    )
    return len(changed) + len(gone)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=str, default=str(DB),
                    help="SQLite DB holding bank_audit_credit_quality (default "
                         "data/bddk_data.db). The audit pipeline passes "
                         "data/bank_audit.db.")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: {db} not found", file=sys.stderr)
        sys.exit(1)
    with sqlite3.connect(str(db)) as conn:
        build_stages(conn)


if __name__ == "__main__":
    main()
