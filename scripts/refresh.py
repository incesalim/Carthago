"""One-shot data refresh orchestrator.

Steps (each can be skipped individually):
  1. Incremental monthly update (only new months BDDK has published).
  2. Incremental weekly update (latest 13-week window).
  3. EVDS refresh (TCMB macro / rate series).
  4. TBB quarterly digital-banking refresh (non-critical).
  5. TKBB participation-bank digital refresh (non-critical).
  6. KAP ownership-structure refresh (non-critical).
  7. TEFAS fund-market refresh (non-critical).
  8. Faaliyet-raporları franchise refresh — incremental, non-critical.
  9. VACUUM + gzip to data/bddk_data.db.gz.
 10. Optional: git add / commit / push the new snapshot.

The BIST equity step (Yahoo) was removed 2026-08-01 — Yahoo's terms forbid
redistribution and prohibit automated access, so both the fetch and the serve
had to go. See docs/knowledge/data-source-terms-audit-2026-07-25.md.

After this runs, scripts/push_to_d1.py syncs the changed rows up to
Cloudflare D1 — which the production dashboard reads from.

Example:
    python scripts/refresh.py                                    # full refresh
    python -m src.scrapers.evds_scraper --frequencies all        # EVDS only
    python scripts/refresh.py --push                             # also commit + push
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "bddk_data.db"
DB_GZ = ROOT / "data" / "bddk_data.db.gz"


def file_digest(path: Path) -> str | None:
    """Hash the SQLite file before packaging can alter its bytes.

    A loader that commits no mutation leaves the database file unchanged.
    Workflows use this signal to avoid D1 and R2 writes on quiet source days.
    """
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    parser.add_argument("--skip-nonbank", action="store_true",
                        help="skip the BDDK non-bank sector (leasing/factoring/"
                             "financing/VYŞ) refresh")
    parser.add_argument("--skip-evds", action="store_true")
    parser.add_argument(
        "--evds-frequencies",
        default="all",
        help=("comma-separated EVDS frequency groups to poll: daily, weekly, "
              "monthly, quarterly, or all (default: all)"),
    )
    parser.add_argument("--skip-tbb", action="store_true",
                        help="skip the TBB quarterly digital-banking refresh")
    parser.add_argument("--skip-tkbb", action="store_true",
                        help="skip the TKBB participation-bank digital refresh")
    parser.add_argument("--skip-kap", action="store_true",
                        help="skip the KAP ownership-structure refresh")
    parser.add_argument("--skip-tefas", action="store_true",
                        help="skip the TEFAS fund-market refresh")
    parser.add_argument("--skip-faaliyet", action="store_true",
                        help="skip the Faaliyet-raporları franchise refresh")
    parser.add_argument("--skip-tuik", action="store_true",
                        help="skip the TÜİK national-accounts/PPI-detail refresh")
    parser.add_argument(
        "--change-file",
        default="",
        help=("write 'true' when SQLite changed, otherwise 'false'; workflows "
              "use this to make quiet runs read-only"),
    )
    parser.add_argument(
        "--defer-packaging",
        action="store_true",
        help=("do not VACUUM/gzip a changed DB here; workflows use this so they "
              "package after the D1 writer records successful push state"),
    )
    args = parser.parse_args()

    start = datetime.now()
    print(f"Refresh starting at {start:%Y-%m-%d %H:%M}", flush=True)
    before_digest = file_digest(DB_PATH)

    if not args.skip_monthly:
        _run_step("Monthly update",
                   [sys.executable, "scripts/update_monthly.py"])
    if not args.skip_weekly:
        _run_step("Weekly update",
                   [sys.executable, "scripts/update_weekly.py"])
    if not args.skip_nonbank:
        # BDDK non-bank financial sectors (BultenAylikBdmk): leasing, factoring,
        # financing companies, VYŞ asset management. Sibling of the monthly bank
        # bulletin; incremental (latest+1 → now). Non-critical: a BDDK-portal
        # outage here must not abort the core bank refresh — next cron self-heals.
        _run_step("Non-bank sector update",
                   [sys.executable, "scripts/update_nonbank.py"],
                   critical=False)
    if not args.skip_evds:
        _run_step("EVDS update",
                   [sys.executable, "-m", "src.scrapers.evds_scraper",
                    "--frequencies", args.evds_frequencies])
    if not args.skip_tbb:
        # Quarterly source; latest 2 reports refresh the newest quarter and pick
        # up TBB's revisions. Non-critical: a TBB outage must not abort the core
        # BDDK refresh — the next cron retries.
        _run_step("TBB digital-banking update",
                   [sys.executable, "scripts/update_tbb_digital.py"],
                   critical=False)
        # Monthly remote-vs-branch acquisition report (separate publication). The
        # workbook is cumulative, so one fetch refreshes the full history.
        _run_step("TBB acquisition update",
                   [sys.executable, "scripts/update_tbb_acquisition.py"],
                   critical=False)
    if not args.skip_tkbb:
        # Participation-bank digital stats from TKBB's Veri Peteği (Turboard
        # JSON API). Incremental: fetches only quarters missing locally plus the
        # newest stored one. Non-critical: a TKBB outage must not abort the core
        # BDDK refresh — the next cron retries.
        _run_step("TKBB digital-banking update",
                   [sys.executable, "scripts/update_tkbb_digital.py"],
                   critical=False)
        # Monthly remote-vs-branch acquisition. The public dashboard exposes a
        # rolling 12-month window; each run upserts it and history accumulates.
        _run_step("TKBB acquisition update",
                   [sys.executable, "scripts/update_tkbb_acquisition.py"],
                   critical=False)
    if not args.skip_tuik:
        # TÜİK national-accounts + PPI detail EVDS doesn't carry (GDP expenditure
        # detail, PPI Main Industrial Groupings, CPI weights) → evds_series TUIK.*.
        # Bulletin Excel via the veriportali theme tree. Non-critical: a TÜİK
        # outage must not abort the core refresh; data is monthly/quarterly so the
        # next cron self-heals. Rides the EVDS lane (its evds_series snapshot/push).
        _run_step("TÜİK detail update",
                   [sys.executable, "scripts/update_tuik.py"],
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
    if not args.skip_faaliyet:
        # Bank annual-report (Faaliyet Raporu) franchise stats — incremental:
        # only (bank, year) targets newly added to faaliyet_report_urls.json that
        # aren't already success=1 are fetched, so this is a no-op once a year's
        # reports are in. Annual cadence + R2 acquisition; the fleet backfill runs
        # in backfill-faaliyet.yml. Non-critical: a bank-IR outage (or absent R2
        # creds on a creds-less cron) must not abort the core BDDK refresh.
        _run_step("Faaliyet franchise update",
                   [sys.executable, "scripts/update_faaliyet.py"],
                   critical=False)

    changed = before_digest != file_digest(DB_PATH)
    if args.change_file:
        change_path = Path(args.change_file)
        change_path.parent.mkdir(parents=True, exist_ok=True)
        change_path.write_text("true" if changed else "false", encoding="utf-8")

    if changed and not args.defer_packaging:
        vacuum()
        gzip_db()
    elif changed:
        print("\nSQLite changed; packaging deferred to the workflow handoff.",
              flush=True)
    else:
        print("\n======== QUIET RUN ========", flush=True)
        print("No SQLite changes; skipping VACUUM, gzip, D1/R2 handoff.", flush=True)

    if args.push and changed:
        git_push(start.strftime("%Y-%m-%d"))

    elapsed = (datetime.now() - start).total_seconds() / 60
    print(f"\nRefresh complete in {elapsed:.1f}m.", flush=True)


if __name__ == "__main__":
    main()
