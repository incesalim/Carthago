"""Backfill the narrative-prose lane over the whole R2 fleet, into a LOCAL db.

Writes nothing to D1. The D1 push is deliberately a separate, later step (the
write freeze stands), so this lands in its own SQLite file rather than in the
lane snapshot: `apply_overrides` and the refresh workflows OVERWRITE
`data/bank_audit.db` from the R2 snapshot, and prose rows written there would be
silently destroyed by the next pull. A dedicated file is also trivially
mergeable when the freeze lifts:

    ATTACH 'data/bank_audit_prose.db' AS p;
    INSERT OR REPLACE INTO bank_audit_prose SELECT * FROM p.bank_audit_prose;

Idempotent and resumable: a partition already carrying rows is skipped unless
--force, so an interrupted run continues where it stopped.

Downloads and extraction run in a thread pool; every SQLite write happens on the
main thread, because a connection is not shared across threads.

Usage:
  python scripts/backfill_prose.py                      # whole fleet from R2
  python scripts/backfill_prose.py --only-bank AKBNK,GARAN
  python scripts/backfill_prose.py --local-dir data/eye # no network
  python scripts/backfill_prose.py --limit 20 --force

Env (R2 source only): R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
"""
from __future__ import annotations

import argparse
import queue
import re
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.prose import extract_prose, upsert  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.validator import check_prose, upsert_validation  # noqa: E402

DEFAULT_DB = REPO_ROOT / "data" / "bank_audit_prose.db"
LOCAL_PAT = re.compile(r"^([A-Z0-9]+)_(\d{4}Q\d)_(consolidated|unconsolidated)$", re.I)


def done_partitions(conn: sqlite3.Connection) -> set[tuple[str, str, str]]:
    return {(b, p, k) for b, p, k in conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_prose")}


def _validation_rows(rep) -> list[dict]:
    """The shape check_prose reads — mirrors what the DB would hand it."""
    return [{"section": r.section, "section_role": r.section_role,
             "page_start": r.page_start} for r in rep.rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--local-dir", help="read PDFs from here instead of R2")
    ap.add_argument("--only-bank", help="comma-separated tickers")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true",
                    help="re-extract partitions that already have rows")
    args = ap.parse_args()

    if args.local_dir:
        targets = []
        for f in sorted(Path(args.local_dir).glob("*.pdf")):
            m = LOCAL_PAT.match(f.stem)
            if m:
                targets.append((m.group(1).upper(), m.group(2).upper(),
                                m.group(3).lower(), str(f)))
    else:
        targets = r2_storage.list_audit_pdfs()

    if args.only_bank:
        want = {t.strip().upper() for t in args.only_bank.split(",")}
        targets = [t for t in targets if t[0] in want]
    targets.sort()

    conn = sqlite3.connect(args.db)
    init_schema(conn)
    already = set() if args.force else done_partitions(conn)
    todo = [t for t in targets if (t[0], t[1], t[2]) not in already]
    if args.limit:
        todo = todo[:args.limit]

    print(f"{len(targets)} filings in scope | {len(already)} already done | "
          f"{len(todo)} to process -> {args.db}")
    if not todo:
        return 0

    results: queue.Queue = queue.Queue()

    def work(target) -> None:
        ticker, period, kind, ref = target
        try:
            if args.local_dir:
                rep = extract_prose(ref, period)
            else:
                with tempfile.TemporaryDirectory() as td:
                    local = Path(td) / "f.pdf"
                    r2_storage.download_to(ref, local)
                    rep = extract_prose(str(local), period)
            results.put((target, rep, None))
        except Exception as e:                       # one bad filing must not stop the run
            results.put((target, None, str(e)[:160]))

    t0 = time.time()
    ok = failed = empty = 0
    n_rows = 0
    pool = ThreadPoolExecutor(max_workers=args.workers)
    threading.Thread(target=lambda: [pool.submit(work, t) for t in todo],
                     daemon=True).start()

    for i in range(len(todo)):
        (ticker, period, kind, _ref), rep, err = results.get()
        if err is not None:
            failed += 1
            print(f"  FAIL {ticker} {period} {kind}: {err}")
            continue
        n = upsert(conn, ticker, period, kind, rep)
        res = check_prose(_validation_rows(rep))
        upsert_validation(conn, ticker, period, kind, {"prose": res})
        conn.commit()
        n_rows += n
        if n == 0:
            empty += 1
        elif res.failed == 0:
            ok += 1
        if (i + 1) % 25 == 0:
            el = time.time() - t0
            print(f"  {i + 1}/{len(todo)}  {el:.0f}s  "
                  f"({el / (i + 1):.1f}s/filing)  {n_rows:,} rows", flush=True)
    pool.shutdown(wait=True)

    total = conn.execute("SELECT COUNT(*) FROM bank_audit_prose").fetchone()[0]
    parts = len(done_partitions(conn))
    clean = conn.execute(
        "SELECT COUNT(*) FROM bank_audit_validation "
        "WHERE statement='prose' AND checks_failed=0 AND checks_passed>0").fetchone()[0]
    print(f"\n{len(todo)} processed in {time.time() - t0:.0f}s — "
          f"{ok} clean, {len(todo) - ok - failed - empty} with validation failures, "
          f"{empty} empty, {failed} errored")
    print(f"db now holds {total:,} prose rows across {parts} partitions; "
          f"{clean} partitions pass check_prose")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
