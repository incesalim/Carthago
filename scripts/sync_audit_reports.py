"""Cron-friendly audit-report sync: scrape new PDFs → R2 → extract → local DB.

After this runs, scripts/push_to_d1.py syncs the new bank_audit_* rows to D1.
Designed for the weekly GitHub Actions cron — no local PDF storage required;
PDFs live in R2, extraction happens on the runner's tmpfs.

Pipeline:
  1. Read data/banks/audit_report_urls.json for the canonical list of
     (ticker, period, kind, url) targets.
  2. For each target: check if PDF already exists in R2 under
     <ticker_lower>/<TICKER>_<period>_<kind>.pdf. If not, fetch + upload.
  3. List R2 → find PDFs not yet in bank_audit_extractions (success=1).
  4. For each pending PDF: download to a temp file, run extractor, upsert
     into local SQLite (data/bddk_data.db).
  5. Done. Caller is expected to run push_to_d1.py next to sync to D1.

Idempotent end-to-end. Safe to re-run any time.

Env vars required:
  R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY [R2_BUCKET]

Usage:
  python scripts/sync_audit_reports.py [--workers 16] [--no-scrape] [--no-extract]
  python scripts/sync_audit_reports.py --only-bank AKBNK   # one bank only
  python scripts/sync_audit_reports.py --only-bank AKBNK,GARAN
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.discovery import discover_targets  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.loader import upsert_report  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402


CONFIG = REPO_ROOT / "data" / "banks" / "audit_report_urls.json"
DB_PATH = REPO_ROOT / "data" / "bddk_data.db"

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
}
# Banks whose CDN blocks bare requests — supply Referer to bypass
REFERERS = {
    "TSKB":   "https://www.tskb.com.tr/en/investor-relations/financial-information",
    "QNBFB":  "https://www.qnb.com.tr/en/investor-relations/financial-information",
    "PASHA":  "https://www.pashabank.com.tr/tr/yatirimci-iliskileri",
    "AKTIF":  "https://www.aktifbank.com.tr/hakkimizda/finansal-bilgiler/denetim-raporlari",
    "VAKIFK": "https://www.vakifkatilim.com.tr/",
}

def _restrict_to_latest_period(rows: list, t_idx: int = 0, p_idx: int = 1) -> list:
    """Keep only the rows for each ticker's most-recent period.

    Periods are formatted YYYYQN, so a plain lexicographic max is chronological
    ('2026Q1' > '2025Q4'). Used by --latest-period so a per-bank trigger only
    touches the newest published quarter, not the bank's full history."""
    latest: dict[str, str] = {}
    for r in rows:
        t, p = r[t_idx].upper(), r[p_idx].upper()
        if t not in latest or p > latest[t]:
            latest[t] = p
    return [r for r in rows if r[p_idx].upper() == latest[r[t_idx].upper()]]


# ---------------------------------------------------------------------------
# Step 1+2: scrape new PDFs into R2
# ---------------------------------------------------------------------------
def fetch_pdf_bytes(url: str, ticker: str) -> tuple[bytes | None, str]:
    """Fetch a URL → return (bytes, note). Handles VAKIFK wrapper + ZIP."""
    headers = dict(UA)
    if ticker in REFERERS:
        headers["Referer"] = REFERERS[ticker]
    try:
        r = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
    except requests.RequestException as e:
        return None, f"err:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http:{r.status_code}"
    body = r.content
    # VAKIFK CMS bug: PDFs wrapped in 27-byte Java ObjectOutputStream header
    if body[:4] == b"\xac\xed\x00\x05" and b"%PDF" in body[:64]:
        body = body[body.find(b"%PDF"):]
    # ZIP-wrapped PDFs (some VAKBN solo files)
    if body[:4] == b"PK\x03\x04":
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile:
            return None, "bad-zip"
        pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
        if not pdf_names:
            return None, "no-pdf-in-zip"
        body = zf.read(pdf_names[0])
    if not body.startswith(b"%PDF"):
        return None, f"not-pdf:{body[:8]!r}"
    return body, "ok"


def scrape_to_r2(
    workers: int = 16, only: set[str] | None = None, latest_period: bool = False
) -> dict[str, int]:
    """Walk audit_report_urls.json; upload any new PDFs to R2.

    If ``only`` is given (a set of upper-case tickers), restrict the scrape to
    just those banks. If ``latest_period`` is set, restrict each bank to its
    newest quarter only (across all kinds)."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets: list[tuple[str, str, str, str]] = []  # ticker, period, kind, url
    seen: set[tuple[str, str, str]] = set()  # (ticker, period, kind) — dedup
    for ticker, b in cfg["banks"].items():
        if only and ticker.upper() not in only:
            continue
        # Static, hand-maintained URLs.
        for kind, period_map in b.get("urls", {}).items():
            normalised = "unconsolidated" if kind == "unconsolidated_zip" else kind
            for period, url in period_map.items():
                key = (ticker.upper(), period.upper(), normalised)
                if key in seen:
                    continue
                seen.add(key)
                targets.append((ticker, period, normalised, url))
        # Auto-discovered URLs. Augments the config so new quarters are picked
        # up without a hand-edit; on failure it returns [] and we keep the static
        # targets above. Never adds a duplicate (ticker, period, kind).
        for period, kind, url in discover_targets(ticker, b):
            key = (ticker.upper(), period.upper(), kind)
            if key in seen:
                continue
            seen.add(key)
            targets.append((ticker, period, kind, url))
    if latest_period:
        targets = _restrict_to_latest_period(targets)

    counts = {"new": 0, "skipped": 0, "failed": 0}

    def _one(t: tuple[str, str, str, str]) -> tuple[str, str, str, str, int]:
        ticker, period, kind, url = t
        key = r2_storage.make_key(ticker, period, kind)
        try:
            if r2_storage.exists(key):
                return ticker, period, kind, "skip", 0
        except Exception as e:
            return ticker, period, kind, f"err:r2head:{e}", 0
        body, note = fetch_pdf_bytes(url, ticker)
        if body is None:
            return ticker, period, kind, note, 0
        try:
            r2_storage.upload_bytes(body, key)
        except Exception as e:
            return ticker, period, kind, f"err:r2put:{e}", 0
        return ticker, period, kind, "ok", len(body)

    print(f"[scrape] {len(targets)} targets · {workers} parallel · uploading to R2")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed(ex.submit(_one, t) for t in targets):
            ticker, period, kind, note, size = fut.result()
            if note == "skip":
                counts["skipped"] += 1
            elif note == "ok":
                counts["new"] += 1
                if counts["new"] % 10 == 1 or counts["new"] <= 10:
                    print(f"  [NEW]  {ticker:<8} {period} {kind:<14} {size/1024:.1f} KB")
            else:
                counts["failed"] += 1
                print(f"  [FAIL] {ticker:<8} {period} {kind:<14} {note}", flush=True)
    print(f"[scrape] new={counts['new']} skipped={counts['skipped']} failed={counts['failed']}")
    return counts


# ---------------------------------------------------------------------------
# Step 3+4: extract pending PDFs from R2 → local DB
# ---------------------------------------------------------------------------
def list_r2_pdfs() -> list[tuple[str, str, str, str]]:
    """Thin alias preserved for callers that imported from this module."""
    return r2_storage.list_audit_pdfs()


def already_extracted(db_path: Path) -> set[tuple[str, str, str]]:
    if not db_path.exists():
        return set()
    with sqlite3.connect(str(db_path)) as conn:
        try:
            rows = conn.execute(
                "SELECT bank_ticker, period, kind FROM bank_audit_extractions WHERE success=1"
            ).fetchall()
            return set(rows)
        except sqlite3.OperationalError:
            return set()


def _worker_extract(args):
    """Worker process: pull PDF from R2, run extractor (BS/PL + credit-quality
    in one pass), return the report. Pickleable so it can cross the
    ProcessPool boundary."""
    ticker, period, kind, key, tmp_dir = args
    t0 = time.time()
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    try:
        r2_storage.download_to(key, dest)
    except Exception as e:
        return (ticker, period, kind, key, False, 0, 0, 0, 0, 0,
                time.time() - t0, f"r2get:{type(e).__name__}:{str(e)[:80]}",
                None, str(dest))
    try:
        rep = extract(str(dest))
    except Exception as e:
        return (ticker, period, kind, key, False, 0, 0, 0, 0, 0,
                time.time() - t0, f"extract:{type(e).__name__}:{str(e)[:80]}",
                None, str(dest))
    return (
        ticker, period, kind, key, True,
        len(rep.bs_assets), len(rep.bs_liabilities), len(rep.off_balance), len(rep.profit_loss),
        len(rep.credit_quality),
        time.time() - t0, "", rep, str(dest),
    )


def extract_from_r2(
    workers: int, db_path: Path = DB_PATH, only: set[str] | None = None,
    latest_period: bool = False, periods: set[str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        init_schema(conn)

    pdfs = list_r2_pdfs()
    if only:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if t.upper() in only]
    if periods:
        want = {p.upper() for p in periods}
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if p.upper() in want]
    if latest_period:
        pdfs = _restrict_to_latest_period(pdfs)
    done = already_extracted(db_path)
    if force:
        # Re-extract even already-done partitions (upsert_report replaces them).
        # Targeted re-runs from the admin coverage matrix rely on this.
        todo = list(pdfs)
        print(f"[extract] {len(pdfs)} in R2 · force re-extract (ignoring {len(done)} already done)")
    else:
        todo = [(t, p, k, key) for (t, p, k, key) in pdfs if (t, p, k) not in done]
        print(f"[extract] {len(pdfs)} in R2 · {len(done)} already done · {len(todo)} to extract")
    if not todo:
        return {"ok": 0, "fail": 0}

    counts = {"ok": 0, "fail": 0}
    with tempfile.TemporaryDirectory(prefix="bddk_pdfs_") as tmp_dir:
        work = [(t, p, k, key, tmp_dir) for (t, p, k, key) in todo]
        with sqlite3.connect(str(db_path)) as conn, \
             ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_worker_extract, w) for w in work]
            for fut in as_completed(futures):
                res = fut.result()
                (ticker, period, kind, key, succ,
                 bsa, bsl, obs, pl, cq,
                 secs, err, rep, path_str) = res
                if not succ:
                    counts["fail"] += 1
                    print(f"  [FAIL] {ticker:<8} {period} {kind:<14} {err}", flush=True)
                    continue
                upsert_report(conn, ticker, period, kind, rep, key)
                tag = "OK" if (bsa >= 20 and bsl >= 20 and pl >= 20) else "WARN"
                counts["ok"] += 1
                print(
                    f"  [{tag:<4}] {ticker:<8} {period} {kind:<14} "
                    f"BSA={bsa} BSL={bsl} OBS={obs} PL={pl} CQ={cq}  ({secs:.1f}s)",
                    flush=True,
                )
                # Delete the temp file as we go so disk doesn't fill up
                try:
                    Path(path_str).unlink()
                except OSError:
                    pass

    print(f"[extract] ok={counts['ok']} fail={counts['fail']}")
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16, help="parallel HTTP / extraction workers")
    ap.add_argument("--no-scrape", action="store_true", help="skip the scrape step")
    ap.add_argument("--no-extract", action="store_true", help="skip the extract step")
    ap.add_argument("--only-bank", type=str, default="",
                    help="restrict scrape + extract to one or more tickers "
                         "(comma-separated, e.g. AKBNK or AKBNK,GARAN). "
                         "Default: all banks in audit_report_urls.json.")
    ap.add_argument("--latest-period", action="store_true",
                    help="restrict to each bank's newest quarter only (across "
                         "all kinds). Pair with --only-bank to grab just the "
                         "report a bank has freshly published.")
    ap.add_argument("--periods", type=str, default="",
                    help="restrict extraction to one or more quarters "
                         "(comma-separated 'YYYYQn', e.g. 2024Q4). Pair with "
                         "--only-bank + --force for a targeted re-extraction.")
    ap.add_argument("--force", action="store_true",
                    help="re-extract even partitions already in the DB (upsert "
                         "replaces them). Without this, done partitions are skipped.")
    ap.add_argument("--new-count-file", type=str, default="",
                    help="write the count of newly-scraped PDFs to this file "
                         "(so acquire-audit.yml can notify when new reports land).")
    ap.add_argument("--db", type=str, default=str(DB_PATH),
                    help="SQLite DB to upsert extracted rows into (default "
                         "data/bddk_data.db). The standalone audit pipeline "
                         "passes data/bank_audit.db so audit data lives in its "
                         "own snapshot, decoupled from the BDDK-bulletin DB.")
    ap.add_argument("--fail-threshold", type=float, default=0.25,
                    help="Exit non-zero if the scrape/extract failure ratio "
                         "exceeds this on a non-trivial batch (>=4 items). "
                         "Catches systemic breakage (R2 down, extractor broken) "
                         "while ignoring the ~2%% known-partial baseline.")
    args = ap.parse_args()

    db_path = Path(args.db)

    only: set[str] | None = None
    if args.only_bank.strip():
        only = {t.strip().upper() for t in args.only_bank.split(",") if t.strip()}
        known = {t.upper() for t in json.loads(CONFIG.read_text(encoding="utf-8"))["banks"]}
        unknown = only - known
        if unknown:
            print(f"[warn] unknown ticker(s) not in audit_report_urls.json: "
                  f"{', '.join(sorted(unknown))}", file=sys.stderr)
        print(f"[filter] restricting to bank(s): {', '.join(sorted(only))}")
    if args.latest_period:
        print("[filter] restricting to each bank's latest period only")

    periods: set[str] | None = None
    if args.periods.strip():
        periods = {p.strip().upper() for p in args.periods.split(",") if p.strip()}
        bad = sorted(p for p in periods
                     if not (len(p) == 6 and p[:4].isdigit() and p[4] == "Q" and p[5] in "1234"))
        if bad:
            sys.exit(f"[error] bad --periods value(s): {', '.join(bad)} (want YYYYQn, e.g. 2024Q4)")
        print(f"[filter] restricting to period(s): {', '.join(sorted(periods))}")
    if args.force:
        print("[filter] force re-extraction (already-done partitions included)")

    t0 = time.time()
    scrape_counts: dict[str, int] = {}
    extract_counts: dict[str, int] = {}
    if not args.no_scrape:
        scrape_counts = scrape_to_r2(
            workers=args.workers, only=only, latest_period=args.latest_period)
    if args.new_count_file:
        Path(args.new_count_file).write_text(str(scrape_counts.get("new", 0)), encoding="utf-8")
    if not args.no_extract:
        # Extraction is CPU-bound (pdfplumber/fitz) — cap at min(workers, cpu_count)
        import os
        cpu_workers = min(args.workers, (os.cpu_count() or 4))
        extract_counts = extract_from_r2(
            workers=cpu_workers, db_path=db_path, only=only,
            latest_period=args.latest_period, periods=periods, force=args.force)
    print(f"\ntotal {time.time() - t0:.1f}s")

    # Systemic-failure guard: make the run exit non-zero (→ CI failure email +
    # webhook alert) when a non-trivial batch mostly failed. Tiny batches and the
    # known-partial baseline don't trip it.
    problems = []
    sc_fail = scrape_counts.get("failed", 0)
    sc_total = sc_fail + scrape_counts.get("new", 0)
    if sc_total >= 4 and sc_fail / sc_total > args.fail_threshold:
        problems.append(f"scrape {sc_fail}/{sc_total} failed")
    ex_fail = extract_counts.get("fail", 0)
    ex_total = ex_fail + extract_counts.get("ok", 0)
    if ex_total >= 4 and ex_fail / ex_total > args.fail_threshold:
        problems.append(f"extract {ex_fail}/{ex_total} failed")
    if problems:
        print(f"SYSTEMIC FAILURE: {'; '.join(problems)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
