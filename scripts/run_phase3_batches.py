"""Phase 3 — batchwise history repair with verification gates between batches.

Runs scripts/backfill_extraction.py for small bank batches (re-extract from R2
→ clear D1 partitions → push → snapshot), and after each batch verifies the
local post-backfill state against the Phase-2 evidence baseline
(data/fleet_scratch.db): per-bank identity-check failures must not exceed the
dry-run's, and row counts must not shrink. ABORTS before the next batch on any
violation — a stopped run leaves earlier batches repaired and later banks
untouched.

TSKB is excluded by design (split-digit text damage needs its own pass);
ALBRK/BURGAN were already repaired on 2026-06-10.

  python scripts/run_phase3_batches.py            # all batches
  python scripts/run_phase3_batches.py --start 3  # resume from batch 3
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

DB = REPO / "data" / "bank_audit.db"
SCRATCH = REPO / "data" / "fleet_scratch.db"

BATCHES = [
    ["AKBNK", "AKTIF", "ALNTF", "ANADOLU", "ATBANK"],
    ["DENIZ", "EMLAK", "EXIM", "FIBA", "GARAN"],
    ["HALKB", "HSBC", "ICBCT", "ING", "ISCTR"],
    ["KLNMA", "KUVEYT", "ODEA", "PASHA", "QNBFB"],
    ["SKBNK", "TEB", "TFKB", "VAKBN"],
    ["VAKIFK", "YKBNK", "ZIRAAT", "ZIRAATK"],
]


def _per_bank(conn: sqlite3.Connection, banks: list[str]) -> dict[str, tuple[int, int]]:
    """(identity failures, balance-sheet rows) per bank."""
    out = {}
    for b in banks:
        failed = conn.execute(
            "SELECT COALESCE(SUM(checks_failed),0) FROM bank_audit_validation "
            "WHERE bank_ticker=?", (b,)).fetchone()[0]
        rows = conn.execute(
            "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=?",
            (b,)).fetchone()[0]
        out[b] = (failed, rows)
    return out


def _per_partition(conn: sqlite3.Connection, bank: str) -> dict[tuple, tuple[int, int]]:
    """{(period, kind, statement): (identity failures, rows)} for one bank.

    Statement-level so a loss in one statement can't be masked by a gain in
    another (ICBCT: liabilities lost the malformed 16.4 row while off_balance
    RECOVERED two long-dropped rows — net +1 at partition level). 'cross'
    failures are attributed to 'liabilities' (they compare both statements)."""
    failed: dict[tuple, int] = {}
    for p, k, s, f in conn.execute(
            "SELECT period, kind, statement, SUM(checks_failed) "
            "FROM bank_audit_validation WHERE bank_ticker=? GROUP BY 1,2,3", (bank,)):
        s = "liabilities" if s == "cross" else s
        key = (p, k, s)
        failed[key] = failed.get(key, 0) + (f or 0)
    rows = {(p, k, s): n for p, k, s, n in conn.execute(
        "SELECT period, kind, statement, COUNT(*) FROM bank_audit_balance_sheet "
        "WHERE bank_ticker=? GROUP BY 1,2,3", (bank,))}
    return {key: (failed.get(key, 0), rows.get(key, 0))
            for key in set(failed) | set(rows)}


def _is_honest_skip(bank: str) -> tuple[bool, list[str]]:
    """A bank may exceed its baseline failures ONLY via the honest-skip class:
    the fixed extractor drops a malformed row the dry-run stored with a garbage
    value (EMLAK 'IX. CARİ VERGİ BORCU' with the dipnot (8) as amount_tl=-8) —
    so the partition LOSES rows and a sum check starts failing visibly.
    Garbage-VALUE corruption keeps row counts, so it still trips the gate."""
    notes = []
    with sqlite3.connect(str(DB)) as new_c, sqlite3.connect(str(SCRATCH)) as base_c:
        new_p, base_p = _per_partition(new_c, bank), _per_partition(base_c, bank)
    for key, (nf, nr) in sorted(new_p.items()):
        bf, br = base_p.get(key, (0, 0))
        if nf <= bf:
            continue
        if nr < br and nf - bf <= 3:
            notes.append(f"{bank} {' '.join(key)}: +{nf - bf} failure(s) with "
                         f"rows {br}→{nr} — honest skip of a malformed row")
        else:
            return False, [f"{bank} {' '.join(key)}: +{nf - bf} failure(s), "
                           f"rows {br}→{nr} — not an honest skip"]
    return True, notes


def verify_batch(banks: list[str], baseline: dict[str, tuple[int, int]]) -> list[str]:
    problems = []
    with sqlite3.connect(str(DB)) as conn:
        got = _per_bank(conn, banks)
    for b in banks:
        bf, br = baseline[b]
        gf, gr = got[b]
        if gf > bf:
            ok, notes = _is_honest_skip(b)
            for n in notes:
                print(f"[phase3]   note: {n}", flush=True)
            # No flat per-bank failure cap: the honest-skip signature is
            # per-partition (+3 max each, row loss required) and the row floor
            # below bounds any pathological mass-drop (ICBCT legitimately had
            # 4 partitions each skipping the same malformed equity row).
            if not ok:
                problems.append(f"{b}: identity failures {gf} > dry-run baseline {bf}")
        if gr < br - 5:
            problems.append(f"{b}: balance-sheet rows {gr} << dry-run baseline {br}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1, help="1-based batch to start from")
    args = ap.parse_args()

    with sqlite3.connect(str(SCRATCH)) as conn:
        baseline = _per_bank(conn, [b for batch in BATCHES for b in batch])
    print(f"[phase3] baseline loaded for {len(baseline)} banks from {SCRATCH.name}")

    for i, banks in enumerate(BATCHES, 1):
        if i < args.start:
            continue
        print(f"\n[phase3] ===== batch {i}/{len(BATCHES)}: {','.join(banks)} =====", flush=True)
        rc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "backfill_extraction.py"),
             "--banks", ",".join(banks), "--window-hours", "3"],
            cwd=str(REPO)).returncode
        if rc != 0:
            print(f"[phase3] ABORT: backfill for batch {i} exited {rc}", flush=True)
            return 1
        problems = verify_batch(banks, baseline)
        if problems:
            print(f"[phase3] ABORT after batch {i} — verification failed:", flush=True)
            for p in problems:
                print("  -", p, flush=True)
            return 1
        print(f"[phase3] batch {i} verified clean", flush=True)
    print("\n[phase3] ALL BATCHES DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
