"""Walk all bank audit-report PDFs and load extracted statements into SQLite.

Idempotent: skips PDFs already loaded with success=1 in bank_audit_extractions.
Parallel: ProcessPoolExecutor with N workers.

Output: data/bddk_data.db (existing project DB) — adds bank_audit_* tables.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding='utf-8')

from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

DB = REPO / 'data' / 'bddk_data.db'
ROOT = REPO / 'data' / 'audit_reports'

# Standard filename pattern: <TICKER>_<YYYY>Q<n>_<kind>.pdf
STD_PAT = re.compile(r'^([A-Z]+)_(\d{4}Q\d)_(consolidated|unconsolidated)\.pdf$', re.I)


def discover_pdfs() -> list[tuple[str, str, str, Path]]:
    """Return list of (ticker, period, kind, path) for all extractable PDFs."""
    out: list[tuple[str, str, str, Path]] = []
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir():
            continue
        for pdf in sorted(folder.glob('*.pdf')):
            m = STD_PAT.match(pdf.name)
            if not m:
                continue
            tkr = m.group(1).upper()
            period = m.group(2).upper()
            kind = m.group(3).lower()
            out.append((tkr, period, kind, pdf))
    return out


def already_done(db_path: Path) -> set[tuple[str, str, str]]:
    if not db_path.exists():
        return set()
    with sqlite3.connect(str(db_path)) as conn:
        try:
            rows = conn.execute(
                'SELECT bank_ticker, period, kind FROM bank_audit_extractions WHERE success=1'
            ).fetchall()
            return set(rows)
        except sqlite3.OperationalError:
            return set()


def worker(args):
    ticker, period, kind, path_str = args
    t0 = time.time()
    try:
        rep = extract(path_str)
    except Exception as e:
        return (ticker, period, kind, False, 0, 0, 0, 0, time.time()-t0, f'extract:{type(e).__name__}:{str(e)[:80]}')
    secs = time.time() - t0
    counts = {
        'bs_assets': len(rep.bs_assets),
        'bs_liabilities': len(rep.bs_liabilities),
        'off_balance': len(rep.off_balance),
        'profit_loss': len(rep.profit_loss),
    }
    return (ticker, period, kind, True, counts['bs_assets'], counts['bs_liabilities'],
            counts['off_balance'], counts['profit_loss'], secs, '', rep, path_str)


def main():
    # Init schema
    with sqlite3.connect(str(DB)) as conn:
        init_schema(conn)

    pdfs = discover_pdfs()
    done = already_done(DB)
    todo = [(t, p, k, str(path)) for (t, p, k, path) in pdfs if (t, p, k) not in done]

    print(f'discovered {len(pdfs)} PDFs, {len(done)} already done, {len(todo)} to extract')
    if not todo:
        print('nothing to do')
        return

    import os
    workers = min(8, (os.cpu_count() or 8))
    print(f'using {workers} parallel workers\n')

    ok = fail = 0
    t_start = time.time()
    # We can't pickle pdfplumber objects across processes, but we CAN do
    # the extract in the worker and return the BankReport object (dataclass).
    # However opening a sqlite connection in each process is fine.
    futures_started = 0
    with sqlite3.connect(str(DB)) as conn, ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker, t) for t in todo]
        for fut in as_completed(futures):
            res = fut.result()
            if len(res) == 12:  # success path includes rep + path
                ticker, period, kind, succ, bsa, bsl, obs, pl, secs, err, rep, path_str = res
                # Write to DB in main process
                upsert_report(conn, ticker, period, kind, rep, path_str)
                tag = 'OK' if (bsa >= 20 and bsl >= 20 and pl >= 20) else 'WARN'
                print(f'  [{tag}] {ticker:<8} {period} {kind:<14} BSA={bsa} BSL={bsl} OBS={obs} PL={pl}  ({secs:.1f}s)', flush=True)
                ok += 1
            else:
                ticker, period, kind, succ, bsa, bsl, obs, pl, secs, err = res
                print(f'  [FAIL] {ticker:<8} {period} {kind:<14} {err}', flush=True)
                fail += 1

    elapsed = time.time() - t_start
    print(f'\ndone in {elapsed/60:.1f} min: ok={ok} fail={fail}')


if __name__ == '__main__':
    main()
