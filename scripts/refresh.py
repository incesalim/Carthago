"""One-shot data refresh orchestrator.

Steps (each can be skipped individually):
  1. Incremental monthly update (only new months BDDK has published).
  2. Incremental weekly update (latest 13-week window).
  3. EVDS refresh (TCMB macro / rate series).
  4. TBB quarterly digital-banking refresh (non-critical).
  5. KAP ownership-structure refresh (non-critical).
  6. TEFAS fund-market refresh (non-critical).
  7. VACUUM + gzip to data/bddk_data.db.gz.
  8. Optional: git add / commit / push the new snapshot.

After this runs, scripts/push_to_d1.py syncs the changed rows up to
Cloudflare D1 — which the production dashboard reads from.

Example:
    python scripts/refresh.py                                    # full refresh
    python scripts/refresh.py --skip-monthly --skip-weekly       # EVDS only
    python scripts/refresh.py --push                             # also commit + push
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "bddk_data.db"
DB_GZ = ROOT / "data" / "bddk_data.db.gz"


def _run_step(name: str, cmd: list[str], critical: bool = True) -> None:
    print(f"\n{'='*8} {name} {'='*8}", flush=True)
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        print(f"{name} exited with code {res.returncode}", flush=True)
        if critical:
            sys.exit(res.returncode)
        print(f"(non-critical) continuing despite {name} failure", flush=True)


def vacuum() -> None:
    print("\n======== VACUUM DB ========", flush=True)
    before = DB_PATH.stat().st_size
    c = sqlite3.connect(DB_PATH)
    c.execute("VACUUM")
    c.close()
    after = DB_PATH.stat().st_size
    print(f"{before/1e6:.1f} MB → {after/1e6:.1f} MB", flush=True)


def gzip_db() -> None:
    print("\n======== gzip snapshot ========", flush=True)
    with open(DB_PATH, "rb") as src, gzip.open(DB_GZ, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    print(f"{DB_GZ.name}: {DB_GZ.stat().st_size/1e6:.1f} MB", flush=True)


def git_push(date_label: str) -> None:
    print("\n======== git push ========", flush=True)
    msg = f"Refresh data snapshot ({date_label})"
    subprocess.run(["git", "add", str(DB_GZ)], cwd=str(ROOT), check=True)
    res = subprocess.run(["git", "commit", "-m", msg], cwd=str(ROOT))
    if res.returncode != 0:
        print("Nothing to commit (snapshot unchanged).", flush=True)
        return
    subprocess.run(["git", "push"], cwd=str(ROOT), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true",
                        help="git add/commit/push the new bddk_data.db.gz snapshot")
    parser.add_argument("--skip-monthly", action="store_true")
    parser.add_argument("--skip-weekly", action="store_true")
    parser.add_argument("--skip-evds", action="store_true")
    parser.add_argument("--skip-tbb", action="store_true",
                        help="skip the TBB quarterly digital-banking refresh")
    parser.add_argument("--skip-kap", action="store_true",
                        help="skip the KAP ownership-structure refresh")
    parser.add_argument("--skip-tefas", action="store_true",
                        help="skip the TEFAS fund-market refresh")
    args = parser.parse_args()

    start = datetime.now()
    print(f"Refresh starting at {start:%Y-%m-%d %H:%M}", flush=True)

    if not args.skip_monthly:
        _run_step("Monthly update",
                   [sys.executable, "scripts/update_monthly.py"])
    if not args.skip_weekly:
        _run_step("Weekly update",
                   [sys.executable, "scripts/update_weekly.py"])
    if not args.skip_evds:
        _run_step("EVDS update",
                   [sys.executable, "-m", "src.scrapers.evds_scraper"])
    if not args.skip_tbb:
        # Quarterly source; latest 2 reports refresh the newest quarter and pick
        # up TBB's revisions. Non-critical: a TBB outage must not abort the core
        # BDDK refresh — the next cron retries.
        _run_step("TBB digital-banking update",
                   [sys.executable, "scripts/update_tbb_digital.py"],
                   critical=False)
    if not args.skip_kap:
        # Ownership structure from KAP Genel Bilgi Formu pages. Non-critical:
        # a KAP outage must not abort the core BDDK refresh; per-bank parse
        # failures keep that bank's previous rows in place.
        _run_step("KAP ownership update",
                   [sys.executable, "scripts/update_kap_ownership.py"],
                   critical=False)
    if not args.skip_tefas:
        # Fund-market aggregates from tefas.gov.tr (trailing 7-day window,
        # rate-limited to ~5.5 req/min ≈ 2.5 min). Non-critical: a TEFAS
        # outage must not abort the core BDDK refresh — the trailing window
        # self-heals on the next cron.
        _run_step("TEFAS funds update",
                   [sys.executable, "scripts/update_tefas.py"],
                   critical=False)

    vacuum()
    gzip_db()

    if args.push:
        git_push(start.strftime("%Y-%m-%d"))

    elapsed = (datetime.now() - start).total_seconds() / 60
    print(f"\nRefresh complete in {elapsed:.1f}m.", flush=True)


if __name__ == "__main__":
    main()
