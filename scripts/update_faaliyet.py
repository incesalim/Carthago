"""Acquire + extract bank Faaliyet Raporları (annual reports) → franchise stats.

Reads ``data/banks/faaliyet_report_urls.json`` for the curated per-bank,
per-fiscal-year report URLs, fetches each PDF into R2 (cached — skipped if
already present), runs the deterministic franchise extractor
(``src/faaliyet/extractor.py``) and upserts ``faaliyet_franchise`` +
``faaliyet_extractions`` in ``data/bddk_data.db``. ``scripts/push_to_d1.py``
then syncs the rows to Cloudflare D1.

This lane never touches the bank_audit_* tables (BS/P&L frozen); it only
cross-checks branch/employee counts against ``bank_audit_profile`` read-only.

Modes:
- **Default**: process every configured (bank, year) not yet ``success=1`` —
  picks up newly-curated URLs incrementally.
- **Backfill** (``--backfill``): process every configured target, resumable —
  completed (bank, year) pairs are recorded in ``faaliyet_fetch_log`` and
  skipped on re-run. With ``--push-every K`` the rows are pushed to D1 every K
  banks (one end-of-run push of the whole fleet would exceed wrangler's file
  size).

Env (R2 acquisition + the D1 push): R2_ACCOUNT_ID R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY [R2_FAALIYET_BUCKET] CLOUDFLARE_API_TOKEN

Usage:
  python scripts/update_faaliyet.py                       # incremental
  python scripts/update_faaliyet.py --backfill --push-every 5
  python scripts/update_faaliyet.py --only-bank AKBNK --year 2025 --force
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.faaliyet import r2_storage                       # noqa: E402
from src.faaliyet.client import fetch_pdf_bytes           # noqa: E402
from src.faaliyet.extractor import extract                # noqa: E402
from src.faaliyet.loader import fetch_done, mark_fetch, upsert_report  # noqa: E402
from src.faaliyet.schema import init_schema               # noqa: E402

import json  # noqa: E402

CONFIG = REPO_ROOT / "data" / "banks" / "faaliyet_report_urls.json"
DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
FAALIYET_TABLES = "faaliyet_franchise,faaliyet_extractions"


def iter_targets(only_bank: set[str] | None, only_year: int | None):
    """Yield (ticker, year, lang, url) from the curated config. Prefers the
    Turkish report when both languages exist (franchise anchors are TR-first)."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for ticker, b in cfg["banks"].items():
        if only_bank and ticker.upper() not in only_bank:
            continue
        for year_str, langs in sorted((b.get("reports") or {}).items()):
            try:
                year = int(year_str)
            except ValueError:
                continue
            if only_year and year != only_year:
                continue
            lang = "tr" if langs.get("tr") else ("en" if langs.get("en") else None)
            if lang is None:
                continue
            yield ticker.upper(), year, lang, langs[lang]


def already_done(conn: sqlite3.Connection, ticker: str, year: int) -> bool:
    row = conn.execute(
        "SELECT success FROM faaliyet_extractions WHERE bank_ticker = ? AND fiscal_year = ?",
        (ticker, year),
    ).fetchone()
    return bool(row) and row[0] == 1


def process_one(conn: sqlite3.Connection, ticker: str, year: int, lang: str,
                url: str, force: bool) -> tuple[str, str]:
    """Acquire (R2-cached) → extract → upsert one (bank, year). Returns (status, note)."""
    key = r2_storage.make_key(ticker, year, lang)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        if not force and r2_storage.exists(key):
            r2_storage.download_to(key, tmp)
        else:
            body, note = fetch_pdf_bytes(url, ticker)
            if body is None:
                mark_fetch(conn, ticker, year, "no_pdf")
                return "no_pdf", note
            r2_storage.upload_bytes(body, key)
            tmp.write_bytes(body)
        rep = extract(tmp, year)
        upsert_report(conn, ticker, year, rep, source_url=url, r2_key=key)
        status = "ocr" if rep.is_ocr else "done"
        mark_fetch(conn, ticker, year, status)
        n = sum(1 for s in rep.stats if s.period_type == "current")
        return status, f"{n} stats [{rep.report_lang}]"
    finally:
        tmp.unlink(missing_ok=True)


def push_tables(hours: int) -> None:
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "push_to_d1.py"),
           "--hours", str(hours), f"--only-tables={FAALIYET_TABLES}"]
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    ap.add_argument("--backfill", action="store_true",
                    help="Process every configured target, resumable via faaliyet_fetch_log")
    ap.add_argument("--only-bank", default=None,
                    help="Restrict to these tickers (comma-separated)")
    ap.add_argument("--year", type=int, default=None, help="Restrict to one fiscal year")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch + re-extract even if already done")
    ap.add_argument("--push-every", type=int, default=0,
                    help="Push faaliyet_* to D1 every K processed banks (0 = never)")
    args = ap.parse_args()

    only_bank = ({t.strip().upper() for t in args.only_bank.split(",") if t.strip()}
                 if args.only_bank else None)
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    counts = {"done": 0, "ocr": 0, "no_pdf": 0, "error": 0, "skip": 0}
    with sqlite3.connect(str(db)) as conn:
        init_schema(conn)
        targets = list(iter_targets(only_bank, args.year))
        for ticker, year, lang, url in targets:
            gate = fetch_done if args.backfill else already_done
            if not args.force and gate(conn, ticker, year):
                counts["skip"] += 1
                print(f"  {ticker} {year}: already done — skipped", flush=True)
                continue
            try:
                status, note = process_one(conn, ticker, year, lang, url, args.force)
            except Exception as e:  # noqa: BLE001 - log + continue the fleet
                mark_fetch(conn, ticker, year, "error")
                status, note = "error", f"{type(e).__name__}: {e}"
            counts[status] = counts.get(status, 0) + 1
            processed += 1
            print(f"  {ticker} {year}: {status} ({note})", flush=True)
            if args.push_every and processed % args.push_every == 0:
                push_tables(hours=6)

        total = conn.execute("SELECT COUNT(*) FROM faaliyet_franchise").fetchone()[0]

    if args.push_every and processed:
        push_tables(hours=6)

    print(f"\nDone. {processed} processed "
          f"(done={counts['done']} ocr={counts['ocr']} no_pdf={counts['no_pdf']} "
          f"error={counts['error']} skip={counts['skip']}); "
          f"faaliyet_franchise holds {total} rows.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
